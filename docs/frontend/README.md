# Ra7al Backend — Frontend Integration Documentation

Welcome! This is the **entry point** for integrating the Ra7al (University Bus Management System) frontend with the backend API. Everything here is generated directly from the current backend code — field names, endpoints, roles, and business rules reflect the real implementation, not plans or legacy behavior.

---

## 1. Project Overview

The API exposes **92 endpoints across 13 routers** (12 routers under `/api/v1` — Auth, Users, Universities, Buses, Stations, Routes, Trips, Reservations, Payments, Subscription Plans, Subscriptions, Boarding — plus the unversioned Health router), all documented in [API_REFERENCE.md](API_REFERENCE.md).

Ra7al is a university bus management platform:

- **Students** register (pending CEO approval), browse routes/plans, purchase subscriptions, book trip seats, and board buses using a QR credential.
- **Supervisors** are created by the CEO, get assigned to trips, and scan/verify student QR credentials at boarding.
- **CEO** is the administrative role: approves students, creates supervisors, manages fleets (buses), stations, routes, trips, subscription plans, payments, and monitors all data.

## 2. Backend Purpose & Technology Stack

| Layer | Technology |
|---|---|
| Framework | Python 3.12 + FastAPI (ASGI, Uvicorn) |
| Database | PostgreSQL 16 (SQLAlchemy 2.0 ORM, Alembic migrations) |
| Validation | Pydantic v2 (all request/response bodies) |
| Auth | JWT bearer tokens (HS256), OAuth2 password flow |
| Storage | Pluggable: local filesystem (dev) or **Supabase Storage** (production), private buckets |
| Rate limiting | Sliding window per client IP (in-memory or Redis) |
| Deployment | Docker / Vercel (`api/index.py` exports the FastAPI app) |

## 3. Environment Requirements

| Environment | Notes |
|---|---|
| **Development** | `APP_ENV=development`. Local run: `uvicorn app.main:app --reload` at `http://localhost:8000`. Local CORS origins are auto-added (`localhost:3000`, `localhost:5173`, `127.0.0.1:3000`). Storage backend is `local`. |
| **Production** | `APP_ENV=production`, `DEBUG=false`. Strict validation forbids default secrets and wildcard CORS. Storage backend is `supabase` (private buckets, backend-only credentials). Deployed via Docker or Vercel serverless. |

## 4. Base URLs

The exact production domain is configured per deployment and is **not hardcoded** in the repository (`UNKNOWN / VERIFY WITH BACKEND` for the final public hostname). Configure your frontend like this:

```
Development:  http://localhost:8000
Production:   UNKNOWN / VERIFY WITH BACKEND (deployment-provided domain)

API prefix:   /api/v1
Full example: {API_BASE_URL}/api/v1/auth/login
```

Recommended frontend config:

```env
VITE_API_BASE_URL=http://localhost:8000   # or the production domain
```

> A handful of endpoints are **unversioned** (no `/api/v1`): `GET /health`, `GET /health/db`, and the Swagger docs routes. Everything else lives under `/api/v1`.

## 5. API Version

- Version prefix: **`/api/v1`** (set by `API_V1_PREFIX`).
- The OpenAPI document reports version `0.1.0`.

## 6. Authentication Mechanism

- **Bearer JWT** via the `Authorization: Bearer <access_token>` header.
- Login uses **phone number + password** (OAuth2 password form). There is **no email login** and **no OTP verification** in the current API.
- Access tokens expire after **30 minutes** (`ACCESS_TOKEN_EXPIRE_MINUTES=30` default). There is no refresh-token endpoint — re-login when the token expires.
- New student accounts are created **PENDING** and cannot log in until the CEO approves them.

See [AUTHENTICATION.md](AUTHENTICATION.md).

## 7. Available Roles

| Role | Description |
|---|---|
| `CEO` | Full administrative access. |
| `SUPERVISOR` | Trip operations: boarding scans, trip rosters, assigned-route data. |
| `STUDENT` | Self-service: subscriptions, reservations, QR, own payments. |

See [RBAC.md](RBAC.md) for the complete permissions matrix.

## 8. Documentation Map

