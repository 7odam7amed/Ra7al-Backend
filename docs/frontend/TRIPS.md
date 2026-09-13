# Trips & Pickup (Gathering) Points

Verified against `app/api/v1/trips.py`, `app/services/trip_service.py`, and `app/services/pickup_point_service.py`.

---

## 1. Trip Model

A trip is one scheduled execution of a route with a specific bus and supervisor.

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
  "route": { "…": "RouteResponse" },
  "bus": { "…": "BusResponse" },
  "supervisor": { "…": "UserResponse" },
  "pickup_points": [ { "…": "PickupPointResponse" } ]
}
```

| Field | Notes |
|---|---|
| `route_id` / `route` | The route being executed. |
| `bus_id` / `bus` | Vehicle; must be `ACTIVE` at creation. |
| `supervisor_id` / `supervisor` | Required; must be an active SUPERVISOR. This assignment is what authorizes the supervisor to scan QR codes for the trip. |
| `departure_time` / `estimated_arrival_time` | Timezone-aware datetimes; arrival strictly after departure. |
| `status` | `TripStatus` — see lifecycle below. |
| `passenger_capacity` | Optional override at creation; defaults to the bus capacity. 1–150. Reservation capacity is checked against this value. |
| `fare_amount` | EGP, default `50.00`, > 0. Used as the amount for reservation payments. |

> The API models **single scheduled departures**, not recurring schedules or separate "going/return trip types". An outbound journey and a return journey are simply two trips. The outbound/return distinction exists at **boarding** level (`BoardingDirection` on the scan) — see [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

## 2. Status Lifecycle

```
SCHEDULED ──→ IN_PROGRESS ──→ COMPLETED
    │              │
    └──────────────┴──→ CANCELLED
```

- Transitions via `PATCH /trips/{trip_id}/status` (CEO). Invalid transitions → `422`.
- `COMPLETED` and `CANCELLED` are terminal.
- Only `SCHEDULED` trips accept reservations; `SCHEDULED` and `IN_PROGRESS` accept boarding scans.
- Setting the same status again is a no-op success.

## 3. Endpoints & Roles

| Endpoint | Roles |
|---|---|
| `POST /trips` | CEO |
| `GET /trips` | CEO, SUPERVISOR |
| `GET /trips/{trip_id}` | CEO, SUPERVISOR |
| `PATCH /trips/{trip_id}` | CEO |
| `PATCH /trips/{trip_id}/status` | CEO |
| `DELETE /trips/{trip_id}` | CEO |
| `POST /trips/{trip_id}/pickup-points` | CEO |
| `GET /trips/{trip_id}/pickup-points` | CEO, SUPERVISOR |
| `PATCH /trips/{trip_id}/pickup-points/{point_id}` | CEO |
| `DELETE /trips/{trip_id}/pickup-points/{point_id}` | CEO |

**Students have no trip endpoints.** To browse bookable trips, students use `GET /reservations/available-trips` ([RESERVATIONS.md](RESERVATIONS.md)).

## 4. Create / Update Rules

`POST /trips` (CEO) — required: `route_id`, `bus_id`, `supervisor_id`, `departure_time`, `estimated_arrival_time`; optional: `passenger_capacity`, `fare_amount`, `pickup_points[]` (created inline).

Server validations at create/update:

| Check | Failure |
|---|---|
| Route exists and is active | `404` / `422` |
| Bus exists and is `ACTIVE` | `404` / `422` |
| Supervisor exists, is SUPERVISOR, is active | `404` / `422` |
| Arrival strictly after departure | `422` |
| **Bus schedule conflict** — the bus must not overlap another trip's window | `409` |
| **Supervisor schedule conflict** — the supervisor must not overlap another trip's window | `409` |

`PATCH /trips/{trip_id}` re-validates only changed references and re-checks conflicts excluding the trip itself.

## 5. Trip Listing Filters (CEO/SUPERVISOR)

`page`, `page_size`, `status`, `route_id`, `bus_id`, `supervisor_id`, `departure_after`, `departure_before` (ISO 8601 datetimes).

## 6. Pickup (Gathering) Points

Per-trip gathering locations where students board and supervisors scan.

`PickupPointResponse`:

```json
{
  "id": 9,
  "trip_id": 55,
  "name": "Cairo University Gate 3",
  "address": "Giza, University St.",
  "sequence": 1,
  "created_at": "...",
  "updated_at": "..."
}
```

- `name` 1–255 chars (required), `address` ≤ 255 optional, `sequence` ≥ 1 (ordering; not enforced unique server-side).
- Students select their outbound (and optionally return) pickup point **from a trip's pickup points** when subscribing; the scan endpoint validates that the scanned pickup point matches the student's configured one and belongs to the scanned trip ([QR_AND_BOARDING.md](QR_AND_BOARDING.md)).
- Points can also be provided inline in `POST /trips` via the `pickup_points` array.

## 7. Frontend Flow Suggestion (CEO scheduler)

```
Pick active route   ← GET /routes?is_active=true
Pick active bus     ← GET /buses?status=ACTIVE
Pick supervisor     ← GET /users?role=SUPERVISOR&is_active=true (CEO)
   ↓
POST /trips (departure/arrival/capacity/fare, optional pickup_points)
   ↓ 409? → adjust time/bus/supervisor (schedule conflict)
PATCH /trips/{id}/pickup-points... (fine-tune gathering points)
   ↓
PATCH /trips/{id}/status (SCHEDULED → IN_PROGRESS on departure day → COMPLETED)
```
