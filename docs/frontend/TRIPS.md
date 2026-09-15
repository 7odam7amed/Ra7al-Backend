# Trips & Trip Stops (Post-Refactor)

Verified against `app/api/v1/trips.py` and `app/services/trip_service.py`.

---

## 1. Trip model

Every trip has exactly **one direction**: `OUTBOUND` (ذهاب) or `RETURN` (عودة). There is **no fare/ticket price** on trips.

```json
{
  "id": 123,
  "route_id": 10,
  "direction": "OUTBOUND",
  "bus_id": 3,
  "supervisor_id": 7,
  "departure_time": "2026-09-20T06:30:00Z",
  "estimated_arrival_time": "2026-09-20T07:00:00Z",
  "status": "SCHEDULED",
  "passenger_capacity": 40,
  "allow_overbooking": false,
  "trip_stops": [
    { "id": 1, "trip_id": 123, "pickup_point_id": 5, "stop_order": 1, "departure_time": "2026-09-20T06:30:00Z", "point_name": "Al-Mahatta" },
    { "id": 2, "trip_id": 123, "pickup_point_id": 7, "stop_order": 2, "departure_time": "2026-09-20T07:00:00Z", "point_name": "Assiut El-Gadida" }
  ]
}
```

Key rules:

| Field | Rule |
|---|---|
| `direction` | `OUTBOUND` or `RETURN`, explicit at creation, immutable. |
| `departure_time` | **Derived**: equals the FIRST stop's `departure_time`. |
| `estimated_arrival_time` | **Derived**: equals the LAST stop's `departure_time`. |
| `trip_stops[].stop_order` | Explicit, unique per trip, > 0. |
| `trip_stops[].departure_time` | Required per stop on create/update. |
| `allow_overbooking` | Optional per-trip flag (default `false`). |
| `fare_amount` | **Removed.** Transportation is subscription-covered. |

## 2. CEO trip creation

`POST /api/v1/trips` (CEO only):

```json
{
  "route_id": 10,
  "direction": "OUTBOUND",
  "bus_id": 3,
  "supervisor_id": 7,
  "passenger_capacity": 40,
  "allow_overbooking": false,
  "stops": [
    { "pickup_point_id": 5, "stop_order": 1, "departure_time": "2026-09-20T06:30:00Z" },
    { "pickup_point_id": 7, "stop_order": 2, "departure_time": "2026-09-20T07:00:00Z" }
  ]
}
```

Validation (`422`):

- Every `pickup_point_id` MUST belong to the trip's route (`"… does not belong to route …"`).
- No duplicate points, no duplicate `stop_order`.
- Direction is required.
- Bus/supervisor must be active and eligible; bus/supervisor time-overlap conflicts return `409`.

## 3. Trip lifecycle & history

- `SCHEDULED → COMPLETED` when the scheduled end passes; completed trips leave the upcoming list but are never deleted.
- History endpoints (see RESERVATIONS.md):
  - CEO: all completed trips.
  - Supervisor: only trips assigned to them.
  - Student: only completed trips they booked.

## 4. Destination semantics (critical)

- **OUTBOUND**: the physical stop sequence ends at the last configured stop, but the destination shown to each student is **the student's registered university** (`current_student.university`). Two students on the same outbound trip can see different destinations.
- **RETURN**: the student's shown destination is **their selected drop-off point**; the last configured stop remains the physical end of the trip.

Never model destination as a Route or Trip field.
