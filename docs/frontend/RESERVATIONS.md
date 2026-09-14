# Reservations — Daily Transportation Selection

The DAILY selection workflow, verified against `app/api/v1/reservations.py`, `app/services/reservation_service.py`, the `Reservation` model, and `app/utils/dates.py`.

> **CORE CONCEPT (v2 contract):** A reservation is the student's DAILY transportation choice: **trip + outbound pickup point + return pickup point for TOMORROW**. It requires an ACTIVE subscription but is otherwise independent of it — the subscription answers "which plan did the student buy?", the reservation answers "how does the student travel on a given day?".

---

## 1. Reservation Model

```json
{
  "id": 101,
  "trip_id": 55,
  "student_id": 42,
  "subscription_id": 88,
  "service_date": "2026-09-15",
  "outbound_pickup_point_id": 9,
  "return_pickup_point_id": 12,
  "direction_mode": "BOTH",
  "status": "CONFIRMED",
  "booked_at": "2026-09-14T12:00:00Z",
  "cancelled_at": null,
  "created_at": "…",
  "updated_at": "…",
  "trip": { "…": "TripResponse" },
  "student": { "…": "UserResponse" },
  "outbound_pickup_point": { "…": "PickupPointResponse" },
  "return_pickup_point": { "…": "PickupPointResponse" }
}
```

| Field | Notes |
|---|---|
| `trip_id` | The scheduled trip departing on `service_date`. |
| `student_id` | Owner (derived from the JWT, never from the request). |
| `subscription_id` | The ACTIVE subscription authorizing this selection. |
| `service_date` | The calendar transportation date — always TOMORROW for API-created selections. |
| `outbound_pickup_point_id` / `return_pickup_point_id` | Selected gathering points; belong to the trip. Null only for one-way `direction_mode`s. |
| `direction_mode` | `BOTH`, `OUTBOUND_ONLY`, or `RETURN_ONLY`. |
| `status` | `CONFIRMED` or `CANCELLED` only. |

## 2. Creating Tomorrow's Selection — `POST /api/v1/reservations` (STUDENT)

```json
{
  "trip_id": 55,
  "outbound_pickup_point_id": 9,
  "return_pickup_point_id": 12,
  "direction_mode": "BOTH"
}
```

- `direction_mode` defaults to `BOTH`, which **requires both** pickup point IDs (`422` otherwise). `OUTBOUND_ONLY` requires `outbound_pickup_point_id`; `RETURN_ONLY` requires `return_pickup_point_id`.
- There is **no `date` field**: the service date is derived server-side as TOMORROW (Today → Tomorrow window). Clients cannot select today, past dates, or arbitrary future dates.

Server rules (exact, in order):

1. Student must exist, be active, role STUDENT (`403`/`422`/`404` otherwise).
2. **An ACTIVE subscription covering the service date is mandatory** (`422` "An ACTIVE subscription covering the service date is required…"). PENDING is not usable — payment must be verified first.
3. Trip must exist (`404`), be `SCHEDULED` (`422` otherwise), and depart on the service date (tomorrow) (`422` "Selected trip does not operate on the requested service date").
4. **Pickup-point validation (server-side, never trusted):** each supplied point must belong to the selected trip — and therefore to the trip's route (`422` "…does not belong to trip X"). A pickup point from another route is ALWAYS rejected.
5. **No duplicate day selection:** the student must not already hold a CONFIRMED reservation for the service date (`409` "Student already has an active daily selection for the requested date; cancel it before creating a new one"). DB-enforced by a partial unique index on (student, service_date) where status = CONFIRMED.
6. **Capacity:** confirmed reservations must be below `trip.passenger_capacity` (`409` "No available seats for this trip"). The trip row is locked during the check, so concurrent bookings cannot overbook.

Response `201` with `status: "CONFIRMED"` and `service_date` = tomorrow.

