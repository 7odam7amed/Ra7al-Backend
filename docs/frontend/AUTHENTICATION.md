# Authentication

Complete authentication lifecycle, verified against `app/api/v1/auth.py`, `app/services/auth_service.py`, and `app/core/security.py`.

---

## 1. Authentication Model

- **Credentials:** phone number + password. There is **no email login** and **no OTP verification** anywhere in the current API.
- **Mechanism:** OAuth2 password flow returning a JWT bearer access token.
- **Header:** `Authorization: Bearer <access_token>` on every authenticated request.
- **Token expiry:** 30 minutes (server setting `ACCESS_TOKEN_EXPIRE_MINUTES`). **No refresh-token endpoint exists** — when a token expires you get `401`; the frontend should redirect to login.
- **Password hashing:** Argon2, server-side. Minimum password length 8 characters (enforced at registration and supervisor creation).
- **Phone normalization:** the server normalizes phone numbers to E.164 (adds leading `+`, strips spaces/dashes/parentheses). Send digits with or without `+`; both work. Stored/logged-in identity is the normalized form.

## 2. Login

### Endpoint

```
POST /api/v1/auth/login
```

Public (no auth). Rate limited: 5 requests / minute / IP.

### Request

`Content-Type: application/x-www-form-urlencoded` (OAuth2 password form — **not** JSON):

| Field | Type | Description |
|---|---|---|
| `username` | string | The user's **registered phone number** |
| `password` | string | Plain password |

```
username=%2B201012345678&password=SecurePass123!
```

> A `LoginJSONRequest` Pydantic model (`phone_number`, `password`) exists in the schema file, but the login endpoint **does not accept JSON** — it only reads the OAuth2 form. Send form-urlencoded.

### Response — `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<payload>.<signature>",
  "token_type": "bearer"
}
```

| Field | Type | Description |
|---|---|---|
| `access_token` | string | JWT access token |
| `token_type` | string | Always `"bearer"` |

### Status codes

| Code | When |
|---|---|
| 200 | Success |
| 401 | Wrong phone number or wrong password (`"Incorrect phone number or password"`) |
| 403 | Account exists but is not permitted to log in — see status table below |
| 422 | Missing/blank form fields |
| 429 | Rate limit exceeded (5/min/IP), includes `Retry-After` header |

### Login behavior per account status

| Account state | Result |
|---|---|
| `APPROVED` + `is_active=true` | 200 + token |
| `PENDING` | 403 — `"Account is pending CEO approval."` |
| `REJECTED` | 403 — `"Account has been rejected."` |
| `INACTIVE` or `is_active=false` | 403 — `"Account is inactive."` |
| Any other non-approved status | 403 — `"Account is not active."` |

## 3. JWT Payload

The token is signed HS256 and contains:

```json
{
  "sub": "42",          // user ID as string
  "role": "STUDENT",    // CEO | SUPERVISOR | STUDENT
  "iat": 1757800000,
  "exp": 1757801800
}
```

> `role` is embedded as a claim, but the backend re-derives authorization from the database user record on every request. Treat the token as opaque; call `GET /api/v1/auth/me` after login to obtain authoritative profile/role data.

## 4. Current User

```
GET /api/v1/auth/me
```

Authenticated. Returns `UserResponse` for the token owner:

```json
{
  "id": 42,
  "full_name": "Ahmed Ali",
  "phone_number": "+201012345678",
  "gender": "MALE",
  "role": "STUDENT",
  "status": "APPROVED",
  "rejection_reason": null,
  "is_active": true,
  "university_id": 1,
  "faculty": "Faculty of Engineering",
  "academic_year": "3rd Year",
  "university_id_card_image": "uploads/id_cards/6f1c...png",
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:00:00Z"
}
```

Status codes: `200`, `401` (missing/invalid/expired token, or the account was deactivated after token issuance).

## 5. Registration (Students)

```
POST /api/v1/auth/register
```

Public. Rate limited: 5 req/min/IP. Creates a **STUDENT** account with `status=PENDING`, `is_active=false`, awaiting CEO approval. Students cannot log in until approved.

### Request — `application/json` (`UserRegisterRequest`)

| Field | Type | Constraints |
|---|---|---|
| `full_name` | string | 1–255 chars, not blank |
| `phone_number` | string | 7–20 chars, must match `^\+?[0-9]{7,15}$` |
| `password` | string | 8–128 chars |
| `gender` | string | `"MALE"` or `"FEMALE"` |
| `university_id` | integer | > 0, must exist and be an **active** university |
| `faculty` | string | 1–100 chars, not blank |
| `academic_year` | string | 1–50 chars, not blank |
| `university_id_card_image` | string | 1–500 chars — the `image_path` returned by the ID-card upload (see below) |

```json
{
  "full_name": "Ahmed Ali",
  "phone_number": "+201012345678",
  "password": "SecurePass123!",
  "gender": "MALE",
  "university_id": 1,
  "faculty": "Faculty of Engineering",
  "academic_year": "3rd Year",
  "university_id_card_image": "uploads/id_cards/6f1c9e2a8b7d4f0c.png"
}
```

### Response — `201 Created` (`UserRegisterResponse`)

Same shape as `UserResponse` plus a `message` field:

```json
{
  "id": 42,
  "full_name": "Ahmed Ali",
  "phone_number": "+201012345678",
  "gender": "MALE",
  "role": "STUDENT",
  "status": "PENDING",
  "rejection_reason": null,
  "is_active": false,
  "university_id": 1,
  "faculty": "Faculty of Engineering",
  "academic_year": "3rd Year",
  "university_id_card_image": "uploads/id_cards/6f1c9e2a8b7d4f0c.png",
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:00:00Z",
  "message": "Registration submitted. Your account is pending CEO approval."
}
```

### Status codes

| Code | When |
|---|---|
| 201 | Registered (pending approval) |
| 404 | `university_id` does not exist |
| 409 | Phone number already registered |
| 422 | Validation failure, or university inactive, or ID-card image missing |
| 429 | Rate limited |

### Registration flow for the frontend

```
[Registration form]
   ↓
