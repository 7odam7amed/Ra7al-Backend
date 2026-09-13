# Roles & RBAC (Role-Based Access Control)

Verified against `app/api/deps.py` (`require_roles` factory and the `CEO_ONLY`, `SUPERVISOR_ONLY`, `STUDENT_ONLY`, `CEO_OR_SUPERVISOR`, `ANY_AUTHENTICATED_ROLE` dependencies) and per-service authorization checks.

---

## 1. Roles

Exact enum (`RoleEnum`): `CEO`, `SUPERVISOR`, `STUDENT`. There are no other roles.

Every authenticated request resolves the user from the database; the role is checked server-side on each endpoint. Role-based failures return:

```
403 { "detail": "Access denied: current role 'STUDENT' lacks required role (CEO)" }
```

## 2. Dependency Categories

| Dependency | Allows |
|---|---|
| `get_current_user` | Any **approved + active** authenticated user (any role) |
| `CEO_ONLY` | CEO |
| `SUPERVISOR_ONLY` | SUPERVISOR |
| `STUDENT_ONLY` | STUDENT |
| `CEO_OR_SUPERVISOR` | CEO, SUPERVISOR |
| `ANY_AUTHENTICATED_ROLE` | CEO, SUPERVISOR, STUDENT (read-only endpoints only) |

## 3. Permissions Matrix

Legend: ✓ allowed, ✗ forbidden, ◐ allowed with relationship/ownership condition (see §4).

### Auth & Users

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `POST /auth/upload-id-card` | ✓ (public) | ✓ (public) | ✓ (public) |
| `POST /auth/register` | ✓ (public) | ✓ (public) | ✓ (public) |
| `POST /auth/login` | ✓ (public) | ✓ (public) | ✓ (public) |
| `GET /auth/me` | ✓ | ✓ | ✓ |
| `GET /users` (list/filter) | ✓ | ✗ | ✗ |
| `GET /users/pending` | ✓ | ✗ | ✗ |
| `POST /users/supervisors` | ✓ | ✗ | ✗ |
| `GET /users/{user_id}` | ✓ | ✗ | ✗ |
| `GET /users/{user_id}/id-card` | ✓ | ✗ | ◐ own card only |
| `GET /users/{user_id}/id-card/signed-url` | ✓ | ✗ | ◐ own card only |
| `PATCH /users/{user_id}` | ✓ | ✗ | ✗ |
| `PATCH /users/{user_id}/role` | ✓ (not own role; only STUDENT↔SUPERVISOR) | ✗ | ✗ |
| `PATCH /users/{user_id}/status` | ✓ (cannot deactivate last active CEO) | ✗ | ✗ |
| `PATCH /users/{user_id}/approve` | ✓ (not own account) | ✗ | ✗ |
| `PATCH /users/{user_id}/reject` | ✓ (not own account) | ✗ | ✗ |

### Universities, Stations, Buses

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `GET /universities` (list), `GET /universities/{id}` | ✓ | ✓ | ✓ (list & get are actually public — no auth required) |
| `POST/PATCH/DELETE /universities...` | ✓ | ✗ | ✗ |
| All `/stations` endpoints (CRUD + status) | ✓ | ✓ | ✗ |
| `POST /buses` (create, optional image) | ✓ | ✗ | ✗ |
| `GET /buses` (list), `GET /buses/{id}` | ✓ | ✓ | ✗ |
| `PATCH /buses/{id}`, `PATCH /buses/{id}/status` | ✓ | ✗ | ✗ |
| `DELETE /buses/{id}` | ✓ | ✗ | ✗ |
| `GET /buses/{bus_id}/image` | ✓ (any bus) | ◐ assigned to bus via a trip | ◐ has CONFIRMED reservation on a trip using this bus |
| `GET /buses/{bus_id}/image/metadata` | ✓ | ◐ same as above | ◐ same as above |
| `PATCH /buses/{bus_id}/image` (replace) | ✓ | ✗ | ✗ |
| `DELETE /buses/{bus_id}/image` (remove) | ✓ | ✗ | ✗ |

### Routes, Trips

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `POST /routes` | ✓ | ✓ | ✗ |
| `GET /routes` (list) | ✓ | ✓ | ✓ (read-only) |
| `GET /routes/{id}` | ✓ | ✓ | ✓ (read-only) |
| `GET /routes/{id}/stops` | ✓ | ✓ | ✓ (read-only) |
| `PATCH /routes/{id}`, `PATCH /routes/{id}/status`, `PATCH /routes/{id}/supervisor` | ✓ | ✓ | ✗ |
| `DELETE /routes/{id}` | ✓ | ✓ | ✗ |
| `POST /routes/{id}/stops`, `PATCH /routes/{id}/stops/reorder`, `PATCH /routes/{id}/stops/{stop_id}`, `DELETE /routes/{id}/stops/{stop_id}` | ✓ | ✓ | ✗ |
| `POST /trips` (create) | ✓ | ✗ | ✗ |
| `GET /trips`, `GET /trips/{id}` | ✓ | ✓ | ✗ |
| `PATCH /trips/{id}`, `PATCH /trips/{id}/status`, `DELETE /trips/{id}` | ✓ | ✗ | ✗ |
| `POST /trips/{id}/pickup-points` | ✓ | ✗ | ✗ |
| `GET /trips/{id}/pickup-points` | ✓ | ✓ | ✗ |
| `PATCH/DELETE /trips/{id}/pickup-points/{point_id}` | ✓ | ✗ | ✗ |

