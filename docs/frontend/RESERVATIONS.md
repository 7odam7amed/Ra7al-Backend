# Reservations / Daily Transportation (Post-Refactor)

Verified against `app/api/v1/reservations.py` and `app/services/reservation_service.py`.

A reservation is **one booking per direction**: each row books ONE trip (which has ONE direction) for ONE student on ONE service date.

```json
{
  "id": 41,
  "trip_id": 4,
  "student_id": 3,
  "subscription_id": 9,
  "service_date": "2026-09-20",
  "direction": "OUTBOUND",
  "selected_pickup_point_id": 5,
  "status": "CONFIRMED",
  "booked_at": "...",
  "cancelled_at": null
}
```

## 1. Rules

- Max **1 OUTBOUND + 1 RETURN** per student per service date (`OUTBOUND + OUTBOUND` → `409`).
- A CONFIRMED reservation can only be for a `SCHEDULED` trip.
- `selected_pickup_point_id`:
  - OUTBOUND → the student's **pickup point** (must be a stop of the booked trip).
  - RETURN → the student's **drop-off point** (must be a stop of the booked trip).
- Requires an ACTIVE subscription covering `service_date` (`422` otherwise).
- Direction is derived from the trip — the client cannot choose it.

## 2. Book a trip

`POST /api/v1/reservations` (Student only):

```json
{
  "trip_id": 123,
  "selected_pickup_point_id": 5
}
```

Response `201`:

```json
{
  "id": 41,
  "trip_id": 123,
  "direction": "OUTBOUND",
  "service_date": "2026-09-20",
  "selected_pickup_point_id": 5,
  "status": "CONFIRMED",
  "booking_state": "BOOKED",
  "origin": "Al-Mahatta",
  "destination": "Assiut National University",
  "estimated_arrival_time": "2026-09-20T07:00:00Z"
}
```

Destination behavior:

| Direction | `origin` | `destination` |
|---|---|---|
| `OUTBOUND` | student's selected pickup point | **student's registered university** (never a trip field) |
| `RETURN` | student's university | **student's selected drop-off point** |

## 3. Booking states (frontend)

| State | Meaning |
|---|---|
| `AVAILABLE` | Student may book this trip. |
| `BOOKED` | Student already holds a CONFIRMED booking for this trip/date+direction (تم الحجز). |
| `FULL` | Capacity reached and `allow_overbooking = false` (تم الملئ). |

`FULL` is never returned for a student who already booked (`BOOKED` wins).

## 4. Upcoming trips

`GET /api/v1/reservations/upcoming-trips` (Student only) returns ALL upcoming `SCHEDULED` trips (not only tomorrow) with direction, ordered stops, stop times, capacity, confirmed count, availability, booking state, and destination info per the rules above.

**Time-based expiration (backend-enforced):** a trip is "upcoming" only while its scheduled completion time has not passed. Completion is derived from the trip's schedule — the LAST stop's departure time (`estimated_arrival_time`), evaluated in UTC — NOT from boarding confirmation. Once that time has passed, the trip disappears from this endpoint even if the student never confirmed boarding. The Trip, Reservations, and Boarding records are preserved; history remains available via `/reservations/my` and `/my/history`.

## 5. Own bookings & history

- `GET /api/v1/reservations/my` — the student's bookings.
- `PATCH /api/v1/reservations/{id}/cancel` — student cancels own booking (`403` for others').
- `GET /api/v1/reservations/history` — completed trips, RBAC-scoped:
  - CEO → all completed trips,
  - supervisor → trips assigned to them,
  - student → trips they booked.

## 6. Errors

| Status | Meaning |
|---|---|
| `403` | Booking for another student, or non-student role. |
| `404` | Trip / point not found. |
| `409` | Second booking for the same date+direction; trip already booked; trip full. |
| `422` | No ACTIVE subscription covering the service date; point not a stop of the trip; trip not SCHEDULED; point belongs to another route. |