POST /api/v1/auth/upload-id-card     (multipart, field "file")
   ↓  ← { "image_path": "uploads/id_cards/<uuid>.png" }
POST /api/v1/auth/register           (JSON incl. university_id_card_image)
   ↓  ← 201 { status: "PENDING", message: "..." }
Show "pending approval" screen
   ↓ (CEO approves)
POST /api/v1/auth/login  →  200 token
```

## 6. ID-Card Upload (pre-registration)

```
POST /api/v1/auth/upload-id-card
```

Public (needed before the account exists). Rate limited: 10 req/min/IP.

- `Content-Type: multipart/form-data`, single file field **`file`**.
- Accepted: JPEG/PNG/WEBP images, ≤ 5 MB, extension must match content signature.
- Response `201`:

```json
{ "image_path": "uploads/id_cards/6f1c9e2a8b7d4f0c.png" }
```

Pass `image_path` verbatim as `university_id_card_image` in the register call. Full validation rules: [FILE_UPLOADS.md](FILE_UPLOADS.md).

## 7. Logout

There is **no logout endpoint** and no server-side token revocation. "Logout" = delete the token from client storage. Tokens remain valid until `exp` (30 min).

## 8. Account Status Semantics (`UserStatus`)

| Status | Meaning | Can log in? |
|---|---|---|
| `PENDING` | Registered, awaiting CEO approval | No (403) |
| `APPROVED` | Approved by CEO (alias: legacy `"ACTIVE"` maps to `APPROVED`) | Yes |
| `REJECTED` | Rejected by CEO (with optional `rejection_reason`) | No (403) |
| `INACTIVE` | Deactivated by CEO | No (403) |

`status` and `is_active` are kept consistent server-side; a user must have **both** `status == APPROVED` and `is_active == true` to authenticate or to pass any authenticated endpoint.

## 9. Frontend Token Handling Recommendations

- Store the token in memory or `localStorage`/`sessionStorage` per your security posture; the API is stateless and browser-based.
- Attach `Authorization: Bearer <token>` via an HTTP interceptor.
- On `401`: clear the token, redirect to login. On `403` at login: show the exact `detail` message (pending/rejected/inactive) — it is user-appropriate.
- Do **not** decode the JWT to make authorization decisions; use `GET /api/v1/auth/me`.