| File | Contents |
|---|---|
| [API_REFERENCE.md](API_REFERENCE.md) | Every endpoint: method, path, auth, roles, request/response schemas, status codes. |
| [AUTHENTICATION.md](AUTHENTICATION.md) | Login lifecycle, JWT payload, registration, user status semantics. |
| [RBAC.md](RBAC.md) | Roles, permissions matrix, relationship-based access rules. |
| [USERS.md](USERS.md) | User management, approval/rejection lifecycle, ID cards. |
| [STUDENTS.md](STUDENTS.md) | Student registration → approval → subscription → boarding lifecycle. |
| [BUSES.md](BUSES.md) | Fleet CRUD and the complete bus-image flow. |
| [FILE_UPLOADS.md](FILE_UPLOADS.md) | Upload constraints, multipart field names, storage behavior. |
| [ROUTES.md](ROUTES.md) | Routes, stations, route stops, supervisor assignment. |
| [TRIPS.md](TRIPS.md) | Trip scheduling, status lifecycle, pickup (gathering) points. |
| [SUPERVISORS.md](SUPERVISORS.md) | Supervisor accounts, assignments, boarding permissions. |
| [SUBSCRIPTIONS.md](SUBSCRIPTIONS.md) | Plans, CEO-defined durations, subscription lifecycle, QR credential. |
| [QR_AND_BOARDING.md](QR_AND_BOARDING.md) | QR generation/scan rules, usage allowances, daily limits, error states. |
| [RESERVATIONS.md](RESERVATIONS.md) | Seat booking, capacity, cancellation. |
| [PAYMENTS.md](PAYMENTS.md) | Payment workflow for reservations and subscriptions. |
| [ERRORS.md](ERRORS.md) | Error response shapes and status-code handling guide. |
| [ENUMS.md](ENUMS.md) | All enums with exact values. |
| [FRONTEND_INTEGRATION.md](FRONTEND_INTEGRATION.md) | Step-by-step integration guide, base URL, CORS, flows. |
| [FLOW_EXAMPLES.md](FLOW_EXAMPLES.md) | End-to-end example request sequences per role. |
| [CHANGELOG.md](CHANGELOG.md) | Backend changes relevant to frontend integration. |

## 9. Swagger / OpenAPI

When the backend is running:

| Documentation | URL |
|---|---|
| Swagger UI | `/docs` |
| ReDoc | `/redoc` |
| OpenAPI JSON | `/openapi.json` |

You can log in from Swagger via the **Authorize** button (OAuth2 password flow: `username` = phone number, `password` = password).

## 10. How to Authenticate (Quick Start)

1. Obtain a phone+password account (students self-register and wait for approval; supervisors and the CEO are created by the backend team/CEO).
2. `POST /api/v1/auth/login` with `application/x-www-form-urlencoded`:

   ```
   username=%2B201012345678&password=SecurePass123!
   ```

3. Response:

   ```json
   { "access_token": "<JWT>", "token_type": "bearer" }
   ```

4. Send every subsequent request with:

   ```
   Authorization: Bearer <access_token>
   ```

## 11. First Successful API Request

```bash
curl http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer <token>"
```

Returns the current user profile (role, status, university info). Use `role` to route users to the correct dashboard.

## 12. Important Frontend Integration Notes

- **Error contract:** all backend errors are `{ "detail": "<message>" }`. Validation errors (422) use FastAPI's array format — see [ERRORS.md](ERRORS.md).
- **Pagination:** list endpoints return `{ items, total, page, page_size, total_pages }` with `page`/`page_size` query params (max 100).
- **Dates:** timestamps are ISO-8601 with timezone; subscription dates are plain `YYYY-MM-DD`.
- **Images are never public URLs.** Buses expose `image_url` as an internal storage reference (may be `null`) — display images through `GET /api/v1/buses/{bus_id}/image`, which streams bytes after access checks. ID cards likewise stream via `/api/v1/users/{user_id}/id-card` or a short-lived signed URL. See [FILE_UPLOADS.md](FILE_UPLOADS.md).
- **QR payload is opaque.** Render `qr_payload` into a QR image; never parse or count usages client-side. The backend is the single source of truth for usage allowances (`max_qr_usages`, `remaining_qr_usages`, `qr_usages_today` on subscription details).
- **Rate limits:** login/register 5 req/min/IP, ID-card upload 10/min, bus-image upload 20/min, boarding scan 60/min. Exceeding them returns `429` with a `Retry-After` header.
- **No refresh tokens:** on `401`, redirect to login.

## 13. Security Notes

- The frontend **must never** receive: JWT secret, database credentials, or the Supabase service-role key. All storage access is proxied through backend endpoints that enforce authentication and RBAC.
- CORS is an explicit allow-list (never `*`). Ensure your frontend origin is registered with the backend team — see [FRONTEND_INTEGRATION.md](FRONTEND_INTEGRATION.md#cors).
- All responses include security headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, etc.); frames/iframes embedding the API are blocked by design.
