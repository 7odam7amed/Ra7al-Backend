# Buses & Bus Images

Fleet management and the image flow, verified against `app/api/v1/buses.py`, `app/services/bus_service.py`, and `app/core/storage.py`.

---

## 1. Bus Model

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

| Field | Type | Notes |
|---|---|---|
| `id` | int | |
| `bus_number` | string | unique; `name` is accepted as an alias on create/update |
| `license_plate` | string | unique; `plate_number` alias; stored UPPERCASE |
| `capacity` | int | 1–150 |
| `model` | string \| null | `type` alias |
| `year` | int \| null | 1990–2050 |
| `status` | string | `ACTIVE` / `INACTIVE` / `MAINTENANCE` |
| `image_url` | string \| null | **internal storage reference — not a public URL** |

## 2. Endpoints

| Method | Path | Roles | Notes |
|---|---|---|---|
| `POST /buses` | CEO | JSON or multipart (multipart required with image). New buses are `ACTIVE`. |
| `GET /buses` | CEO, SUPERVISOR | Filters: `status`, `search` (number/plate/model), pagination. |
| `GET /buses/{bus_id}` | CEO, SUPERVISOR | |
| `PATCH /buses/{bus_id}` | CEO | Vehicle details only — **cannot** change status or image. |
| `PATCH /buses/{bus_id}/status` | CEO | |
| `DELETE /buses/{bus_id}` | CEO | `409` if the bus has active scheduled trips. |
| `PATCH /buses/{bus_id}/image` | CEO | Replace image (multipart, field `image`). Old object deleted after success. |
| `DELETE /buses/{bus_id}/image` | CEO | Removes image; `422` if none exists. |
| `GET /buses/{bus_id}/image` | CEO / assigned supervisor / reserved student | Streams bytes. |
| `GET /buses/{bus_id}/image/metadata` | same | Availability metadata + stream URL. |

Full request/response schemas: [API_REFERENCE.md — Buses](API_REFERENCE.md#buses).

## 3. Bus Image Flow (authoritative)

### Create with or without image

- **No image part (or an empty file part):** the bus is created with `image_url = null`. The frontend must **never assume a bus has an image**.
- **With image:** the file is validated and stored through the backend storage service (`bus_images` namespace) *before* the DB row is written; if the DB insert fails, the stored file is cleaned up. The response's `image_url` is the storage reference.

### Displaying images in the frontend

```
GET /api/v1/buses/{bus_id}/image/metadata   (with Authorization header)
        │
        ├── has_image == false  →  render placeholder; image_stream_url is null
        │
        └── has_image == true   →  GET /api/v1/buses/{bus_id}/image
                                   (Authorization header; fetch as blob)
                                          │
                                          ▼
                                   URL.createObjectURL(blob) → <img src>
```

Key facts:

1. `image_url` on `BusResponse`/`BusImageResponse` is a storage reference like `uploads/bus_images/9ab7d3e1.png` — **not** a fetchable URL. Never put it in an `<img src>`.
2. `image_stream_url` (metadata endpoint) is a **relative** API path (`/api/v1/buses/{id}/image`); prefix it with your `API_BASE_URL`.
3. The stream endpoint enforces relationship access:
   - **CEO:** any bus.
   - **SUPERVISOR:** only buses used by a trip assigned to them.
   - **STUDENT:** only buses of trips on which they hold a **CONFIRMED reservation**.
4. The stream returns `Cache-Control: private, max-age=300` — brief client-side caching is acceptable; the object may change when the CEO replaces the image.
5. A `404` on the stream endpoint with an existing bus means **no image** (`"Bus with ID {id} has no image"`).

### Replacement & removal

- `PATCH /buses/{bus_id}/image`: upload-first semantics — the new object is stored, the reference updated, then the old object deleted. A failed DB update removes the new upload (no orphans).
- `DELETE /buses/{bus_id}/image`: clears `image_url` and deletes the stored object. `422` if the bus has no image.

### Storage backend behavior

| Environment | Backend | Bucket / location |
|---|---|---|
| Development (`STORAGE_BACKEND=local`) | Local filesystem | `uploads/bus_images/` on the server |
| Production (`STORAGE_BACKEND=supabase`) | Supabase Storage | Private **`bus-images`** bucket (separate from the `id-cards` bucket) |

Both buckets are **private**. The frontend cannot and must not access Supabase Storage directly — no public URLs, no anon-key access, no service-role key. All reads go through the authorized streaming endpoint, and all writes through the CEO image endpoints. Details: [FILE_UPLOADS.md](FILE_UPLOADS.md).
