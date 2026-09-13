# Error Handling

Verified against `app/exceptions/base.py`, `app/exceptions/handlers.py`, `app/core/middleware.py`, `app/core/rate_limiter.py`, and the FastAPI/Pydantic defaults.

---

## 1. The Universal Error Contract

Every business error — regardless of status code — returns the same shape:

```json
{ "detail": "<human-readable message>" }
```

The `detail` string is safe to display to end users (messages are descriptive and contain no secrets). This shape applies to all application exceptions:

| Exception class | Status | Typical use |
|---|---|---|
| `UnauthorizedError` | **401** | Missing/invalid/expired token, bad login credentials |
| `ForbiddenError` | **403** | Role denied, ownership/assignment violations |
| `NotFoundError` | **404** | Resource does not exist |
| `ConflictError` | **409** | Duplicate business state (phone exists, overlapping subscription, schedule conflict, duplicate scan) |
| `ValidationError` | **422** | Business rule failure (inactive route/plan, past start date, QR limit reached) |
| `AppException` (base) | configurable | Rare internal cases (e.g. `501` signed URL on local storage, `503` storage unavailable) |

## 2. Status Codes Actually Returned by the API

| Status | Source | Example |
|---|---|---|
| `400` | **Not used.** The backend never returns 400; client errors use 401/403/404/409/422. | — |
| `401` | Auth failures | `"Not authenticated"` (missing header), `"Invalid or expired authentication token"`, `"Incorrect phone number or password"` |
| `403` | RBAC + ownership | `"Access denied: current role 'STUDENT' lacks required role (CEO)"`, `"Account is pending CEO approval."` (at login), `"You are not assigned as the supervisor for this trip"` |
| `404` | Missing resources | `"Bus with ID 3 not found"`, `"Invalid QR token or subscription not found"`, `"Bus with ID 3 has no image"` |
| `409` | Business conflicts | `"A user with this phone number already exists"`, `"No available seats for this trip"`, `"Student has already boarded OUTBOUND for this trip"`, `"An active subscription (ID: 88) already exists for this route…"`, bus/supervisor schedule conflicts |
| `422` | Two distinct shapes — see §3 | Business messages or FastAPI validation arrays |
| `429` | Rate limiting | `"Too many requests. Please try again later."` + `Retry-After` header |
| `500` | Unhandled exceptions | `"Internal server error"` |
| `501` | Signed URL on local storage backend | `"Temporary signed URLs are only supported with the Supabase storage backend…"` |
| `503` | Storage backend unreachable | `"Storage service unavailable"` |
| `200` / `201` / `204` | Success codes (`204` = deleted resource, empty body) | — |

## 3. The Two `422` Shapes (important distinction)

### 3a. Business-rule 422 — object form

Raised by services (`ValidationError`), rendered as the standard object:

```json
{ "detail": "Subscription start date cannot be in the past" }
```

### 3b. Request-validation 422 — array form (FastAPI/Pydantic)

Malformed or schema-invalid requests (bad types, missing required fields, constraint violations) produce FastAPI's native format:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "password"],
      "msg": "Field required",
      "input": { "full_name": "Ahmed Ali" }
    }
  ]
}
```

- `loc[0]` is `"body"`, `"query"`, or `"path"`; `loc[1+]` is the field path.
- Pydantic custom messages (e.g. `"Invalid phone number format"`, `"DAILY plans must use a duration of exactly 1 day"`) appear in `msg`.

**Frontend handling:** check `Array.isArray(body.detail)` — render the array form by joining `msg`s (or map `loc` to form fields); otherwise show `detail` as-is.

## 4. Validation Rules with Real Examples

Registration (`POST /auth/register`) validation failures (422 array form):
- `phone_number` not matching `^\+?[0-9]{7,15}$` → `"Invalid phone number format"` (business 409 if already registered).
- `password` shorter than 8 chars → `String should have at least 8 characters`.
- Blank `full_name`/`faculty`/`academic_year` → `"Full name cannot be empty or blank"` etc.

Plan creation (`POST /subscription-plans`):
- `duration_days` > 730 → `less_than_equal` constraint violation.
- `DAILY` with `duration_days != 1` → `"DAILY plans must use a duration of exactly 1 day"`.

Pagination bounds: `page < 1` or `page_size > 100` → `422`.

## 5. Rate Limiting (429)

Sliding window **per client IP** (not per user):

| Endpoint | Limit |
|---|---|
| `POST /auth/login` | 5 / minute |
| `POST /auth/register` | 5 / minute |
| `POST /auth/upload-id-card` | 10 / minute |
| Bus image upload endpoints | 20 / minute |
| `POST /boarding/scan` | 60 / minute |
| Everything else | No limit |

Response:

```
429
Retry-After: 37
{ "detail": "Too many requests. Please try again later." }
```

Honor `Retry-After` (seconds) before retrying.

## 6. Recommended Frontend Handling Matrix

| Status | Meaning | Recommended action |
|---|---|---|
| 401 | Not authenticated / token expired / bad credentials | Clear token; redirect to login. At login: show `detail` ("Incorrect phone number or password"). |
| 403 | Authenticated but not permitted (role/ownership/lifecycle) | Show `detail` message; hide the triggering action. At login: show pending/rejected/inactive message verbatim. |
| 404 | Resource missing (or "no image" on image endpoints) | Show not-found state; refresh lists. |
| 409 | Conflict with current state | Refresh the affected data and inform the user (seat taken, duplicate scan, phone exists, schedule overlap). |
| 422 (object) | Business rule rejected | Display `detail`; it names the exact rule. |
| 422 (array) | Request malformed | Map `loc`→field / join `msg`s for a form error banner. |
| 429 | Rate limited | Wait `Retry-After` seconds; disable the submit control meanwhile. |
| 500 | Unexpected server error | Generic error UI + retry option; report to backend with timestamp. |
| 501/503 | Storage feature unavailable / storage down | For signed URLs: fall back to the streaming endpoint in development; for 503: retry later. |

## 7. Security Headers on Every Response

`SecurityHeadersMiddleware` adds (frontend-visible behavior):

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), camera=(), microphone=()
Content-Security-Policy: default-src 'self' https://cdn.jsdelivr.net; … frame-ancestors 'none'
```

Notes: `X-Frame-Options: DENY` + `frame-ancestors 'none'` mean API responses cannot be embedded in iframes. Image streaming endpoints additionally set `Cache-Control: private, max-age=300` and `nosniff`.

Unhandled server errors (500) are also given CORS headers when the origin is allow-listed, so the browser surfaces the real 500 instead of masking it as a CORS failure.
