# Frontend Integration Guide

Practical integration instructions using only actual endpoints and behavior.

---

## 1. Configure the API Base URL

```env
# .env of your frontend project
VITE_API_BASE_URL=http://localhost:8000        # development
# VITE_API_BASE_URL=https://<production-domain> # production — UNKNOWN / VERIFY WITH BACKEND for the exact host
```

All versioned endpoints are `{API_BASE_URL}/api/v1/...`. Unversioned: `/health`, `/health/db`, `/docs`, `/redoc`, `/openapi.json`.

## 2. Login

```js
const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({
    username: phone,      // registered phone number
    password: password,
  }),
});
if (res.status === 403) showError((await res.json()).detail); // pending / rejected / inactive
const { access_token, token_type } = await res.json();        // token_type === "bearer"
```

## 3. Store the Token & Attach the Authorization Header

```js
// axios interceptor
api.interceptors.request.use((config) => {
  const token = getToken();                    // memory or localStorage
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

Tokens expire after **30 minutes**; there is no refresh endpoint — intercept `401` and re-login.

## 4. Determine the User Role

```js
const me = await api.get("/api/v1/auth/me");   // authoritative profile
switch (me.data.role) {
  case "CEO":        /* CEO dashboard */ break;
  case "SUPERVISOR": /* supervisor console */ break;
  case "STUDENT":    /* student app */ break;
}
```

Do not decode the JWT for authorization decisions.

## 5. Central Error Handling (401 / 403 / 409 / 422)

```js
api.interceptors.response.use(null, (error) => {
  const { status, data } = error.response;
  if (status === 401) { clearToken(); redirectToLogin(); return; }
  if (status === 403) showPermissionToast(data.detail);       // role/ownership problem
  if (status === 404) showNotFound(data.detail);
  if (status === 409) { refreshRelatedData(); showConflict(data.detail); }
  if (status === 422) {
    if (Array.isArray(data.detail)) showFieldErrors(data.detail);  // schema validation
    else showBusinessError(data.detail);                            // business rule
  }
  if (status === 429) waitRetryAfter(error.response);
  return Promise.reject(error);
});
```

Full matrix: [ERRORS.md](ERRORS.md).

## 6. Upload Files

All uploads are `multipart/form-data` with **exact** field names:

```js
// Student ID card (public, pre-registration)
const fd = new FormData();
fd.append("file", idCardFile);                       // field MUST be "file"
const { data } = await api.post("/api/v1/auth/upload-id-card", fd);
// data.image_path → send as university_id_card_image in POST /auth/register

// Bus image (CEO) — create
const fd2 = new FormData();
fd2.append("bus_number", "BUS-101");
fd2.append("license_plate", "ABC-1234");
fd2.append("capacity", "50");
fd2.append("image", busImageFile);                   // field MUST be "image"
await api.post("/api/v1/buses", fd2);

// Bus image (CEO) — replace
await api.patch(`/api/v1/buses/${busId}/image`, fdImage);
```

Rules: JPEG/PNG/WEBP only, ≤ 5 MB, extension must match actual content. Let the browser set the multipart `Content-Type` (do not set it manually).

## 7. Display Bus Images

```js
// 1. Metadata first (auth required)
const meta = await api.get(`/api/v1/buses/${busId}/image/metadata`);
if (!meta.data.has_image) return renderPlaceholder();

// 2. Stream bytes as blob (auth header required — <img src> won't work)
const img = await api.get(`${API_BASE_URL}/api/v1/buses/${busId}/image`, {
  responseType: "blob",
});
busImage.src = URL.createObjectURL(img.data);
```

`BusResponse.image_url` is a storage reference (or `null`) — **never** use it as an `img src`. Details: [BUSES.md](BUSES.md).

## 8. Fetch Routes (students too)

```js
// Any authenticated user; students get read-only access (subscription flow needs this)
const routes = await api.get("/api/v1/routes", { params: { is_active: true, page: 1, page_size: 50 } });
// routes.data.items[] → id, route_number, name, origin_station, destination_station, stops[]
```

## 9. Create a Subscription (student)

```js
// 1. Plans for purchase screen (plain array, active only)
const plans = await api.get("/api/v1/subscriptions/plans");

// 2. Pick a trip's pickup points for the chosen route (points are per-trip)
//    (discover trips via GET /reservations/available-trips?route_id=… or CEO-provided info,
//     then GET /trips/{id}/pickup-points — note: students cannot call GET /trips;
//     pickup point selection UI must rely on data provided through available plans/routes flows
//     or an admin-provided list. UNKNOWN / VERIFY WITH BACKEND if the student flow needs
//     direct pickup-point discovery.)

