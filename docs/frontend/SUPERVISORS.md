# Supervisors

Supervisor creation, assignment, and operational access, verified against `app/api/v1/users.py`, `app/api/v1/boarding.py`, and the relevant services.

---

## 1. Supervisor Accounts

- Created **only by the CEO**: `POST /api/v1/users/supervisors` with `{ full_name, phone_number, password, gender }`.
- Created directly as `role: "SUPERVISOR"`, `status: "APPROVED"`, `is_active: true` — **no approval flow**, they can log in immediately.
- There is no supervisor self-registration. The role can also be granted/removed by the CEO via `PATCH /users/{user_id}/role` (only `STUDENT` ↔ `SUPERVISOR` transitions are allowed; the last active CEO cannot be demoted).
- Deactivation/rejection: same status mechanics as any user ([USERS.md](USERS.md)). An inactive supervisor cannot be assigned to trips or routes.

## 2. Assignments

Supervisors are assigned in **two independent places**:

| Assignment | Endpoint | Effect |
|---|---|---|
| **Route supervisor** | `PATCH /routes/{route_id}/supervisor` | Organizational/display info on `RouteResponse.supervisor_id`. Does **not** grant boarding permissions. |
| **Trip supervisor** | `trip.supervisor_id` (set at `POST /trips`, changeable via `PATCH /trips/{trip_id}`) | **The operational assignment**: authorizes QR scanning, trip rosters, and trip boarding records. |

A supervisor may be assigned to many trips, subject to the schedule-conflict rule (no overlapping trip windows per supervisor → `409`).

## 3. Supervisor-Accessible Data

| Capability | Endpoint(s) | Condition |
|---|---|---|
| List/get buses | `GET /buses`, `GET /buses/{id}` | Any supervisor |
| View bus image | `GET /buses/{id}/image` | Only for buses used by a trip **assigned to them** |
| List/get routes, stops | `GET /routes…` | Read + management (CEO/SUPERVISOR shared) |
| List/get trips | `GET /trips…` | Any supervisor (all trips visible in listings) |
| Trip pickup points (read) | `GET /trips/{id}/pickup-points` | Any supervisor |
| Trip roster | `GET /boarding/trips/{trip_id}/students` | Assigned supervisor (or CEO) |
| Trip boarding records | `GET /boarding/trips/{trip_id}/records` | Assigned supervisor (or CEO) |
| **Scan QR / record boarding** | `POST /boarding/scan` | Assigned supervisor only |
| Subscription details/history | `GET /subscriptions/{id}…` | Only if assigned to a trip on the subscription's route |
| Reservations & payments listings | `GET /reservations`, `GET /payments` | All records visible; cancel/verify/reject actions allowed (payment **submit** is owner-student-only) |
| Plans & universities | `GET /subscription-plans`, `GET /universities` | Read (plans list shows active only for non-CEO) |

**Not accessible to supervisors:** user management, student ID cards, creating trips/buses/stations? (stations they *can* manage), creating trips/buses/plans/pickup points, deleting trips, subscription create/cancel/renew, QR credential fetch, system-wide boarding records (`GET /boarding/records` → CEO only).

## 4. QR / Boarding Permissions

The scan endpoint (`POST /api/v1/boarding/scan`) enforces, in order:

1. Role must be `SUPERVISOR` (CEO gets 403 — scans are supervisor-only).
2. `trip_id` must exist and be `SCHEDULED`/`IN_PROGRESS` (not `CANCELLED`/`COMPLETED`).
3. **`trip.supervisor_id` must equal the scanner's ID** → otherwise `403 "You are not assigned as the supervisor for this trip"`.
4. Then all student/subscription/QR validations run — full list in [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

Rate limit: 60 scans/min/IP.

## 5. Suggested Supervisor Workflow (frontend)

```
Login → GET /auth/me (role SUPERVISOR)
   ↓
GET /trips?supervisor_id=<me>&status=SCHEDULED   (today's assignments)
   ↓
For a trip:
  GET /boarding/trips/{trip_id}/students  → roster with outbound_boarded / return_boarded flags
  GET /trips/{trip_id}/pickup-points      → pickup list for the scan form
   ↓
Scan student QR → POST /boarding/scan { qr_token, trip_id, direction, pickup_point_id }
   ↓
BoardingResponse (success) → update roster flags
   ↓
End of day: PATCH /trips/{trip_id}/status is CEO-only — supervisor cannot advance status.
```