## 3. Updating & Fetching Tomorrow's Selection

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/reservations/my/tomorrow` | `GET` | Fetch the student's selection for tomorrow (`404` if none). |
| `/api/v1/reservations/my/tomorrow` | `PUT` | Replace tomorrow's selection in place (same body as POST). Validates trip/pickups/capacity again; `404` if no existing selection. |
| `/api/v1/reservations/my` | `GET` | Paginated history of the student's selections. |

## 4. Browsing Selectable Trips — `GET /api/v1/reservations/available-trips`

Any authenticated role. Query: `page`, `page_size`, `route_id` (optional).

Returns trips departing **tomorrow** with remaining capacity:

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
  "created_at": "…",
  "updated_at": "…",
  "route": { "…": "RouteResponse" },
  "bus": { "…": "BusResponse" },
  "pickup_points": [
    { "id": 9, "trip_id": 55, "name": "Cairo University Gate 3", "address": "Giza, University St.", "sequence": 1, "created_at": "…", "updated_at": "…" },
    { "id": 12, "trip_id": 55, "name": "Main Gate", "address": null, "sequence": 2, "created_at": "…", "updated_at": "…" }
  ]
}
```

### FLOW B (daily transportation) — recommended UI sequence

1. Student must already hold an ACTIVE subscription (check via `GET /subscriptions/my`).
2. `GET /reservations/available-trips` → render tomorrow's trips with `available_seats`.
3. Student picks a trip → use that trip's embedded `pickup_points` to render the outbound and return point pickers (ordered by `sequence`).
4. Student picks outbound + return pickup point → `POST /reservations` (or `PUT /reservations/my/tomorrow` to change an existing selection).
5. On the travel day the supervisor scans the student's QR ([QR_AND_BOARDING.md](QR_AND_BOARDING.md)) — boarding REQUIRES this selection to exist and to match the scanned trip/point.

Use `available_seats` to render seat availability; hide/disable booking when `0` (the server would reject anyway).

## 5. Cancellation — `PATCH /api/v1/reservations/{reservation_id}/cancel`

- Allowed: owner student, CEO, or any supervisor.
- Only non-cancelled reservations (`422` `"Reservation is already cancelled"`).
- Effect: `status → CANCELLED`, `cancelled_at` stamped. The seat is released (capacity is computed from CONFIRMED reservations only) and the student may create a new selection for the same date.

## 6. Listing

| Endpoint | Roles | Filters |
|---|---|---|
| `GET /reservations/my` | STUDENT | `page`, `page_size`, `status`, `trip_id`, `service_date_from`, `service_date_to` |
| `GET /reservations` | CEO, SUPERVISOR | `page`, `page_size`, `trip_id`, `student_id`, `status`, `service_date_from`, `service_date_to`, `booked_after`, `booked_before` |
| `GET /reservations/{id}` | CEO, SUPERVISOR, owner student | — |

## 7. Relationship to Subscription & Boarding

- **A reservation does NOT modify the subscription.** Creating/updating/cancelling a selection never changes plan, dates, snapshots, or status of the subscription.
- **Boarding REQUIRES a reservation:** a QR scan is only valid if a CONFIRMED selection exists for the trip's service date, belongs to the scanned student's subscription, covers the scan direction, and names the scanned pickup point. See [QR_AND_BOARDING.md](QR_AND_BOARDING.md).
- One usage DAY allows one outbound scan + one return scan; together they count as ONE weekly usage day (see the weekly rule in [QR_AND_BOARDING.md](QR_AND_BOARDING.md)).
- Holding a CONFIRMED reservation on a trip using a bus grants the student access to that **bus image** ([BUSES.md](BUSES.md)).

## 8. Payments

A reservation can have at most one active payment (`PENDING`/`SUBMITTED`/`VERIFIED`). The payment amount comes from `trip.fare_amount`. Flow: [PAYMENTS.md](PAYMENTS.md).
