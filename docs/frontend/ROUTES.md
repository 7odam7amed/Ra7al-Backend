# Routes, Stations & Route Stops

Verified against `app/api/v1/routes.py`, `app/api/v1/stations.py`, `app/services/route_service.py`, and `app/services/station_service.py`.

---

## 1. Stations

Physical stops with coordinates. **All station endpoints: CEO + SUPERVISOR only.**

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

| Endpoint | Notes |
|---|---|
| `POST /stations` | `name` (1–100), `code` (1–50, unique, stored uppercase), `address?`, `latitude` (−90…90), `longitude` (−180…180). Created `is_active: true`. |
| `GET /stations` | Filters: `is_active`, `search` (name/code/address). Paginated. |
| `GET /stations/{station_id}` | |
| `PATCH /stations/{station_id}` | Any subset of the fields. |
| `PATCH /stations/{station_id}/status` | `{ "is_active": bool }`. |
| `DELETE /stations/{station_id}` | `409` if referenced by routes or stops. |

## 2. Routes

A route connects an origin and a destination station (distinct) and carries ordered intermediate stops.

`RouteResponse`:

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
  "origin_station": { "…": "StationResponse" },
  "destination_station": { "…": "StationResponse" },
  "stops": [ { "…": "RouteStopResponse" } ]
}
```

### Route status

Routes have a boolean `is_active` (no enum). Inactive routes cannot be selected when purchasing a subscription and are excluded from trip creation. Toggle with `PATCH /routes/{id}/status { "is_active": false }`.

### Endpoints & roles

| Endpoint | CEO | SUPERVISOR | STUDENT |
|---|:-:|:-:|:-:|
| `POST /routes` | ✓ | ✓ | ✗ |
| `GET /routes` | ✓ | ✓ | ✓ (read-only) |
| `GET /routes/{route_id}` | ✓ | ✓ | ✓ (read-only) |
| `PATCH /routes/{route_id}` | ✓ | ✓ | ✗ |
| `PATCH /routes/{route_id}/status` | ✓ | ✓ | ✗ |
| `PATCH /routes/{route_id}/supervisor` | ✓ | ✓ | ✗ |
| `DELETE /routes/{route_id}` | ✓ | ✓ | ✗ |

**Student read access is intentional:** students need routes to browse the network and read trip context. Route/trip/pickup-point choice is NOT part of subscription purchase — the subscription is plan + dates + payment only; transportation is chosen per day through the reservation workflow. All route management operations remain blocked for students.

### Validation rules

- `route_number`: 1–50 chars, stored **uppercase**, unique (`409` on duplicates).
- `origin_station_id ≠ destination_station_id` (`422` / `409`? — it's `422` on create/update validation; stations themselves must exist → `404`).
- `distance_km` > 0, `estimated_duration_minutes` > 0.
- `supervisor_id` optional; if provided, must reference an **active SUPERVISOR** (`404` not found, `422` wrong role/inactive).

### Supervisor assignment

`PATCH /routes/{route_id}/supervisor` with `{ "supervisor_id": 7 }` or `{ "supervisor_id": null }` (unassign). A route's supervisor is displayed via `supervisor_id` on `RouteResponse`. Note: supervisor assignment also happens per-trip (`Trip.supervisor_id`) — a supervisor scanning QR codes is authorized by the **trip** assignment, not the route assignment.

## 3. Route Stops (intermediate stops)

Ordered stations between origin and destination. `RouteStopResponse`:

```json
{
  "id": 21,
  "route_id": 10,
  "station_id": 4,
  "stop_order": 1,
  "created_at": "...",
  "station": { "…": "StationResponse" }
}
```

Uniqueness rules (server-enforced, `409` violations):
- A station can appear **once** per route.
- Each `stop_order` is unique per route; orders are positive integers (1, 2, 3, …). There is no auto-renumbering — the client chooses orders.

| Endpoint | Roles | Notes |
|---|---|---|
| `GET /routes/{route_id}/stops` | any authenticated (read-only) | Ordered by `stop_order`. |
| `POST /routes/{route_id}/stops` | CEO, SUPERVISOR | Body `{ "station_id": 4, "stop_order": 1 }`. |
| `PATCH /routes/{route_id}/stops/reorder` | CEO, SUPERVISOR | Batch: `{ "stops": [ { "route_stop_id": 21, "stop_order": 2 }, … ] }`. All IDs must belong to the route; duplicate IDs or orders → `422`. |
| `PATCH /routes/{route_id}/stops/{route_stop_id}` | CEO, SUPERVISOR | Body `{ "stop_order": 3 }`. |
| `DELETE /routes/{route_id}/stops/{route_stop_id}` | CEO, SUPERVISOR | `204`. |

`DELETE /routes/{route_id}` cascade-deletes the route's stops.

## 4. Gathering Points vs Route Stops

Two distinct concepts — don't conflate them:

| | **Route stops** (this doc) | **Pickup points** ([TRIPS.md](TRIPS.md)) |
|---|---|---|
| Attached to | Route | Trip |
| Purpose | Geographic path of the route | Student gathering locations for boarding scans |
| Ordered by | `stop_order` | `sequence` |
| Used by | Route display, planning | Daily reservation pickup selection, QR boarding validation |

## 5. Frontend Flow Suggestion (CEO route builder)

```
POST /stations (as needed)
   ↓
POST /routes (origin + destination)
   ↓
POST /routes/{id}/stops (repeat; assign stop_order)
   ↓
PATCH /routes/{id}/stops/reorder (final ordering)
   ↓
PATCH /routes/{id}/supervisor (optional)
```
