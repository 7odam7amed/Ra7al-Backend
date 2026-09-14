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
| POST | `/routes` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| GET | `/routes` | 🔒 | any (students read-only) | [Routes](#routes) |
| GET | `/routes/{route_id}` | 🔒 | any (students read-only) | [Routes](#routes) |
| PATCH | `/routes/{route_id}` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| PATCH | `/routes/{route_id}/status` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| PATCH | `/routes/{route_id}/supervisor` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| DELETE | `/routes/{route_id}` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| GET | `/routes/{route_id}/stops` | 🔒 | any (students read-only) | [Routes](#routes) |
| POST | `/routes/{route_id}/stops` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| PATCH | `/routes/{route_id}/stops/reorder` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| PATCH | `/routes/{route_id}/stops/{route_stop_id}` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |
| DELETE | `/routes/{route_id}/stops/{route_stop_id}` | 🔒 | CEO, SUPERVISOR | [Routes](#routes) |

### Trips — `/api/v1/trips`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/trips` | 🔒 | CEO | [Trips](#trips) |
| GET | `/trips` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| GET | `/trips/{trip_id}` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| PATCH | `/trips/{trip_id}` | 🔒 | CEO | [Trips](#trips) |
| PATCH | `/trips/{trip_id}/status` | 🔒 | CEO | [Trips](#trips) |
| DELETE | `/trips/{trip_id}` | 🔒 | CEO | [Trips](#trips) |
| POST | `/trips/{trip_id}/pickup-points` | 🔒 | CEO | [Trips](#trips) |
| GET | `/trips/{trip_id}/pickup-points` | 🔒 | CEO, SUPERVISOR | [Trips](#trips) |
| PATCH | `/trips/{trip_id}/pickup-points/{point_id}` | 🔒 | CEO | [Trips](#trips) |
| DELETE | `/trips/{trip_id}/pickup-points/{point_id}` | 🔒 | CEO | [Trips](#trips) |

### Reservations — `/api/v1/reservations`
| Method | Path | Auth | Roles | Docs |
|---|---|---|---|---|
| POST | `/reservations` | 🔒 | STUDENT | [Reservations](#reservations) |
| GET | `/reservations/available-trips` | 🔒 | any | [Reservations](#reservations) |
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

`RouteResponse` (includes ordered stops and both stations):

```json
{
  "id": 10,
  "route_number": "R-101",
  "name": "Campus Express",
  "origin_station_id": 1,
  "destination_station_id": 2,
  "distance_km": 15.5,
  "estimated_duration_minutes": 35,
  "is_active": true,
  "supervisor_id": 7,
  "created_at": "...",
  "updated_at": "...",
  "origin_station": { "...": "StationResponse" },
  "destination_station": { "...": "StationResponse" },
  "stops": [ { "...": "RouteStopResponse" } ]
}
```

`RouteStopResponse`:

```json
{ "id": 21, "route_id": 10, "station_id": 4, "stop_order": 1, "created_at": "...", "station": { "...": "StationResponse" } }
```

### `POST /routes` — CEO, SUPERVISOR
Request:

```json
{
  "route_number": "R-101",
  "name": "Campus Express",
  "origin_station_id": 1,
  "destination_station_id": 2,
  "distance_km": 15.5,
  "estimated_duration_minutes": 35,
  "supervisor_id": 7
}
```

`route_number` stored uppercase and unique; origin ≠ destination; `supervisor_id` optional (must be an active SUPERVISOR). Response `201`. Errors: `404` (station/supervisor), `409` (duplicate route number), `422`.

### `GET /routes` — any authenticated (students read-only)
Query: `page`, `page_size`, `is_active`, `supervisor_id`, `search` (route number or name).
Response `200`: `PaginatedRouteResponse`.

### `GET /routes/{route_id}` — any authenticated
Response `200`: `RouteResponse` with `stops` ordered by `stop_order`. Errors: `404`.

### `PATCH /routes/{route_id}` — CEO, SUPERVISOR
Optional fields: `route_number`, `name`, `origin_station_id`, `destination_station_id`, `distance_km` (>0), `estimated_duration_minutes` (>0), `supervisor_id`. Response `200`. Errors: `404`, `409`, `422`.

### `PATCH /routes/{route_id}/status`
Request: `{ "is_active": false }`. Response `200`.

### `PATCH /routes/{route_id}/supervisor`
Request: `{ "supervisor_id": 7 }` or `{ "supervisor_id": null }` to unassign. Response `200`. Errors: `404`, `422` (not an active supervisor).

### `DELETE /routes/{route_id}`
Cascade-deletes intermediate stops. Success: `204`.

### `GET /routes/{route_id}/stops` — any authenticated
Response `200`: array of `RouteStopResponse` in order.

### `POST /routes/{route_id}/stops` — CEO, SUPERVISOR
Request: `{ "station_id": 4, "stop_order": 1 }` (both > 0).
Response `201`: `RouteStopResponse`. Errors: `404` (station/route), `409` (station already a stop, or stop_order occupied), `422`.

### `PATCH /routes/{route_id}/stops/reorder` — CEO, SUPERVISOR
Request:

```json
{ "stops": [ { "route_stop_id": 21, "stop_order": 2 }, { "route_stop_id": 22, "stop_order": 1 } ] }
```

All IDs must belong to the route; no duplicate IDs or orders. Response `200`: full reordered array of `RouteStopResponse`. Errors: `404`, `422`.

### `PATCH /routes/{route_id}/stops/{route_stop_id}` — CEO, SUPERVISOR
Request: `{ "stop_order": 3 }`. Response `200`: `RouteStopResponse`. Errors: `404`, `409` (order taken), `422`.

### `DELETE /routes/{route_id}/stops/{route_stop_id}`
Success: `204`. Errors: `404` (stop not on route).

---

## Trips

`TripResponse`:

```json
{
  "id": 55,
  "route_id": 10,
  "bus_id": 3,
  "supervisor_id": 7,
  "departure_time": "2026-09-15T07:30:00Z",
  "estimated_arrival_time": "2026-09-15T08:05:00Z",
  "status": "SCHEDULED",
  "passenger_capacity": 45,
  "fare_amount": "50.00",
  "created_at": "...",
  "updated_at": "...",
  "route": { "...": "RouteResponse" },
  "bus": { "...": "BusResponse" },
  "supervisor": { "...": "UserResponse" },
  "pickup_points": [ { "...": "PickupPointResponse" } ]
}
```

`PickupPointResponse`:

```json
{ "id": 9, "trip_id": 55, "name": "Cairo University Gate 3", "address": "Giza, University St.", "sequence": 1, "created_at": "...", "updated_at": "..." }
```

### `POST /trips` — CEO
Request (`TripCreateRequest`):

```json
{
  "route_id": 10,
  "bus_id": 3,
  "supervisor_id": 7,
  "departure_time": "2026-09-15T07:30:00Z",
  "estimated_arrival_time": "2026-09-15T08:05:00Z",
  "passenger_capacity": 45,
  "fare_amount": "50.00",
  "pickup_points": [
    { "name": "Cairo University Gate 3", "address": "Giza, University St.", "sequence": 1 }
  ]
}
```

- `route_id`, `bus_id`, `supervisor_id`, `departure_time`, `estimated_arrival_time` required; arrival must be strictly after departure.
- `passenger_capacity` optional (defaults to bus capacity), > 0 ≤ 150.
- `fare_amount` optional (default `50.00` EGP), > 0.
- `pickup_points` optional list created inline.
- Server validations: route active, bus `ACTIVE`, supervisor active SUPERVISOR, **no schedule overlap** for the same bus or supervisor (409).
- Response `201`: `TripResponse` (`status: "SCHEDULED"`).
- Errors: `404`, `409` (bus/supervisor schedule conflict), `422`.

### `GET /trips` — CEO, SUPERVISOR
Query: `page`, `page_size`, `status` (TripStatus), `route_id`, `bus_id`, `supervisor_id`, `departure_after`, `departure_before` (ISO datetimes).
Response `200`: `PaginatedTripResponse`.

### `GET /trips/{trip_id}` — CEO, SUPERVISOR — `200` / `404`.

### `PATCH /trips/{trip_id}` — CEO
All optional: `route_id`, `bus_id`, `supervisor_id`, `departure_time`, `estimated_arrival_time`, `passenger_capacity`, `fare_amount`. Re-validates bus/route/supervisor and re-checks schedule conflicts (excluding this trip).
Response `200`: `TripResponse`. Errors: `404`, `409`, `422`.

### `PATCH /trips/{trip_id}/status` — CEO
Request: `{ "status": "IN_PROGRESS" }`. Valid transitions:

```
SCHEDULED  → IN_PROGRESS | CANCELLED
IN_PROGRESS → COMPLETED | CANCELLED
COMPLETED / CANCELLED → (terminal)
```

Response `200`. Errors: `422` (invalid transition).

### `DELETE /trips/{trip_id}` — CEO — `204`.

### `POST /trips/{trip_id}/pickup-points` — CEO
Request: `{ "name": "Main Gate", "address": "Downtown Square", "sequence": 2 }` (name 1–255, sequence ≥ 1).
Response `201`: `PickupPointResponse`. Errors: `404`, `422`.

### `GET /trips/{trip_id}/pickup-points` — CEO, SUPERVISOR
Response `200`: array ordered by `sequence`.

### `PATCH /trips/{trip_id}/pickup-points/{point_id}` — CEO
Optional: `name`, `address`, `sequence`. Response `200`. Errors: `404`, `422`.

### `DELETE /trips/{trip_id}/pickup-points/{point_id}` — CEO — `204` / `404`.

---

## Reservations

`ReservationResponse`:

```json
{
  "id": 101,
  "trip_id": 55,
  "student_id": 42,
  "status": "CONFIRMED",
  "booked_at": "2026-09-10T12:00:00Z",
  "cancelled_at": null,
  "created_at": "...",
  "updated_at": "...",
  "trip": { "...": "TripResponse" },
  "student": { "...": "UserResponse" }
}
```

`AvailableTripResponse` (for booking screens):

```json
{
  "id": 55,
  "route_id": 10,
  "bus_id": 3,
  "supervisor_id": 7,
  "departure_time": "2026-09-15T07:30:00Z",
  "estimated_arrival_time": "2026-09-15T08:05:00Z",
  "status": "SCHEDULED",
  "passenger_capacity": 45,
  "confirmed_reservations_count": 12,
  "available_seats": 33,
  "fare_amount": "50.00",
  "created_at": "...",
  "updated_at": "...",
  "route": { "...": "RouteResponse" },
  "bus": { "...": "BusResponse" },
  "pickup_points": [
    { "id": 9, "trip_id": 55, "name": "Cairo University Gate 3", "address": "Giza, University St.", "sequence": 1, "created_at": "...", "updated_at": "..." },
    { "id": 12, "trip_id": 55, "name": "Main Gate", "address": null, "sequence": 2, "created_at": "...", "updated_at": "..." }
  ]
}
```

`pickup_points` lists the trip's gathering points ordered by `sequence` (empty list if the trip has none). Use these `id` values as `outbound_pickup_point_id` when purchasing a subscription.

### `POST /reservations` — STUDENT
Request: `{ "trip_id": 55 }`.
Server rules: trip must be `SCHEDULED`, departure in the future, no existing CONFIRMED reservation by this student on this trip (`409`), capacity available (`409` "No available seats").
Response `201`: `ReservationResponse` (`status: "CONFIRMED"`).
Errors: `403` (non-student), `404`, `409`, `422`.

### `GET /reservations/available-trips` — any authenticated
Query: `page`, `page_size`, `route_id` (optional).
Returns future `SCHEDULED` trips with `available_seats > 0`, each including the trip's ordered `pickup_points`. Response `200`: `PaginatedAvailableTripResponse`.

> Students obtain valid `outbound_pickup_point_id` values from `pickup_points` in this response — no privileged endpoint required.

### `GET /reservations/my` — STUDENT
Query: `page`, `page_size`, `status` (ReservationStatus), `trip_id`. Response `200`: `PaginatedReservationResponse`.

### `GET /reservations` — CEO, SUPERVISOR
Query: `page`, `page_size`, `trip_id`, `student_id`, `status`, `booked_after`, `booked_before`. Response `200`: `PaginatedReservationResponse`.

### `GET /reservations/{reservation_id}` — CEO, SUPERVISOR, owner student
Response `200` / `403` / `404`.

### `PATCH /reservations/{reservation_id}/cancel` — CEO, SUPERVISOR, owner student
Sets `status: "CANCELLED"`, stamps `cancelled_at`. Fails `422` if already cancelled.
Response `200`: `ReservationResponse`.

---

## Payments

`PaymentResponse`:

```json
{
  "id": 301,
  "reservation_id": 101,
  "subscription_id": null,
  "student_id": 42,
  "amount": "50.00",
  "currency": "EGP",
  "method": "VODAFONE_CASH",
  "status": "SUBMITTED",
  "transaction_reference": "VC-123456789",
  "notes": "Paid via Vodafone Cash number 01012345678",
  "paid_at": "2026-09-10T12:05:00Z",
  "verified_at": null,
  "verified_by": null,
  "created_at": "...",
  "updated_at": "...",
  "reservation": { "...": "ReservationResponse or null" },
  "student": { "...": "UserResponse" },
  "verifier": { "...": "UserResponse or null" }
}
```

Payment lifecycle:

```
PENDING → SUBMITTED → VERIFIED
   │           │
   │           └→ REJECTED / CANCELLED
   └→ VERIFIED | REJECTED | CANCELLED   (direct admin actions)
VERIFIED / REJECTED / CANCELLED = terminal
```

A payment targets **exactly one** of `reservation_id` or `subscription_id` (never both, never neither).

### `POST /payments` — STUDENT
Creates a payment attempt for the student's own **CONFIRMED** reservation whose trip has not departed.

Request:

```json
{ "reservation_id": 101, "method": "VODAFONE_CASH", "transaction_reference": "VC-123456789", "notes": "Paid via Vodafone Cash 01012345678" }
```

- `method` required (PaymentMethod). `transaction_reference`, `notes` optional (≤ 100 / ≤ 500 chars).
- Amount is server-derived from the trip `fare_amount`.
- If method is VODAFONE_CASH/INSTAPAY **and** a reference is provided → status starts at `SUBMITTED` (with `paid_at`); otherwise `PENDING`.
- Response `201`: `PaymentResponse`.
- Errors: `403` (other student's reservation / non-student), `404`, `409` (an active payment already exists for the reservation), `422` (reservation not CONFIRMED, trip departed).

### `GET /payments/my` — STUDENT
Query: `page`, `page_size`, `status`, `method`, `reservation_id`. Response `200`: `PaginatedPaymentResponse`.

### `GET /payments` — CEO, SUPERVISOR
Query: `page`, `page_size`, `reservation_id`, `student_id`, `method`, `status`, `created_after`, `created_before`. Response `200`: `PaginatedPaymentResponse`.

### `GET /payments/{payment_id}` — CEO, SUPERVISOR, owner student — `200` / `403` / `404`.

### `PATCH /payments/{payment_id}/submit` — owner STUDENT only

> The route enforces `STUDENT_ONLY` at the dependency level — CEO/SUPERVISOR receive `403` here, even though the service layer contains an admin branch. Only the **owner student** can submit payment proof.

Only from `PENDING`. Body optional (`PaymentSubmitRequest`): `transaction_reference` (≤100), `notes` (≤500).
For VODAFONE_CASH/INSTAPAY a reference is **required** (either new or previously stored) — otherwise `422`.
Response `200`: `PaymentResponse` (`status: "SUBMITTED"`, `paid_at` set).

### `PATCH /payments/{payment_id}/cancel` — CEO, SUPERVISOR, owner student
Only from `PENDING`/`SUBMITTED` (not terminal). No body. Response `200`: `PaymentResponse` (`status: "CANCELLED"`).

### `PATCH /payments/{payment_id}/verify` — CEO, SUPERVISOR
Only from `PENDING`/`SUBMITTED`. No body. Sets `status: "VERIFIED"`, `verified_at`, `verified_by`.
**Subscription side-effect:** if the payment targets a subscription, verifying it **activates** the subscription (`PENDING → ACTIVE`) when the end date has not passed. Response `200`: `PaymentResponse`.

### `PATCH /payments/{payment_id}/reject` — CEO, SUPERVISOR
Only from `PENDING`/`SUBMITTED`. Optional body:

```json
{ "rejection_reason": "Transaction reference not found in statement" }
```

Reason is appended to `notes`. Response `200`: `PaymentResponse` (`status: "REJECTED"`).

---

## Subscription Plans

`SubscriptionPlanResponse`:

```json
{
  "id": 5,
  "name": "Weekly Standard",
  "plan_type": "WEEKLY",
  "duration_days": 7,
  "price": "120.00",
  "currency": "EGP",
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

> `duration_days` is **CEO-defined** per plan (1–730). Only DAILY is fixed to exactly 1. See [SUBSCRIPTIONS.md](SUBSCRIPTIONS.md).

### `POST /subscription-plans` — CEO
Request:

```json
{ "name": "Weekly Standard", "plan_type": "WEEKLY", "duration_days": 7, "price": "120.00" }
```

- `name` 2–100 chars; `plan_type` enum; `duration_days` 1–730 (**DAILY must be exactly 1**); `price` > 0 (2 decimals); `currency` optional (default EGP).
- Duplicate check: same (type, name, duration) → `409`.
- Response `201`: `SubscriptionPlanResponse` (`is_active: true`). Errors: `403`, `409`, `422`.

### `GET /subscription-plans` — 🔓 public
Query: `page`, `page_size`, `is_active` (CEO only — ignored/forced true for others).
Non-CEO callers always receive active plans only. Response `200`: `PaginatedSubscriptionPlanResponse`.

### `GET /subscription-plans/{plan_id}` — 🔓 public (no auth dependency)
Response `200`: `SubscriptionPlanResponse` (including inactive plans). Errors: `404`.

### `PATCH /subscription-plans/{plan_id}` — CEO
Optional: `name`, `price`, `duration_days` (1–730, DAILY stays 1), `is_active`. Response `200`. Errors: `403`, `404`, `422`.

### `PATCH /subscription-plans/{plan_id}/status` — CEO
Request: `{ "is_active": false }`. Response `200`.

---

## Subscriptions

`SubscriptionResponse` (base):

```json
{
  "id": 88,
  "student_id": 42,
  "route_id": 10,
  "plan_id": 5,
  "price_snapshot": "120.00",
  "currency": "EGP",
  "start_date": "2026-09-14",
  "end_date": "2026-09-20",
  "outbound_pickup_point_id": 9,
  "return_pickup_point_id": 9,
  "return_pickup_mode": "SAME_AS_OUTBOUND",
  "payment_id": 400,
  "status": "PENDING",
  "created_at": "...",
  "updated_at": "...",
  "student": null,
  "route": null,
  "plan": null,
  "payment": null,
  "outbound_pickup_point": null,
  "return_pickup_point": null
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
  "max_qr_usages": 14,
  "used_qr_usages": 4,
  "remaining_qr_usages": 10,
  "qr_usages_today": 1
}
```

`SubscriptionQRResponse`:

```json
{
  "subscription_id": 88,
  "plan_type": "WEEKLY",
  "route_id": 10,
  "route_name": "Campus Express",
  "valid_from": "2026-09-14",
  "valid_until": "2026-09-20",
  "qr_payload": "ra7al://subscription/<opaque-token>",
  "status": "ACTIVE"
}
```

### `GET /subscriptions/plans` — any authenticated
Convenience list of **active** plans (same shape as `SubscriptionPlanResponse`), **not paginated** — a plain array. Intended for the student plan-selection screen.

### `POST /subscriptions` — STUDENT
Purchase a plan for a route. Request (`SubscriptionCreateRequest`):

```json
{
  "route_id": 10,
  "plan_id": 5,
  "start_date": "2026-09-14",
  "outbound_pickup_point_id": 9,
  "return_pickup_mode": "DIFFERENT",
  "return_pickup_point_id": 12,
  "payment_method": "VODAFONE_CASH",
  "transaction_reference": "VC-123456789"
}
```

| Field | Required | Notes |
|---|---|---|
| `route_id` | ✓ | must be an **active** route |
| `plan_id` | ✓ | must be an **active** plan |
| `start_date` | optional | defaults to today (UTC); cannot be in the past. `service_date` is an accepted alias; both must match if both sent |
| `outbound_pickup_point_id` | ✓ | pickup point must belong to the chosen route (points are per-trip). Get valid values from `pickup_points` in `GET /reservations/available-trips` for that route |
| `return_pickup_mode` | optional | `SAME_AS_OUTBOUND` (default) or `DIFFERENT` |
| `return_pickup_point_id` | conditional | required when mode = `DIFFERENT`; must belong to the route |
| `payment_method` | optional | default `CASH` |
| `transaction_reference` | optional | ≤ 100 chars; with a digital method → payment starts SUBMITTED |

Server behavior:
- `end_date = start_date + plan.duration_days - 1` (inclusive).
- Rejects overlap with an existing PENDING/ACTIVE subscription for the same student+route (`409`).
- Creates the subscription with `status: "PENDING"` and an auto-created payment record (plan price snapshot).
- Generates the QR token server-side (opaque; hashed in DB).

Response `201`: `SubscriptionResponse`.
Errors: `403` (non-student), `404` (route/plan/pickup point), `409` (overlapping subscription), `422`.

### `GET /subscriptions/my` — STUDENT
Query: `page`, `page_size`, `status`, `route_id`. Response `200`: `PaginatedSubscriptionResponse` (items are `SubscriptionDetailResponse`).

### `GET /subscriptions` — CEO
Query: `page`, `page_size`, `student_id`, `university_id`, `route_id`, `plan_type`, `status`, `start_date_from`, `start_date_to`, `end_date_from`, `end_date_to`. Response `200`: `PaginatedSubscriptionResponse`.

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
  "plan_type": "WEEKLY",
  "route_id": 10,
  "direction": "OUTBOUND",
  "pickup_point_id": 9,
  "boarded_at": "2026-09-15T07:35:00Z"
}
```

`SupervisorTripStudentResponse`:

```json
{
  "student_id": 42,
  "student_name": "Ahmed Ali",
  "subscription_id": 88,
  "subscription_type": "WEEKLY",
  "subscription_status": "ACTIVE",
  "start_date": "2026-09-14",
  "end_date": "2026-09-20",
  "payment_status": "VERIFIED",
  "outbound_pickup": "Cairo University Gate 3",
  "return_pickup": "Main Gate",
  "boarding_count": 4,
  "outbound_boarding_count": 2,
  "return_boarding_count": 2,
  "outbound_boarded": true,
  "return_boarded": false,
  "last_boarded_at": "2026-09-16T07:35:00Z"
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
- Full validation order and all error states: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

Response `200`: `BoardingResponse`.

### `GET /boarding/trips/{trip_id}/students` — CEO or assigned supervisor
Students subscribed to the trip's route with per-trip attendance flags. Response `200`: array of `SupervisorTripStudentResponse`. Errors: `403`, `404`.

### `GET /boarding/trips/{trip_id}/records` — CEO or assigned supervisor
All boarding records for the trip. Response `200`: array of `BoardingRecordResponse`. Errors: `403`, `404`.

### `GET /boarding/records` — CEO
System-wide records. Query: `page`, `page_size`, `trip_id`, `student_id`, `supervisor_id`, `subscription_id`, `direction`, `boarded_after`, `boarded_before`.
Response `200`: `PaginatedBoardingRecordResponse`.
