# Routes & Pickup Points (Post-Refactor)

Verified against `app/api/v1/routes.py`, `app/services/route_service.py`, and the new transportation model.

---

## 1. Route = container of pickup points

A Route is **only a logical group of pickup points**. It has NO origin, destination, distance, duration, or supervisor. `RouteStop` no longer exists.

`RouteResponse`:

```json
{
  "id": 10,
  "name": "Route A",
  "is_active": true,
  "pickup_points": [ { "…": "PickupPointResponse" } ],
  "created_at": "...",
  "updated_at": "..."
}
```

| Endpoint | Method | Notes |
|---|---|---|
| `/routes` | `POST` | CEO only. Body: `{ "name": "Route A" }`. |
| `/routes` | `GET` | Any authenticated role. Paginated. |
| `/routes/{id}` | `GET` | Any authenticated role. Includes `pickup_points`. |
| `/routes/{id}` | `PATCH` | CEO only. Rename / toggle `is_active` (`PATCH /routes/{id}/status`). |
| `/routes/{id}` | `DELETE` | CEO only. `409` when the route still has pickup points. |

## 2. Pickup points belong to exactly ONE route

A pickup point is created **under a route** and can never belong to two routes. There is **no latitude/longitude**.

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

| Endpoint | Method | Notes |
|---|---|---|
| `/routes/{route_id}/pickup-points` | `POST` | CEO only. Body: `{ "name": "Al-Mahatta", "address": null, "sequence": 1 }`. |
| `/routes/{route_id}/pickup-points` | `GET` | Any authenticated role. Points in order. |
| `/routes/{route_id}/pickup-points/{point_id}` | `PATCH` | CEO only. Name / address / sequence. |
| `/routes/{route_id}/pickup-points/{point_id}` | `DELETE` | CEO only. `409` when referenced by trip stops or bookings. |
| `/pickup-points/{point_id}/move` | `POST` | **Not supported.** A point cannot be moved between routes. Delete + recreate instead. |

### Errors

| Status | Meaning |
|---|---|
| `409` | Point already belongs to another route (one-route-per-point rule), or deletion blocked by references. |
| `404` | Route or point not found. |
| `422` | Validation (empty name, bad sequence). |

## 3. Stations (legacy, unchanged)

Stations still exist for their own CRUD (`/stations`, CEO + SUPERVISOR) but are **not** referenced by routes anymore.