// 3. Purchase
const sub = await api.post("/api/v1/subscriptions", {
  route_id: 10,
  plan_id: 5,
  outbound_pickup_point_id: 9,
  return_pickup_mode: "SAME_AS_OUTBOUND",   // or DIFFERENT + return_pickup_point_id
  payment_method: "VODAFONE_CASH",
  transaction_reference: "VC-123456789",    // optional; → payment starts SUBMITTED
});
// sub.data.status === "PENDING" until an admin verifies the payment
```

## 10. Display Subscription Status & Usage

```js
const sub = await api.get(`/api/v1/subscriptions/${id}`);
// sub.data: { status, payment_status, start_date, end_date,
//             duration_days, max_qr_usages, used_qr_usages,
//             remaining_qr_usages, qr_usages_today, ... }
```

UI recipe:

```
Status:        sub.status (+ payment_status while PENDING)
Validity:      sub.start_date → sub.end_date
QR remaining:  {remaining_qr_usages} / {max_qr_usages}
Used today:    {qr_usages_today} / 2
```

Never compute allowances client-side — the fields above are the contract. Details: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

## 11. Show the QR (student)

```js
const qr = await api.get(`/api/v1/subscriptions/${id}/qr`);  // owner only, ACTIVE only
renderQrImage(qr.data.qr_payload);                            // render verbatim
// Also show qr.valid_from / qr.valid_until
```

## 12. Scan QR (supervisor)

```js
const scan = await api.post("/api/v1/boarding/scan", {
  qr_token: scannedPayload,        // decoded QR content as-is
  trip_id: currentTripId,          // must be the trip assigned to this supervisor
  direction: "OUTBOUND",           // or "RETURN"
  pickup_point_id: currentPickupId // must match the student's configured point
});
// 200 → scan.data.student.full_name boarded at scan.data.boarded_at
// 409 → already boarded this trip+direction
// 422 → daily limit / allowance exhausted / subscription invalid / wrong pickup
```

## 13. Handle the Daily QR Limit & Exhausted Allowance

| Signal | Action |
|---|---|
| `qr_usages_today >= 2` (or scan 422 "Daily QR usage limit reached…") | "Daily limit reached — scans resume tomorrow." Keep roster flags visible. |
| `remaining_qr_usages === 0` (or scan 422 "QR usage allowance exhausted…") | "Allowance used up." Offer `PATCH /api/v1/subscriptions/{id}/renew`. |
| Scan 409 ("already boarded … for this trip") | Mark the direction boarded; don't retry. |

After any successful scan, refetch the subscription to refresh counters.

## 14. CORS

The backend enforces an **explicit origin allow-list** (wildcards are forbidden in production and validated at startup):

- Development (auto-added even if not configured): `http://localhost:3000`, `http://localhost:5173`, `http://127.0.0.1:3000`.
- Production: whatever origins are configured in the backend's `CORS_ORIGINS` env var — **your production frontend origin must be registered with the backend team**. `UNKNOWN / VERIFY WITH BACKEND` for the final list.
- `allow_credentials: true`, all methods and headers allowed.

If the browser reports a CORS error: (1) confirm the exact origin (scheme + host + port) is allow-listed — `http://localhost:5173` works in dev automatically; (2) a masked CORS error can also mean the server returned 500 — check the network tab for the actual status; the backend attaches CORS headers even to 500 responses.

## 15. Swagger / OpenAPI

| Resource | URL | Notes |
|---|---|---|
| Swagger UI | `{API_BASE_URL}/docs` | Try endpoints interactively. Click **Authorize**, choose OAuth2 password flow, enter the phone number as `username`. |
| ReDoc | `{API_BASE_URL}/redoc` | Readable reference. |
| OpenAPI JSON | `{API_BASE_URL}/openapi.json` | Generate typed clients from it. |

> These doc routes are unversioned (no `/api/v1`). This documentation package is derived from the code and cross-checked against these schemas.

## 16. Integration Checklist

- [ ] `API_BASE_URL` configured per environment
- [ ] Login via form-urlencoded; pending/rejected/inactive messages surfaced
- [ ] Token attached via interceptor; 401 → re-login
- [ ] Role from `GET /auth/me`; role-specific dashboards
- [ ] Error interceptor handles object vs array 422, 409 conflicts, 429 `Retry-After`
- [ ] Registration: upload ID card first → use returned `image_path`
- [ ] Bus images: metadata → blob stream; placeholder when `has_image === false`
- [ ] Subscription purchase → show PENDING until `payment_status === "VERIFIED"`
- [ ] QR usage displayed from API fields only (no client counters)
- [ ] Production origin registered for CORS
