# Complete API Reference

Every HTTP endpoint exposed by the backend — **92 endpoints across 13 routers** — verified from `app/main.py`, `app/api/health.py`, and all routers in `app/api/v1/`.

- Base URL: `{API_BASE_URL}` (e.g. `http://localhost:8000` in development).
- Versioned prefix: **`/api/v1`**. Two health endpoints are unversioned.
- Auth column: 🔓 public · 🔒 any authenticated user · role lists show exact restriction.
- All error bodies are `{"detail": "..."}` — see [ERRORS.md](ERRORS.md). All list endpoints paginate (`page`, `page_size` ≤ 100) and return `{items, total, page, page_size, total_pages}` — see [Pagination](#pagination-contract).
- Types like `UserResponse`, `TripResponse` are defined in the per-domain docs and in [ENUMS.md](ENUMS.md).

## Endpoint Index

### Health (unversioned)
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| GET | `/health` | 🔓 | — | [Health](#health) |
| GET | `/health/db` | 🔓 | — | [Health](#health) |

### Auth — `/api/v1/auth`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/auth/upload-id-card` | 🔓 | public | [Auth](#auth) |
| POST | `/auth/register` | 🔓 | public | [Auth](#auth) |
| POST | `/auth/login` | 🔓 | public | [Auth](#auth) |
| GET | `/auth/me` | 🔒 | any | [Auth](#auth) |

### Users — `/api/v1/users`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| GET | `/users` | 🔒 | CEO | [Users](#users) |
| GET | `/users/pending` | 🔒 | CEO | [Users](#users) |
| POST | `/users/supervisors` | 🔒 | CEO | [Users](#users) |
| GET | `/users/{user_id}` | 🔒 | CEO | [Users](#users) |
| GET | `/users/{user_id}/id-card` | 🔒 | CEO / owner student | [Users](#users) |
| GET | `/users/{user_id}/id-card/signed-url` | 🔒 | CEO / owner student | [Users](#users) |
| PATCH | `/users/{user_id}` | 🔒 | CEO | [Users](#users) |
| PATCH | `/users/{user_id}/role` | 🔒 | CEO | [Users](#users) |
| PATCH | `/users/{user_id}/status` | 🔒 | CEO | [Users](#users) |
| PATCH | `/users/{user_id}/approve` | 🔒 | CEO | [Users](#users) |
| PATCH | `/users/{user_id}/reject` | 🔒 | CEO | [Users](#users) |

### Universities — `/api/v1/universities`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| GET | `/universities` | 🔓 | public | [Universities](#universities) |
| GET | `/universities/{university_id}` | 🔓 | public | [Universities](#universities) |
| POST | `/universities` | 🔒 | CEO | [Universities](#universities) |
| PATCH | `/universities/{university_id}` | 🔒 | CEO | [Universities](#universities) |
| DELETE | `/universities/{university_id}` | 🔒 | CEO | [Universities](#universities) |

### Buses — `/api/v1/buses`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/buses` | 🔒 | CEO | [Buses](#buses) |
| GET | `/buses` | 🔒 | CEO, SUPERVISOR | [Buses](#buses) |
| GET | `/buses/{bus_id}` | 🔒 | CEO, SUPERVISOR | [Buses](#buses) |
| GET | `/buses/{bus_id}/image` | 🔒 | CEO / assigned supervisor / reserved student | [Buses](#buses) |
| GET | `/buses/{bus_id}/image/metadata` | 🔒 | CEO / assigned supervisor / reserved student | [Buses](#buses) |
| PATCH | `/buses/{bus_id}` | 🔒 | CEO | [Buses](#buses) |
| PATCH | `/buses/{bus_id}/image` | 🔒 | CEO | [Buses](#buses) |
| DELETE | `/buses/{bus_id}/image` | 🔒 | CEO | [Buses](#buses) |
| PATCH | `/buses/{bus_id}/status` | 🔒 | CEO | [Buses](#buses) |
| DELETE | `/buses/{bus_id}` | 🔒 | CEO | [Buses](#buses) |

### Stations — `/api/v1/stations` (all: CEO + SUPERVISOR)
| Method | Path | Docs |
|---|---|---|
| POST | `/stations` | [Stations](#stations) |
| GET | `/stations` | [Stations](#stations) |
| GET | `/stations/{station_id}` | [Stations](#stations) |
| PATCH | `/stations/{station_id}` | [Stations](#stations) |
| PATCH | `/stations/{station_id}/status` | [Stations](#stations) |
| DELETE | `/stations/{station_id}` | [Stations](#stations) |

### Routes — `/api/v1/routes`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/routes` | 🔒 | CEO | [Routes](#routes) |
| GET | `/routes` | 🔒 | any authenticated | [Routes](#routes) |
| GET | `/routes/{route_id}` | 🔒 | any authenticated | [Routes](#routes) |
| PATCH | `/routes/{route_id}` | 🔒 | CEO | [Routes](#routes) |
| PATCH | `/routes/{route_id}/status` | 🔒 | CEO | [Routes](#routes) |
| DELETE | `/routes/{route_id}` | 🔒 | CEO | [Routes](#routes) |
| POST | `/routes/{route_id}/pickup-points` | 🔒 | CEO | [Routes](#routes) |
| GET | `/routes/{route_id}/pickup-points` | 🔒 | any authenticated | [Routes](#routes) |
| PATCH | `/routes/{route_id}/pickup-points/{point_id}` | 🔒 | CEO | [Routes](#routes) |
| DELETE | `/routes/{route_id}/pickup-points/{point_id}` | 🔒 | CEO | [Routes](#routes) |

### Trips — `/api/v1/trips`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/trips` | 🔒 | CEO | [Trips](#trips) |
| GET | `/trips` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| GET | `/trips/history` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| GET | `/trips/{trip_id}` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| PATCH | `/trips/{trip_id}` | 🔒 | CEO | [Trips](#trips) |
| PATCH | `/trips/{trip_id}/stops` | 🔒 | CEO | [Trips](#trips) |
| GET | `/trips/{trip_id}/stops` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| PATCH | `/trips/{trip_id}/status` | 🔒 | CEO | [Trips](#trips) |
| DELETE | `/trips/{trip_id}` | 🔒 | CEO | [Trips](#trips) |
| GET | `/trips/route-points/{route_id}` | 🔒 | CEO | [Trips](#trips) |

### Reservations — `/api/v1/reservations`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/reservations` | 🔒 | STUDENT (active subscription) | [Reservations](#reservations) |
| GET | `/reservations/upcoming-trips` | 🔒 | STUDENT | [Reservations](#reservations) |
| GET | `/reservations/my/selection` | 🔒 | STUDENT | [Reservations](#reservations) |
| PUT | `/reservations/my/selection` | 🔒 | STUDENT | [Reservations](#reservations) |
| GET | `/reservations/my` | 🔒 | STUDENT | [Reservations](#reservations) |
| GET | `/reservations` | 🔒 | CEO, SUPERVISOR | [Reservations](#reservations) |
| GET | `/reservations/{reservation_id}` | 🔒 | CEO, SUPERVISOR, owner student | [Reservations](#reservations) |
| PATCH | `/reservations/{reservation_id}/cancel` | 🔒 | CEO, SUPERVISOR, owner student | [Reservations](#reservations) |

### Payments — `/api/v1/payments`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/payments` | 🔒 | STUDENT | [Payments](#payments) |
| GET | `/payments/my` | 🔒 | STUDENT | [Payments](#payments) |
| GET | `/payments` | 🔒 | CEO, SUPERVISOR | [Payments](#payments) |
| GET | `/payments/{payment_id}` | 🔒 | CEO, SUPERVISOR, owner student | [Payments](#payments) |
| PATCH | `/payments/{payment_id}/submit` | 🔒 | owner STUDENT only | [Payments](#payments) |
| PATCH | `/payments/{payment_id}/cancel` | 🔒 | CEO, SUPERVISOR, owner student | [Payments](#payments) |
| PATCH | `/payments/{payment_id}/verify` | 🔒 | CEO, SUPERVISOR | [Payments](#payments) |
| PATCH | `/payments/{payment_id}/reject` | 🔒 | CEO, SUPERVISOR | [Payments](#payments) |

### Subscription Plans — `/api/v1/subscription-plans`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/subscription-plans` | 🔒 | CEO | [Subscription Plans](#subscription-plans) |
| GET | `/subscription-plans` | 🔓 | public (non-CEO sees active only) | [Subscription Plans](#subscription-plans) |
| GET | `/subscription-plans/{plan_id}` | 🔓 | public | [Subscription Plans](#subscription-plans) |
| PATCH | `/subscription-plans/{plan_id}` | 🔒 | CEO | [Subscription Plans](#subscription-plans) |
| PATCH | `/subscription-plans/{plan_id}/status` | 🔒 | CEO | [Subscription Plans](#subscription-plans) |

### Subscriptions — `/api/v1/subscriptions`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| GET | `/subscriptions/plans` | 🔒 | any | [Subscriptions](#subscriptions) |
| POST | `/subscriptions` | 🔒 | STUDENT | [Subscriptions](#subscriptions) |
| GET | `/subscriptions/my` | 🔒 | STUDENT | [Subscriptions](#subscriptions) |
| GET | `/subscriptions` | 🔒 | CEO | [Subscriptions](#subscriptions) |
| GET | `/subscriptions/{subscription_id}` | 🔒 | CEO / assigned supervisor / owner student | [Subscriptions](#subscriptions) |
| GET | `/subscriptions/{subscription_id}/qr` | 🔒 | owner student (ACTIVE sub only) | [Subscriptions](#subscriptions) |
| GET | `/subscriptions/{subscription_id}/history` | 🔒 | CEO / assigned supervisor / owner student | [Subscriptions](#subscriptions) |
| PATCH | `/subscriptions/{subscription_id}/renew` | 🔒 | CEO / owner student | [Subscriptions](#subscriptions) |
| PATCH | `/subscriptions/{subscription_id}/cancel` | 🔒 | CEO / owner student (PENDING) | [Subscriptions](#subscriptions) |

### Boarding — `/api/v1/boarding`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/boarding/scan` | 🔒 | SUPERVISOR (assigned to trip) | [Boarding](#boarding) |
| GET | `/boarding/trips/{trip_id}/students` | 🔒 | CEO, assigned SUPERVISOR | [Boarding](#boarding) |
| GET | `/boarding/trips/{trip_id}/records` | 🔒 | CEO, assigned SUPERVISOR | [Boarding](#boarding) |
| GET | `/boarding/records` | 🔒 | CEO | [Boarding](#boarding) |

---

## Pagination Contract

All list endpoints (except `GET /subscriptions/plans`, boarding history's flat list, and the trip-student/record lists) accept:

| Query param | Type | Default | Constraints |
|---|---|---|---|
| `page` | int | 1 | ≥ 1 |
| `page_size` | int | 20 | 1–100 |

Response envelope (identical everywhere):

```json
{
  "items": [ ... ],
  "total": 57,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

`total_pages = ceil(total / page_size)` when `total > 0`, else `0`.

---

## Health

### `GET /health`
- 🔓 Public. Purpose: liveness probe.
- Response `200`:

```json
{ "status": "ok" }
```

### `GET /health/db`
- 🔓 Public. Purpose: database connectivity probe.
- Response `200`:

```json
{ "status": "ok", "database": "connected" }
```

- Response `503` (database down):

```json
{ "status": "error", "database": "disconnected" }
```

---

## Auth

### `POST /auth/upload-id-card`
Upload a university ID-card image **before** registering; returns a storage reference to send as `university_id_card_image`.

- 🔓 Public. Rate limit: 10/min/IP.
- Request: `multipart/form-data`, file field **`file`**. JPEG/PNG/WEBP, ≤ 5 MB.
- Response `201`:

```json
{ "image_path": "uploads/id_cards/6f1c9e2a8b7d4f0c.png" }
```

- Errors: `422` (bad extension/MIME/signature/size/empty), `429`.
- Frontend notes: call this first, then `POST /auth/register`. Details: [FILE_UPLOADS.md](FILE_UPLOADS.md).

### `POST /auth/register`
Creates a STUDENT account with `status=PENDING`, `is_active=false`. Full schema: [AUTHENTICATION.md](AUTHENTICATION.md#5-registration-students).

- Request `application/json` — `full_name`, `phone_number`, `password`, `gender`, `university_id`, `faculty`, `academic_year`, `university_id_card_image` (all required).
- Response `201`: `UserRegisterResponse` = `UserResponse` + `message: "Registration submitted. Your account is pending CEO approval."`, `status: "PENDING"`, `is_active: false`.
- Errors: `404` unknown university, `409` phone exists, `422` validation/inactive university, `429`.

### `POST /auth/login`
OAuth2 password form (`username` = phone number, `password`). Response `200`:

```json
{ "access_token": "<JWT>", "token_type": "bearer" }
```

Errors: `401` bad credentials, `403` pending/rejected/inactive, `422`, `429`. Full details: [AUTHENTICATION.md](AUTHENTICATION.md).

### `GET /auth/me`
Current user profile. Response `200`: `UserResponse` (see [AUTHENTICATION.md](AUTHENTICATION.md#4-current-user)). Errors: `401`.

---

## Users

`UserResponse` shape (all user endpoints):

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
  "university_id_card_image": "uploads/id_cards/6f1c.png",
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:00:00Z"
}
```

### `GET /users` — CEO
Query: `page`, `page_size`, `role` (RoleEnum, optional), `is_active` (bool, optional), `status` (UserStatus, optional).
Response `200`: `PaginatedUserResponse` (envelope of `UserResponse`).

### `GET /users/pending` — CEO
Query: `page`, `page_size`. Returns users with `status=PENDING`. Response `200`: `PaginatedUserResponse`.

### `POST /users/supervisors` — CEO
Creates an already-approved, active SUPERVISOR account.

Request:

```json
{
  "full_name": "Sara Supervisor",
  "phone_number": "+201098765432",
  "password": "SuperSecret123!",
  "gender": "FEMALE"
}
```

Response `201`: `UserResponse` with `role: "SUPERVISOR"`, `status: "APPROVED"`, `is_active: true`.
Errors: `409` phone exists, `422`.

### `GET /users/{user_id}` — CEO
Response `200`: `UserResponse`. Errors: `404`.

### `GET /users/{user_id}/id-card` — CEO or owner student
Streams the ID-card image bytes.

- Response `200`: raw image bytes, `Content-Type: image/jpeg|image/png|image/webp`, `X-Content-Type-Options: nosniff`.
- Errors: `403` (not owner/CEO, or supervisor), `404` (user or stored file missing).

### `GET /users/{user_id}/id-card/signed-url` — CEO or owner student
Query: `expires_in` (int, default 60, 1–300 seconds).
Response `200`:

```json
{
  "url": "https://<supabase>/storage/v1/object/sign/...",
  "signed_url": "https://<supabase>/storage/v1/object/sign/...",
  "expires_in": 60
}
```

> Signed URLs require the **Supabase** storage backend (production). On the `local` backend this returns **501**. Prefer the streaming endpoint in development.

### `PATCH /users/{user_id}` — CEO
Request (all optional): `full_name`, `gender`, `phone_number`, `faculty`, `academic_year`.
Response `200`: `UserResponse`. Errors: `409` phone taken, `422`.

### `PATCH /users/{user_id}/role` — CEO
Request:

```json
{ "role": "SUPERVISOR" }
```

Only `STUDENT` and `SUPERVISOR` are assignable via this endpoint (assigning CEO returns 422). CEO cannot change own role; cannot demote the last active CEO.
Response `200`: `UserResponse`. Errors: `403` (self-target), `404`, `422`.

### `PATCH /users/{user_id}/status` — CEO
Activate/deactivate. Request (at least one of):

```json
{ "is_active": false }
```
```json
{ "status": "INACTIVE" }
```

If only `status` given, `is_active` is derived (`APPROVED` → active). If only `is_active` given, status becomes `APPROVED`/`INACTIVE` accordingly. Cannot deactivate the last active CEO.
Response `200`: `UserResponse`. Errors: `404`, `422`.

### `PATCH /users/{user_id}/approve` — CEO
`PENDING → APPROVED` (sets `is_active=true`, clears rejection reason). Approving an already-approved user returns it unchanged. No body.
Response `200`: `UserResponse`. Errors: `403` self-approve, `404`, `422` (user is REJECTED).

### `PATCH /users/{user_id}/reject` — CEO
`PENDING → REJECTED`. Optional body:

```json
{ "reason": "University ID card image is blurred and illegible." }
```

Body may be omitted entirely. Cannot reject an APPROVED user.
Response `200`: `UserResponse` (with `rejection_reason` set). Errors: `403`, `404`, `422`.

---

## Universities

`UniversityResponse`:

```json
{ "id": 1, "name": "Cairo University", "is_active": true, "created_at": "...", "updated_at": "..." }
```

### `GET /universities` — 🔓 public
Query: `page`, `page_size`, `is_active` (bool), `search` (name).
Response `200`: `PaginatedUniversityResponse`.

### `GET /universities/{university_id}` — 🔓 public
Response `200`: `UniversityResponse`. Errors: `404`.

### `POST /universities` — CEO
Request: `{ "name": "Cairo University" }`. Response `201`: `UniversityResponse` (`is_active: true`). Errors: `409` duplicate name.

### `PATCH /universities/{university_id}` — CEO
Request (optional fields): `{ "name": "Ain Shams University", "is_active": true }`. Response `200`. Errors: `404`, `409`.

### `DELETE /universities/{university_id}` — CEO
Fails with `409` if any student is still registered. Success: `204` no body.

---

## Buses

`BusResponse`:

```json
{
  "id": 3,
  "bus_number": "BUS-101",
  "license_plate": "ABC-1234",
  "capacity": 50,
  "model": "Mercedes-Benz Travego",
  "year": 2022,
  "status": "ACTIVE",
  "image_url": "uploads/bus_images/9ab7d3e1.png",
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:00:00Z"
}
```

> `image_url` is an **internal storage reference**, not a browser-usable URL. It is `null` when the bus has no image. Display via `GET /buses/{bus_id}/image`. Full flow: [BUSES.md](BUSES.md).

### `POST /buses` — CEO
Accepts **both** `application/json` and `multipart/form-data` (multipart required when uploading an image). Rate limit: 20/min/IP (upload limiter).

Fields (`BusCreateRequest` — field names identical in JSON and multipart):

| Field | Required | Type | Notes |
|---|---|---|---|
| `bus_number` | conditional* | string ≤ 50 | *if omitted, `name` is used |
| `name` | conditional* | string ≤ 50 | alias for `bus_number` |
| `license_plate` | conditional* | string ≤ 50 | *if omitted, `plate_number` is used; stored UPPERCASE |
| `plate_number` | conditional* | string ≤ 50 | alias for `license_plate` |
| `capacity` | no (default 50) | int > 0, ≤ 150 | |
| `model` | no | string ≤ 100 | alias: `type` |
| `type` | no | string ≤ 100 | alias for `model` |
| `year` | no | int 1990–2050 | |
| `image` | no | file | multipart only |

A final `bus_number` and `license_plate` are **mandatory** (422 if both aliases blank). New buses start `status: "ACTIVE"`.

Example (multipart with image):

```http
POST /api/v1/buses
Content-Type: multipart/form-data; boundary=...
Authorization: Bearer <token>

------boundary
Content-Disposition: form-data; name="bus_number"

BUS-101
------boundary
Content-Disposition: form-data; name="license_plate"

ABC-1234
------boundary
Content-Disposition: form-data; name="capacity"

50
------boundary
Content-Disposition: form-data; name="image"; filename="bus.png"
Content-Type: image/png

<binary>
------boundary--
```

Example (JSON, no image):

```json
{ "bus_number": "BUS-102", "license_plate": "XYZ-5678", "capacity": 45, "year": 2023 }
```

Response `201`: `BusResponse` (`image_url` null or the stored reference).
Errors: `409` duplicate bus_number or license_plate, `422` validation or bad image, `429`.

### `GET /buses` — CEO, SUPERVISOR
Query: `page`, `page_size`, `status` (BusStatus), `search` (matches bus number, license plate, or model).
Response `200`: `PaginatedBusResponse`.

### `GET /buses/{bus_id}` — CEO, SUPERVISOR
Response `200`: `BusResponse`. Errors: `404`.

### `GET /buses/{bus_id}/image` — CEO / assigned supervisor / student with CONFIRMED reservation on a trip using this bus
Streams image bytes.

- Response `200`: raw bytes with `Content-Type: image/*`, headers `X-Content-Type-Options: nosniff`, `Cache-Control: private, max-age=300`.
- Errors: `403` (no relationship), `404` (bus exists but has **no image**, or bus missing).
- Frontend notes: fetch as a blob with the `Authorization` header (cannot use `<img src>` directly). See [BUSES.md](BUSES.md).

### `GET /buses/{bus_id}/image/metadata` — same access rules as above
Response `200`:

```json
{
  "bus_id": 3,
  "has_image": true,
  "image_url": "uploads/bus_images/9ab7d3e1.png",
  "image_stream_url": "/api/v1/buses/3/image"
}
```

`image_stream_url` is `null` when `has_image` is false.

### `PATCH /buses/{bus_id}` — CEO
Request (all optional): `bus_number`/`name`, `license_plate`/`plate_number`, `capacity` (>0 ≤150), `model`/`type`, `year`.
Response `200`: `BusResponse`. Errors: `409` duplicates, `404`, `422`.

### `PATCH /buses/{bus_id}/image` — CEO
Multipart, field **`image`** (required). Replaces the image; the previous stored object is deleted after success.
Response `200`: `BusResponse`. Errors: `404`, `422` (no file / bad image), `429`.

### `DELETE /buses/{bus_id}/image` — CEO
Removes and deletes the stored image. Fails `422` if the bus has no image.
Response `200`: `BusResponse` (`image_url: null`).

### `PATCH /buses/{bus_id}/status` — CEO
Request: `{ "status": "MAINTENANCE" }` (BusStatus). Response `200`: `BusResponse`.

### `DELETE /buses/{bus_id}` — CEO
Fails `409` if the bus has active scheduled trips (deactivate it instead). Success: `204`.

---

## Stations

All endpoints require CEO or SUPERVISOR.

`StationResponse`:

```json
{
  "id": 1,
  "name": "Main Campus Gate",
  "code": "ST-CAMPUS-01",
  "address": "123 University Avenue, Cairo",
  "latitude": 30.0444,
  "longitude": 31.2357,
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

### `POST /stations`
Request:

```json
{ "name": "Main Campus Gate", "code": "ST-CAMPUS-01", "address": "123 University Avenue, Cairo", "latitude": 30.0444, "longitude": 31.2357 }
```

`code` is stored uppercase (unique). Response `201`. Errors: `409` duplicate code, `422`.

### `GET /stations`
Query: `page`, `page_size`, `is_active`, `search` (name/code/address). Response `200`: `PaginatedStationResponse`.

### `GET /stations/{station_id}` — `200` / `404`.

### `PATCH /stations/{station_id}`
Optional fields: `name`, `code`, `address`, `latitude`, `longitude`. Response `200`. Errors: `409`, `404`, `422`.

### `PATCH /stations/{station_id}/status`
Request: `{ "is_active": false }`. Response `200`.

### `DELETE /stations/{station_id}`
Fails `409` if referenced by any route or stop. Success: `204`.

---

## Routes

A route is a **logical container of pickup points**. It has no origin, destination, distance, duration, or supervisor. `RouteStop` no longer exists.

`RouteResponse`:

```json
{
  "id": 10,
  "name": "Route A",
  "is_active": true,
  "created_at": "...",
  "updated_at": "...",
  "pickup_points": [ { "...": "PickupPointResponse" } ]
}
```

### `POST /routes` — CEO
Request: `{ "name": "Route A" }` (1-100 chars). Response `201`: `RouteResponse`.

### `GET /routes` — any authenticated
Query: `page`, `page_size`, `is_active`, `search` (name). Response `200`: `PaginatedRouteResponse`.

### `GET /routes/{route_id}` — any authenticated
Response `200`: `RouteResponse` with `pickup_points`. Errors: `404`.

### `PATCH /routes/{route_id}` — CEO
Optional fields: `name`. Response `200`. Errors: `404`, `422`.

### `PATCH /routes/{route_id}/status` — CEO
Request: `{ "is_active": false }`. Response `200`.

### `DELETE /routes/{route_id}` — CEO
Deletes the route and its pickup points. Success: `204`.

### `POST /routes/{route_id}/pickup-points` — CEO
Request:

```json
{ "name": "Al-Mahatta", "address": null, "sequence": 1 }
```

- `route_id` in the body is ignored; the owning route comes from the URL path (a body value must match it).
- A pickup point belongs to **exactly one route** — a point already owned by another route can never be added again.
- Duplicate names on the same route are rejected (`409`).
Response `201`: `PickupPointResponse`. Errors: `404`, `409`, `422`.

### `GET /routes/{route_id}/pickup-points` — any authenticated
Response `200`: array of `PickupPointResponse` ordered by `sequence`.

### `PATCH /routes/{route_id}/pickup-points/{point_id}` — CEO
Optional: `name`, `address`, `sequence`. Response `200`. Errors: `404`, `409`, `422`.

### `DELETE /routes/{route_id}/pickup-points/{point_id}` — CEO
Success: `204`. Errors: `404`; `409` when referenced by trip stops or bookings.

`PickupPointResponse`:

```json
{
  "id": 5,
  "route_id": 10,
  "name": "Al-Mahatta",
  "address": null,
  "sequence": 1,
  "created_at": "...",
  "updated_at": "..."
}
```

No latitude/longitude exists on pickup points.

---

## Trips

Every trip has exactly ONE direction (`OUTBOUND` ذهاب / `RETURN` عودة) and **no fare**. Trip times are DERIVED from the stops: `departure_time` = first stop's time, `estimated_arrival_time` = last stop's time.

`TripResponse`:

```json
{
  "id": 55,
  "route_id": 10,
  "direction": "OUTBOUND",
  "bus_id": 3,
  "supervisor_id": 7,
  "departure_time": "2026-09-20T06:30:00Z",
  "estimated_arrival_time": "2026-09-20T07:00:00Z",
  "status": "SCHEDULED",
  "passenger_capacity": 45,
  "allow_overbooking": false,
  "created_at": "...",
  "updated_at": "...",
  "route": { "...": "RouteResponse" },
  "bus": { "...": "BusResponse" },
  "supervisor": { "...": "UserResponse" },
  "trip_stops": [ { "...": "TripStopResponse" } ]
}
```

`TripStopResponse`:

```json
{
  "id": 1,
  "trip_id": 55,
  "pickup_point_id": 5,
  "stop_order": 1,
  "departure_time": "2026-09-20T06:30:00Z",
  "point_name": "Al-Mahatta",
  "address": null
}
```

### `POST /trips` — CEO
Request (`TripCreateRequest`):

```json
{
  "route_id": 10,
  "direction": "OUTBOUND",
  "bus_id": 3,
  "supervisor_id": 7,
  "passenger_capacity": 45,
  "allow_overbooking": false,
  "stops": [
    { "pickup_point_id": 5, "stop_order": 1, "departure_time": "2026-09-20T06:30:00Z" },
    { "pickup_point_id": 7, "stop_order": 2, "departure_time": "2026-09-20T07:00:00Z" }
  ]
}
```

- `route_id`, `direction`, `bus_id`, `supervisor_id`, `stops` required; `stops` needs at least one entry.
- Every `pickup_point_id` MUST belong to the trip's route (`422` otherwise).
- No duplicate points and no duplicate `stop_order` (`422`).
- `passenger_capacity` optional (defaults to bus capacity), > 0 ≤ 150.
- `allow_overbooking` optional (default `false`).
- Server validations: route active, bus `ACTIVE`, supervisor active SUPERVISOR, no schedule overlap for the same bus or supervisor (`409`).
- Response `201`: `TripResponse` (`status: "SCHEDULED"`).
- Errors: `404`, `409` (bus/supervisor conflict), `422`.

### `GET /trips` — CEO, SUPERVISOR
Query: `page`, `page_size`, `status`, `route_id`, `bus_id`, `supervisor_id`, `direction`, `departure_after`, `departure_before`.
Response `200`: `PaginatedTripResponse`.

### `GET /trips/history` — CEO, SUPERVISOR
Completed-trip history, RBAC-scoped: CEO sees all completed trips; a supervisor only those assigned to them. Query: `page`, `page_size`.

### `GET /trips/{trip_id}` — CEO, SUPERVISOR — `200` / `404`.

### `PATCH /trips/{trip_id}` — CEO
All optional: `bus_id`, `supervisor_id`, `passenger_capacity`, `allow_overbooking`. Re-validates bus/supervisor and re-checks schedule conflicts (excluding this trip). Response `200`. Errors: `404`, `409`, `422`.

### `PATCH /trips/{trip_id}/stops` — CEO
Replaces the trip's ordered stop sequence. Request body: `{ "stops": [ { "pickup_point_id": 5, "stop_order": 1, "departure_time": "..." }, ... ] }` — same validation rules as creation. Response `200`: `TripResponse`.

### `GET /trips/{trip_id}/stops` — CEO, SUPERVISOR
Response `200`: array of `TripStopResponse` ordered by `stop_order`.

### `PATCH /trips/{trip_id}/status` — CEO
Request: `{ "status": "IN_PROGRESS" }`. Valid transitions:

```
SCHEDULED  → IN_PROGRESS | CANCELLED
IN_PROGRESS → COMPLETED | CANCELLED
COMPLETED / CANCELLED → (terminal)
```

Response `200`. Errors: `422` (invalid transition).

### `DELETE /trips/{trip_id}` — CEO — `204`.

### `GET /trips/route-points/{route_id}` — CEO
Step 2 of trip creation: fetch a route's registered pickup points so the CEO can select, order, and time them. Response `200`: `RouteResponse` with `pickup_points`.

---

## Reservations — Daily Transportation

A reservation is **one directed booking**: one student + one trip (which has ONE direction) + one service date. Maximum one OUTBOUND and one RETURN booking per student per service date. See [RESERVATIONS.md](RESERVATIONS.md).

`ReservationResponse`:

```json
{
  "id": 41,
  "trip_id": 55,
  "student_id": 42,
  "subscription_id": 88,
  "service_date": "2026-09-20",
  "direction": "OUTBOUND",
  "selected_pickup_point_id": 5,
  "selected_pickup_point": { "...": "PickupPointResponse" },
  "status": "CONFIRMED",
  "booked_at": "2026-09-14T12:00:00Z",
  "cancelled_at": null,
  "created_at": "...",
  "updated_at": "...",
  "trip": { "...": "TripResponse" },
  "student": { "...": "UserResponse" },
  "origin": "Al-Mahatta",
  "destination": "Assiut National University"
}
```

Destination semantics (never stored on the trip/route):

| Direction | `origin` | `destination` |
|---|---|---|
| `OUTBOUND` | student's selected pickup point | **student's registered university** (per-student) |
| `RETURN` | student's university | **student's selected drop-off point** |

### `POST /reservations` — STUDENT with an ACTIVE subscription
Request (`ReservationCreateRequest`):

```json
{
  "trip_id": 55,
  "selected_pickup_point_id": 5,
  "service_date": "2026-09-20"
}
```

| Field | Required | Notes |
|---|---|---|
| `trip_id` | ✓ | must be a SCHEDULED trip |
| `selected_pickup_point_id` | ✓ | pickup point for OUTBOUND, drop-off point for RETURN; must be one of the trip's stops |
| `service_date` | optional | today or a future date within subscription validity; defaults to TOMORROW |

Server rules: direction is derived from the trip (client cannot choose it); ACTIVE subscription covering the service date required (`422` — PENDING is not usable); point must be one of the trip's stops (`422`); max one OUTBOUND + one RETURN per date (`409` on duplicate direction); capacity/`allow_overbooking` respected (`409` when FULL).
Response `201`: `ReservationResponse` (`status: "CONFIRMED"`).
Errors: `403` (non-student), `404`, `409`, `422`.

### `GET /reservations/upcoming-trips` — STUDENT
The student transportation screen (مواصلات الغد): **ALL upcoming SCHEDULED trips** (not only tomorrow). Query: `page`, `page_size`, `direction` (optional filter).

`StudentTripViewResponse`:

```json
{
  "trip_id": 55,
  "direction": "OUTBOUND",
  "route": { "...": "RouteResponse" },
  "origin": "Al-Mahatta",
  "destination": "Assiut National University",
  "selected_point_id": null,
  "estimated_arrival_time": "2026-09-20T07:00:00Z",
  "booking_state": "AVAILABLE",
  "departure_time": "2026-09-20T06:30:00Z",
  "status": "SCHEDULED",
  "passenger_capacity": 45,
  "confirmed_reservations_count": 12,
  "available_seats": 33,
  "bus": { "...": "BusResponse" },
  "stops": [ { "...": "TripStopResponse" } ],
  "pickup_points": [ { "...": "PickupPointResponse" } ]
}
```

`booking_state`: `AVAILABLE`, `BOOKED` (تم الحجز — the student already holds a booking), or `FULL` (تم الملئ — capacity reached with `allow_overbooking=false`). `BOOKED` wins over `FULL`.

On RETURN trips `destination` is `null` until the student books and selects a drop-off point.

### `GET /reservations/trips/{trip_id}` — STUDENT
One trip's details from the student's perspective (dynamic destination + booking state). Query: `service_date` (optional).

### `PUT /reservations/my/selection` — STUDENT
Replaces the student's existing booking in the SAME direction as the new trip for the resolved service date (same body as POST). Response `200`: `ReservationResponse`. Errors: `404`, `409`, `422`.

### `GET /reservations/my/selection` — STUDENT
The student's bookings for a date. Query: `service_date` (defaults to TOMORROW), `direction` (optional). Response `200`: array (up to two: one OUTBOUND + one RETURN).

### `GET /reservations/my/history` — STUDENT
Completed trips the student participated in (RBAC: own bookings only). Query: `page`, `page_size`. Response `200`: `PaginatedReservationResponse`.

### `GET /trips/history` — CEO, SUPERVISOR (see Trips section)
CEO: all completed trips; supervisor: assigned trips only.

### `GET /reservations/my` — STUDENT
Query: `page`, `page_size`, `status`, `direction`, `trip_id`, `service_date_from`, `service_date_to`. Response `200`: `PaginatedReservationResponse`.

### `GET /reservations` — CEO, SUPERVISOR
Query: `page`, `page_size`, `trip_id`, `student_id`, `direction`, `status`, `service_date_from`, `service_date_to`, `booked_after`, `booked_before`. Response `200`: `PaginatedReservationResponse`.

### `GET /reservations/{reservation_id}` — CEO, SUPERVISOR, owner student
Response `200` / `403` / `404`.

### `PATCH /reservations/{reservation_id}/cancel` — CEO, SUPERVISOR, owner student
Sets `status: "CANCELLED"`, stamps `cancelled_at`. Fails `422` if already cancelled.
Response `200`: `ReservationResponse`.

---

## Payments

Payments are created automatically with each subscription request. **Reservation/ticket payments are retired** — trips carry no fare; transportation is subscription-covered. See [PAYMENTS.md](PAYMENTS.md).

`PaymentResponse`:

```json
{
  "id": 301,
  "reservation_id": null,
  "subscription_id": 88,
  "student_id": 42,
  "amount": "750.00",
  "currency": "EGP",
  "method": "VODAFONE_CASH",
  "status": "SUBMITTED",
  "transaction_reference": "VC-123456789",
  "receipt_image_path": "uploads/payment_receipts/6f2a….png",
  "notes": null,
  "paid_at": "2026-09-10T12:05:00Z",
  "verified_at": null,
  "verified_by": null,
  "created_at": "...",
  "updated_at": "...",
  "subscription": { "...": "SubscriptionResponse or null" },
  "student": { "...": "UserResponse" },
  "verifier": { "...": "UserResponse or null" }
}
```

Payment lifecycle:

```
PENDING ──(receipt uploaded + reference set, digital)──► SUBMITTED ──(admin verify)──► VERIFIED
   │                                                        │
   └───────────────────── admin cancel ─────────────────────┴──► CANCELLED / REJECTED (terminal)
```

**Digital payment rule** (`VODAFONE_CASH`, `INSTAPAY`): BOTH the `transaction_reference` (payment code) AND a receipt image are REQUIRED before verification. Digital payments are born `PENDING` and advance to `SUBMITTED` when the receipt is uploaded. `CASH` needs no reference or receipt.

### `POST /payments` — STUDENT
**Retired**: always `422` — payments are created with subscriptions.

### `POST /payments/{payment_id}/receipt` — owner STUDENT
Multipart upload of the required receipt image (JPEG/PNG/WEBP, ≤ 5 MB):

```
image: (binary)
```

Response `201`:

```json
{ "payment_id": 301, "receipt_image_path": "uploads/payment_receipts/6f2a….png", "status": "SUBMITTED", "message": "Payment receipt uploaded successfully" }
```

Errors: `403` (not the owner / not a student), `404`, `422` (invalid file, CASH method, terminal status). The image is stored via the storage abstraction in the PRIVATE `payment-receipts` bucket (production) and never exposed publicly.

### `GET /payments/{payment_id}/receipt` — owner STUDENT, CEO, SUPERVISOR
Streams the stored receipt image through an authorized backend flow (access re-checked per request; never a public URL). Response `200`: image bytes. Errors: `401`, `403` (unrelated student), `404` (no receipt uploaded).

### `GET /payments/my` — STUDENT
Query: `page`, `page_size`, `status`, `method`, `subscription_id`. Response `200`: `PaginatedPaymentResponse`.

### `GET /payments` — CEO, SUPERVISOR
Query: `page`, `page_size`, `subscription_id`, `student_id`, `method`, `status`, `created_after`, `created_before`. Response `200`: `PaginatedPaymentResponse`.

### `GET /payments/{payment_id}` — CEO, SUPERVISOR, owner student
Response `200` / `403` / `404`.

### `PATCH /payments/{payment_id}/submit` — STUDENT (owner only)
Submit reference/notes. For digital methods a reference is required (`422`); a digital payment without a receipt stays `PENDING`. Response `200`: `PaymentResponse`.

### `PATCH /payments/{payment_id}/cancel` — CEO, SUPERVISOR, owner student
Response `200`. Errors: `422` (terminal status).

### `PATCH /payments/{payment_id}/verify` — CEO, SUPERVISOR
Digital methods: `422` unless reference + receipt are both present. On success sets `VERIFIED` and **activates the PENDING subscription** (or marks it `EXPIRED` if its end date passed). Response `200`.

### `PATCH /payments/{payment_id}/reject` — CEO, SUPERVISOR
Optional `{ "rejection_reason": "..." }`; appended to `notes`. Response `200`.

---

## Subscription Plans

`SubscriptionPlanResponse`:

```json
{
  "id": 5,
  "name": "Weekly Standard",
  "plan_type": "WEEKLY",
  "duration_days": 7,
  "days_per_week": 4,
  "price": "120.00",
  "currency": "EGP",
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

> `duration_days` is **CEO-defined** per plan (1–730). Only DAILY is fixed to exactly 1. `days_per_week` is the CEO-defined weekly usage-day allowance (1–7): the maximum DISTINCT usage DAYS per calendar week — NOT a QR-scan count. See [SUBSCRIPTIONS.md](SUBSCRIPTIONS.md) and [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

### `POST /subscription-plans` — CEO
Request:

```json
{ "name": "Weekly Standard", "plan_type": "WEEKLY", "duration_days": 7, "days_per_week": 4, "price": "120.00" }
```

- `name` 2–100 chars; `plan_type` enum; `duration_days` 1–730 (**DAILY must be exactly 1**); `days_per_week` 1–7 (required); `price` > 0 (2 decimals); `currency` optional (default EGP).
- Duplicate check: same (type, name, duration) → `409`.
- Response `201`: `SubscriptionPlanResponse` (`is_active: true`). Errors: `403`, `409`, `422`.

### `GET /subscription-plans` — 🔓 public
Query: `page`, `page_size`, `is_active` (CEO only — ignored/forced true for others).
Non-CEO callers always receive active plans only. Response `200`: `PaginatedSubscriptionPlanResponse`.

### `GET /subscription-plans/{plan_id}` — 🔓 public (no auth dependency)
Response `200`: `SubscriptionPlanResponse` (including inactive plans). Errors: `404`.

### `PATCH /subscription-plans/{plan_id}` — CEO
Optional: `name`, `price`, `duration_days` (1–730, DAILY stays 1), `days_per_week` (1–7), `is_active`. Editing these affects only FUTURE subscriptions — active subscriptions keep the values snapshotted at purchase. Response `200`. Errors: `403`, `404`, `422`.

### `PATCH /subscription-plans/{plan_id}/status` — CEO
Request: `{ "is_active": false }`. Response `200`.

---

## Subscriptions

A subscription is ONLY a plan purchase: `plan + start_date + payment_method (+ digital payment reference)`. **There is NO route, trip, or pickup-point selection in the subscription contract.** Daily transportation is chosen separately via [Reservations](#reservations--daily-transportation-selection).

`SubscriptionResponse` (base):

```json
{
  "id": 88,
  "student_id": 42,
  "plan_id": 5,
  "price_snapshot": "120.00",
  "currency": "EGP",
  "start_date": "2026-09-14",
  "end_date": "2026-09-20",
  "duration_days_snapshot": 7,
  "days_per_week_snapshot": 4,
  "payment_id": 400,
  "status": "PENDING",
  "created_at": "...",
  "updated_at": "...",
  "student": null,
  "plan": null,
  "payment": null
}
```

`SubscriptionDetailResponse` = base **plus**:

```json
{
  "plan_type": "WEEKLY",
  "price": "120.00",
  "payment_status": "SUBMITTED",
  "boarding_count": 4,
  "outbound_boarding_count": 2,
  "return_boarding_count": 2,
  "last_boarded_at": "2026-09-15T16:40:00Z",
  "duration_days": 7,
  "days_per_week": 4,
  "usage_days_this_week": 3,
  "remaining_usage_days_this_week": 1,
  "used_qr_usages": 4,
  "qr_usages_today": 1
}
```

> `usage_days_this_week` and `remaining_usage_days_this_week` are DAYS, not scans: one calendar day with outbound + return scans counts as ONE usage day (Mon–Sun, UTC week). `used_qr_usages` / `qr_usages_today` are raw scan counters.

`SubscriptionQRResponse`:

```json
{
  "subscription_id": 88,
  "plan_type": "WEEKLY",
  "valid_from": "2026-09-14",
  "valid_until": "2026-09-20",
  "qr_payload": "ra7al://subscription/<opaque-token>",
  "status": "ACTIVE"
}
```

### `GET /subscriptions/plans` — any authenticated
Convenience list of **active** plans (same shape as `SubscriptionPlanResponse`), **not paginated** — a plain array. Intended for the student plan-selection screen.

### `POST /subscriptions` — STUDENT
Purchase a plan. The ENTIRE request (`SubscriptionCreateRequest`):

```json
{
  "plan_id": 5,
  "start_date": "2026-09-14",
  "payment_method": "VODAFONE_CASH",
  "transaction_reference": "VC-123456789"
}
```

| Field | Required | Notes |
|---|---|---|
| `plan_id` | ✓ | must be an **active** plan |
| `start_date` | optional | defaults to today (UTC); cannot be in the past |
| `payment_method` | optional | `CASH` (default) \| `VODAFONE_CASH` \| `INSTAPAY` |
| `transaction_reference` | conditional | ≤ 100 chars; **REQUIRED for `VODAFONE_CASH`/`INSTAPAY`** (`422` if missing); tolerated-but-optional for `CASH` |

Server behavior:
- `end_date = start_date + plan.duration_days - 1` (inclusive).
- Plan `duration_days` and `days_per_week` are **snapshotted** onto the subscription (`*_snapshot` fields) — later CEO plan edits never change this subscription.
- Rejects any overlap with an existing PENDING/ACTIVE subscription for the student (`409`).
- Creates the subscription with `status: "PENDING"` and an auto-created payment record (plan price snapshot); digital methods start `SUBMITTED` (reference provided upfront), `CASH` starts `PENDING`.
- Generates the QR token server-side (opaque; hashed in DB).

Response `201`: `SubscriptionResponse`.
Errors: `403` (non-student), `404` (plan), `409` (overlapping subscription), `422` (inactive plan, past start date, missing digital reference).

### `GET /subscriptions/my` — STUDENT
Query: `page`, `page_size`, `status`. Response `200`: `PaginatedSubscriptionResponse` (items are `SubscriptionDetailResponse`).

### `GET /subscriptions` — CEO
Query: `page`, `page_size`, `student_id`, `university_id`, `route_id` (legacy rows only), `plan_type`, `status`, `start_date_from`, `start_date_to`, `end_date_from`, `end_date_to`. Response `200`: `PaginatedSubscriptionResponse`.

### `GET /subscriptions/{subscription_id}` — CEO / assigned supervisor / owner student
Response `200`: `SubscriptionDetailResponse` (with QR usage accounting). Auto-expires: if `end_date` has passed and status was ACTIVE, the response shows `EXPIRED`. Errors: `403`, `404`.

### `GET /subscriptions/{subscription_id}/qr` — owner student, subscription must be ACTIVE
Response `200`: `SubscriptionQRResponse`. Render `qr_payload` as a QR image.
Errors: `403` (not owner — CEO/supervisor also forbidden), `404`, `422` (subscription not ACTIVE / no token).

### `GET /subscriptions/{subscription_id}/history` — CEO / assigned supervisor / owner student
Query: `page`, `page_size` (default 50, ≤ 100).
Response `200`: **plain array** (not paginated envelope) of:

```json
{
  "id": 777,
  "subscription_id": 88,
  "trip_id": 55,
  "direction": "OUTBOUND",
  "pickup_point_id": 9,
  "pickup_point_name": "Cairo University Gate 3",
  "supervisor_id": 7,
  "supervisor_name": "Sara Supervisor",
  "boarded_at": "2026-09-15T07:35:00Z"
}
```

### `PATCH /subscriptions/{subscription_id}/renew` — owner student or CEO
Creates the next cycle from the same plan:
- New `start_date` = old `end_date + 1` (bumped to today if that's in the past).
- `duration_days` comes from the plan; new price snapshot from the plan's **current** price.
- Requires subscription `ACTIVE`/`EXPIRED` and an active plan; an ACTIVE subscription is expired first; renewal starts `PENDING` with a CASH payment.
- Response **`201`**: `SubscriptionResponse` (the new subscription).
- Errors: `403`, `404`, `409` (overlap), `422` (bad status / inactive plan).

### `PATCH /subscriptions/{subscription_id}/cancel` — owner student (PENDING only) or CEO
Students can cancel only `PENDING` subscriptions. CEO can cancel `PENDING`/`ACTIVE` (not terminal statuses).
Response `200`: `SubscriptionResponse` (`status: "CANCELLED"`). Errors: `403`, `404`, `422`.

---

## Boarding

`BoardingResponse` (successful scan):

```json
{
  "success": true,
  "message": "Boarding verified successfully",
  "student": {
    "id": 42,
    "full_name": "Ahmed Ali",
    "phone_number": "+201012345678",
    "faculty": "Faculty of Engineering",
    "academic_year": "3rd Year"
  },
  "subscription_id": 88,
  "route_id": 10,
  "direction": "OUTBOUND",
  "pickup_point_id": 9,
  "boarded_at": "2026-09-15T07:35:00Z",
  "usage_days_this_week": 3,
  "remaining_usage_days_this_week": 1
}
```

`SupervisorTripStudentResponse` (students who selected the trip for its service date):

```json
{
  "student_id": 42,
  "student_name": "Ahmed Ali",
  "subscription_id": 88,
  "subscription_status": "ACTIVE",
  "service_date": "2026-09-15",
  "direction": "OUTBOUND",
  "payment_status": "VERIFIED",
  "selected_point": "Al-Mahatta",
  "outbound_boarded": true,
  "return_boarded": false,
  "last_boarded_at": "2026-09-15T07:35:00Z"
}
```

`BoardingRecordResponse`:

```json
{
  "id": 777,
  "subscription_id": 88,
  "student_id": 42,
  "student_name": "Ahmed Ali",
  "trip_id": 55,
  "supervisor_id": 7,
  "supervisor_name": "Sara Supervisor",
  "direction": "OUTBOUND",
  "pickup_point_id": 9,
  "pickup_point_name": "Cairo University Gate 3",
  "boarded_at": "2026-09-15T07:35:00Z",
  "created_at": "..."
}
```

### `POST /boarding/scan` — SUPERVISOR assigned to the trip
Validates a student QR and records the boarding event. Rate limit: 60/min/IP.

Request (`BoardingScanRequest`):

```json
{
  "qr_token": "ra7al://subscription/<opaque-token>",
  "trip_id": 55,
  "direction": "OUTBOUND",
  "pickup_point_id": 9
}
```

- `qr_token` 1–512 chars. The `ra7al://subscription/` prefix is optional (the raw token also works).
- Trip must be `SCHEDULED` or `IN_PROGRESS` (`422` for CANCELLED/COMPLETED).
- Scanner must be the trip's assigned supervisor (`403`).
- Boarding is real-time: only on the trip's own service date (`422` otherwise).
- A confirmed DAILY reservation matching the student/subscription/trip/direction/pickup point is REQUIRED (`422` otherwise).
- Weekly rule: at most `days_per_week` DISTINCT usage days per week (Mon–Sun, UTC); outbound + return on the same day = ONE usage day; at most 2 scans per day; duplicates rejected `409`.
- Full validation order and all error states: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

Response `200`: `BoardingResponse`.

### `GET /boarding/trips/{trip_id}/students` — CEO or assigned supervisor
Students who selected this trip for the trip's service date, with per-trip attendance flags. Response `200`: array of `SupervisorTripStudentResponse`. Errors: `403`, `404`.

### `GET /boarding/trips/{trip_id}/records` — CEO or assigned supervisor
All boarding records for the trip. Response `200`: array of `BoardingRecordResponse`. Errors: `403`, `404`.

### `GET /boarding/records` — CEO
System-wide records. Query: `page`, `page_size`, `trip_id`, `student_id`, `supervisor_id`, `subscription_id`, `direction`, `boarded_after`, `boarded_before`.
Response `200`: `PaginatedBoardingRecordResponse`.