> Route **management** is available to both CEO and Supervisor; students get read-only route access (needed for the subscription purchase flow).

### Subscriptions & Plans

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `GET /subscriptions/plans` (active plans) | ✓ | ✓ | ✓ |
| `POST /subscriptions` (purchase) | ✗ | ✗ | ✓ |
| `GET /subscriptions/my` | ✗ | ✗ | ✓ |
| `GET /subscriptions` (all, filtered) | ✓ | ✗ | ✗ |
| `GET /subscriptions/{id}` (detail) | ✓ | ◐ supervisor assigned to a trip on the subscription's route | ◐ own subscription |
| `GET /subscriptions/{id}/qr` | ✗ | ✗ | ◐ own subscription (must be ACTIVE) |
| `GET /subscriptions/{id}/history` | ✓ | ◐ assigned to route | ◐ own subscription |
| `PATCH /subscriptions/{id}/renew` | ✓ | ✗ | ◐ own subscription (ACTIVE or EXPIRED) |
| `PATCH /subscriptions/{id}/cancel` | ✓ | ✗ | ◐ own subscription, **PENDING only** |
| `POST /subscription-plans` (create) | ✓ | ✗ | ✗ |
| `GET /subscription-plans` (list) | ✓ | ✓ (active only) | ✓ (active only) — endpoint is actually public |
| `GET /subscription-plans/{id}` | ✓ | ✓ | ✓ (endpoint is actually public — no auth required) |
| `PATCH /subscription-plans/{id}`, `PATCH /subscription-plans/{id}/status` | ✓ | ✗ | ✗ |

### Reservations & Payments

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `POST /reservations` (book seat) | ✗ | ✗ | ✓ |
| `GET /reservations/available-trips` | ✓ | ✓ | ✓ |
| `GET /reservations/my` | ✗ | ✗ | ✓ |
| `GET /reservations` (all, filtered) | ✓ | ✓ | ✗ |
| `GET /reservations/{id}` | ✓ | ✓ | ◐ own reservation |
| `PATCH /reservations/{id}/cancel` | ✓ | ✓ | ◐ own reservation |
| `POST /payments` (create attempt) | ✗ | ✗ | ✓ |
| `GET /payments/my` | ✗ | ✗ | ✓ |
| `GET /payments` (all, filtered) | ✓ | ✓ | ✗ |
| `GET /payments/{id}` | ✓ | ✓ | ◐ own payment |
| `PATCH /payments/{id}/submit` | ✗ | ✗ | ◐ own payment (PENDING only) — STUDENT-only route |
| `PATCH /payments/{id}/cancel` | ✓ | ✓ | ◐ own payment (non-terminal) |
| `PATCH /payments/{id}/verify` | ✓ | ✓ | ✗ |
| `PATCH /payments/{id}/reject` | ✓ | ✓ | ✗ |

### Boarding / QR

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `POST /boarding/scan` | ✗ | ◐ must be the supervisor assigned to the trip | ✗ |
| `GET /boarding/trips/{trip_id}/students` | ✓ | ◐ assigned to the trip | ✗ |
| `GET /boarding/trips/{trip_id}/records` | ✓ | ◐ assigned to the trip | ✗ |
| `GET /boarding/records` (system-wide) | ✓ | ✗ | ✗ |

## 4. Relationship-Based (Ownership) Rules

Role alone is not always sufficient; the service layer additionally enforces:

| Rule | Detail |
|---|---|
| **Bus image — supervisor** | Allowed only if the supervisor is assigned to at least one **trip** that uses this bus (`trip.supervisor_id == current_user.id`). |
| **Bus image — student** | Allowed only if the student holds a **CONFIRMED reservation** on a trip that uses this bus. |
| **ID card** | Students can access only their own; supervisors never; CEO any. |
| **Subscription detail/history** | Student = owner only; Supervisor = must be assigned to a trip on the subscription's route; CEO = any. |
| **Subscription QR** | Owner student only, and only while status is `ACTIVE`. |
| **Subscription cancel** | Owner student only while `PENDING`; CEO any non-terminal. |
| **Subscription renew** | Owner student or CEO; requires `ACTIVE`/`EXPIRED` status and an active plan. |
| **Boarding scan** | Supervisor only, and `trip.supervisor_id` must equal the scanner's user ID; trip must be `SCHEDULED` or `IN_PROGRESS`. |
| **Trip students / trip boarding records** | CEO any trip; supervisor only trips assigned to them. |
| **Reservations / payments** | Students operate only on their own records; CEO/SUPERVISOR can act on all. |
| **User role/status/approve/reject** | CEO cannot target themselves; last active CEO cannot be demoted or deactivated; only STUDENT↔SUPERVISOR role changes are permitted via the API. |

## 5. Frontend Handling of `403`

`403` means the account is authenticated but not permitted. Display the `detail` message where useful (e.g. `"You are not assigned as the supervisor for this trip"`), and hide UI actions the role cannot perform rather than relying on errors. Distinguish from `401` (not authenticated — re-login). See [ERRORS.md](ERRORS.md).
