# File Uploads & Storage

Verified against `app/core/storage.py`, `app/api/v1/auth.py`, and `app/api/v1/buses.py`.

---

## 1. Upload Endpoints

| Endpoint | Field name | Purpose | Auth | Rate limit |
|---|---|---|---|---|
| `POST /api/v1/auth/upload-id-card` | `file` | Student ID card (pre-registration) | Public | 10/min/IP |
| `POST /api/v1/buses` | `image` (optional) | Bus image at creation | CEO | 20/min/IP |
| `PATCH /api/v1/buses/{bus_id}/image` | `image` (required) | Replace bus image | CEO | 20/min/IP |

## 2. Universal Validation Rules (server-enforced)

| Rule | Value |
|---|---|
| Allowed extensions | `.jpg`, `.jpeg`, `.png`, `.webp` |
| Allowed MIME types | `image/jpeg`, `image/png`, `image/webp` |
| Max size | **5 MB** (5 × 1024 × 1024 bytes) |
| Empty file | Rejected (`422`) |
| Path traversal / null bytes / `..` in filename | Rejected |
| Dangerous double extensions (e.g. `image.php.png`, `x.exe.jpg`) | Rejected |
| Executable/script magic bytes (MZ, ELF, `<?php`, HTML, `<script>`) | Rejected |
| **Content-signature check** | File header bytes must match the declared MIME **and** the extension (JPEG magic `FF D8 FF`, PNG magic, WEBP `RIFF…WEBP`) |

All violations produce `422` with a descriptive `detail` message. Send the correct `Content-Type` for the file part and keep extensions consistent with actual content — mismatches are rejected.

## 3. ID-Card Upload Flow

```
POST /api/v1/auth/upload-id-card
Content-Type: multipart/form-data
        │  field: file = <binary>
        ▼
201 { "image_path": "uploads/id_cards/<uuid>.png" }
        │
        ▼  send image_path verbatim as university_id_card_image
POST /api/v1/auth/register { ..., "university_id_card_image": "uploads/id_cards/<uuid>.png" }
```

- The stored reference is later exposed on the user record as `university_id_card_image`.
- Viewing: `GET /users/{user_id}/id-card` (bytes) or `GET /users/{user_id}/id-card/signed-url?expires_in=60` (production only) — owner student or CEO only.

## 4. Bus Image Flow

- Create-time: include an `image` part in the multipart create request; omit it (or send an empty part) for `image_url = null`.
- Replace: `PATCH /buses/{bus_id}/image` with field `image`; the previous object is deleted after a successful swap.
- Remove: `DELETE /buses/{bus_id}/image` (no body).
- Display: always via `GET /buses/{bus_id}/image` after checking `GET /buses/{bus_id}/image/metadata`. Full flow: [BUSES.md](BUSES.md).

Example — replacing a bus image:

```http
PATCH /api/v1/buses/3/image HTTP/1.1
Authorization: Bearer <token>
Content-Type: multipart/form-data; boundary=xx

--xx
Content-Disposition: form-data; name="image"; filename="newbus.png"
Content-Type: image/png

<binary>
--xx--
```

## 5. What the Frontend Receives

| Upload | Returns |
|---|---|
| ID card | `{ "image_path": "uploads/id_cards/<uuid>.<ext>" }` — a storage reference, **not** a URL |
| Bus create/replace | `BusResponse` with `image_url` = `"uploads/bus_images/<uuid>.<ext>"` or `null` |

Neither value is directly fetchable by a browser. Rendering always goes through the authorized streaming endpoints (`/users/{id}/id-card`, `/buses/{id}/image`) or, for ID cards in production, the short-lived signed URL.

## 6. Storage Architecture (what the frontend needs to know)

- **Backends:** `local` (development; files under `uploads/<namespace>/` on the server) or `supabase` (production; private buckets). Selected by `STORAGE_BACKEND`; production with Supabase credentials always uses Supabase.
- **Buckets:** ID cards → `id-cards` (configurable); bus images → **`bus-images`** (private, dedicated bucket, never mixed with ID cards).
- **Both buckets are private.** There are no public object URLs anywhere in the API.
- **Supabase service-role key is server-only.** It is never returned by any endpoint, and the backend actively strips/validates signed URLs to ensure the key never leaks.
- **Direct Supabase access from the frontend is NOT supported by the current architecture.** Do not use the Supabase JS client against these buckets; use the backend endpoints above.
- **Signed URLs** exist only for ID cards (`GET /users/{id}/id-card/signed-url`, 1–300 s expiry) and only on the Supabase backend — `501` on the local backend. Bus images have no signed-URL endpoint; they stream through the authorized API path.

## 7. Error Reference

| Status | Cause |
|---|---|
| 422 | Unsupported extension, wrong MIME, signature/MIME/extension mismatch, > 5 MB, empty file, dangerous double extension, no file part (bus image replace) |
| 401/403 | Missing/invalid token, or insufficient role (bus image endpoints) |
| 404 | Target bus/user not found, or underlying object missing at view time |
| 429 | Rate limit exceeded (`Retry-After` header) |
| 503 | Storage backend unavailable (Supabase unreachable) |
| 501 | Signed URL requested while backend runs on local storage |
