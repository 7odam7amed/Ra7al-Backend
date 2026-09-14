# Backend Changelog (Frontend-Relevant)

Documents backend changes that affect frontend integration. Dates/versions are only stated when verifiable; migration filenames are used as the factual anchor for ordering. The repository does not tag releases, so no version numbers are claimed.

---

## Verified from migration history

The Alembic chain (`alembic/versions/`) confirms this evolution:

| Migration | Change |
|---|---|
| `010_auth_phone_number.py` | Authentication identifier switched to **phone number** (from email-era credentials). |
| `011_otp_verification.py` | OTP verification tables introduced at one point. |
| `012_user_status_approval.py` | **User lifecycle statuses** (`PENDING`/`APPROVED`/`REJECTED`/`INACTIVE`) and the CEO approval workflow. |
| `013_remove_otp_verification.py` | **OTP verification removed.** No OTP endpoints exist in the current API. |
| `014_bus_image_flexible_plans.py` | **Bus images** added (`buses.image_url`, dedicated storage) **and flexible plan durations** (CEO-defined `duration_days`). |

## Current behavior (as of this documentation, September 2026)

### Authentication
- Login is **phone number + password** via the OAuth2 password form (`username` = phone). No email login. No OTP — do not build OTP UI. *(Migration `013`.)*
- JWT access tokens only: 30-minute expiry, HS256, `sub`/`role`/`iat`/`exp` claims. No refresh-token endpoint.
- Student accounts are created **PENDING** and cannot log in until the CEO approves them. *(Migration `012`.)*
- `UserStatus.ACTIVE` exists only as a legacy input alias mapping to `APPROVED`; responses always use `APPROVED`.

### Route read access
- `GET /routes`, `GET /routes/{id}`, and `GET /routes/{id}/stops` are readable by **any authenticated user, including STUDENTS** (read-only). Students need this for the subscription purchase flow. All route/stops *management* endpoints remain CEO+Supervisor.

### Bus images & Supabase Storage
- Buses carry an optional image: create without image → `image_url = null`. *(Migration `014`.)*
- Production storage is **Supabase** with private buckets; bus images use the dedicated **`bus-images`** bucket (separate from the `id-cards` bucket). No public object URLs; the service-role key never reaches the frontend.
- Images are displayed via `GET /buses/{id}/image` (relationship-authorized streaming) and `GET /buses/{id}/image/metadata`. Image replace/delete endpoints exist for the CEO.
- ID cards gained the streaming endpoint and a short-lived **signed-URL** endpoint (Supabase backend only; `501` on local storage).

### Subscription plans — CEO-defined durations
- `duration_days` is **CEO-defined** per plan (1–730). The `WEEKLY` type is **not** fixed to 7 days — e.g. WEEKLY+5, WEEKLY+12, MONTHLY+45, TERM+120 can coexist. Only `DAILY` is constrained to exactly 1 day. *(Migration `014`; enforced by schema and DB constraints.)*
- Subscription validity: `end_date = start_date + duration_days − 1` (inclusive).
- Renewal duration always comes from the plan's configured `duration_days`.

### QR usage allowance
- Allowance formula: **`max_qr_usages = duration_days × 2`**.
- Daily cap: **at most 2 successful scans per calendar day** (1 outbound + 1 return); a third scan same-day is rejected.
- Unused calendar days **do not** consume the allowance — only successful scans count.
- Exposed usage fields on subscription payloads: `duration_days`, `max_qr_usages`, `used_qr_usages`, `remaining_qr_usages`, `qr_usages_today`.
- Duplicate scans (same subscription + trip + direction) are rejected with `409`; concurrent scans are serialized via a DB row lock so limits cannot be exceeded.

### Pickup points in available trips
- `GET /reservations/available-trips` now embeds each trip's `pickup_points` (array of `PickupPointResponse`, ordered by `sequence`, `[]` when the trip has none).
- Additive change: all pre-existing fields, endpoint paths, and role requirements are unchanged.
- Students obtain valid `outbound_pickup_point_id` values for `POST /subscriptions` directly from this student-accessible response — `GET /trips/{id}/pickup-points` remains CEO/SUPERVISOR-only (unchanged).

### Other current-state notes
- Payment system supports reservations **and** subscriptions; verifying a subscription payment activates the subscription (`PENDING → ACTIVE`).
- Rate limiting is active on login/register (5/min), ID-card upload (10/min), bus image uploads (20/min), and boarding scans (60/min) — `429` + `Retry-After`.
- CORS is an explicit allow-list; wildcards are rejected in production configuration. Dev origins (`localhost:3000/5173`, `127.0.0.1:3000`) are auto-added outside production.

## Migration guidance for earlier frontend versions

If a frontend was built against older behavior, remove/replace:

1. Any email-login or OTP UI/flows → phone+password form only.
2. Any assumption `WEEKLY = 7 days` → always read `plan.duration_days`.
3. Any client-side QR counting → use the API usage fields.
4. Any direct image URL usage (`image_url` as `img src`) → metadata + streaming endpoint flow.
5. Any expected `400` responses → the API uses 401/403/404/409/422 instead.
