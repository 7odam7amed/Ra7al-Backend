# Reservations

Seat booking on scheduled trips, verified against `app/api/v1/reservations.py`, `app/services/reservation_service.py`, and the `Reservation` model.

---

## 1. Reservation Model

```json
{
  "id": 101,
  "trip_id": 55,
  "student_id": 42,
  "status": "CONFIRMED",
  "booked_at": "2026-09-10T12:00:00Z",
  "cancelled_at": null,
  "created_at": "…",
  "updated_at": "…",
  "trip": { "…": "TripResponse" },
  "student": { "…": "UserResponse" }
}
```

| Field | Notes |
|---|---|
| `trip_id` | The scheduled trip. |
| `student_id` | Owner. |
| `status` | `CONFIRMED` or `CANCELLED` only. |
| `booked_at` / `cancelled_at` | Timestamps. |

## 2. Booking — `POST /api/v1/reservations` (STUDENT)

Request: `{ "trip_id": 55 }` — nothing else; the student is taken from the token.

Server rules (exact):

1. Student must exist, be active, role STUDENT (`403`/`422`/`404` otherwise).
2. Trip must exist and be `SCHEDULED` (`422` for IN_PROGRESS/COMPLETED/CANCELLED).
3. Departure must be in the future (`422` `"Trip has already departed"`).
4. **No duplicate:** the student must not already hold a CONFIRMED reservation on this trip (`409` `"Student already has an active confirmed reservation for this trip"`). This is DB-enforced by a partial unique index.
5. **Capacity:** confirmed reservations must be below `trip.passenger_capacity` (`409` `"No available seats for this trip"`). The trip row is locked during the check, so concurrent bookings cannot overbook.

Response `201` with `status: "CONFIRMED"`.

> **Overbooking is impossible** via the API — capacity is strictly enforced. There is no waitlist or overbooking behavior to document.

## 3. Browsing Bookable Trips — `GET /api/v1/reservations/available-trips`

Any authenticated role. Query: `page`, `page_size`, `route_id` (optional).

Returns future `SCHEDULED` trips with remaining capacity:

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

Use `available_seats` to render seat availability; hide/disable booking when `0` (the server would reject anyway).

### Pickup points in the response

Each item embeds the trip's `pickup_points` (array of `PickupPointResponse`, ordered by `sequence`, `[]` when the trip has none). **Students use these `id` values as `outbound_pickup_point_id` when purchasing a subscription** ([SUBSCRIPTIONS.md](SUBSCRIPTIONS.md)) — no privileged endpoint needed. At boarding time the scanned pickup point must match the student's configured point and belong to the scanned trip ([QR_AND_BOARDING.md](QR_AND_BOARDING.md)).

## 4. Cancellation — `PATCH /api/v1/reservations/{reservation_id}/cancel`

- Allowed: owner student, CEO, or any supervisor.
- Only non-cancelled reservations (`422` `"Reservation is already cancelled"`).
- Effect: `status → CANCELLED`, `cancelled_at` stamped. The seat is released (capacity is computed from CONFIRMED reservations only).

## 5. Listing

| Endpoint | Roles | Filters |
|---|---|---|
| `GET /reservations/my` | STUDENT | `page`, `page_size`, `status`, `trip_id` |
| `GET /reservations` | CEO, SUPERVISOR | `page`, `page_size`, `trip_id`, `student_id`, `status`, `booked_after`, `booked_before` |
| `GET /reservations/{id}` | CEO, SUPERVISOR, owner student | — |

## 6. Direction, Pickup Points & the Subscription Relationship

- A reservation has **no direction and no pickup point of its own**. It books a seat on one trip.
- Pickup points and outbound/return direction belong to the **subscription** (configured at purchase) and are validated at **boarding** time, not at reservation time.
- **Reservation state and boarding:** boarding scans validate the student's *subscription* (route, dates, status, usage allowance) and the *trip/direction/pickup* — a reservation is **not** required to board. Conversely, holding a CONFIRMED reservation on a trip using a bus is what grants a student access to that **bus image**. See [QR_AND_BOARDING.md](QR_AND_BOARDING.md) and [BUSES.md](BUSES.md).

## 7. Payments

A reservation can have at most one active payment (`PENDING`/`SUBMITTED`/`VERIFIED`). The payment amount comes from `trip.fare_amount`. Flow: [PAYMENTS.md](PAYMENTS.md).
