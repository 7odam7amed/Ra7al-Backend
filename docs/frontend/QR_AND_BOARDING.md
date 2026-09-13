# QR Code & Boarding

The most behavior-critical section. Verified against `app/services/boarding_service.py`, `app/services/subscription_service.py`, `app/api/v1/boarding.py`, `app/api/v1/subscriptions.py`, and the `BoardingRecord` model.

---

## 1. QR Credential Lifecycle

### Generation
- Created **server-side** at subscription creation (and renewal) using a cryptographically secure random token (`secrets.token_urlsafe(32)`).
- Only the SHA-256 hash is stored for matching; the raw token is stored once and returned exclusively through the QR endpoint.
- The frontend never generates, parses, or validates tokens.

### Fetching (Student)

```
GET /api/v1/subscriptions/{subscription_id}/qr
Authorization: Bearer <student-token>
```

- Owner student only — **CEO and supervisors get 403** for this endpoint.
- Subscription must be `ACTIVE` → otherwise `422` (e.g. `"QR credential is only accessible for ACTIVE subscriptions (current status: PENDING)"`).
- Response `SubscriptionQRResponse`:

```json
{
  "subscription_id": 88,
  "plan_type": "WEEKLY",
  "route_id": 10,
  "route_name": "Campus Express",
  "valid_from": "2026-09-14",
  "valid_until": "2026-09-20",
  "qr_payload": "ra7al://subscription/Xk9fQ2s...",
  "status": "ACTIVE"
}
```

### Display (Student app)
- Render `qr_payload` **verbatim** into a QR image (any standard QR library). The `ra7al://subscription/` URI prefix is part of the payload.
- Show alongside: `valid_from`/`valid_until` dates and the usage counters from the subscription detail (below).

## 2. Scanning (Supervisor)

```
POST /api/v1/boarding/scan
Authorization: Bearer <supervisor-token>
```

Request (`BoardingScanRequest`):

```json
{
  "qr_token": "ra7al://subscription/Xk9fQ2s...",
  "trip_id": 55,
  "direction": "OUTBOUND",
  "pickup_point_id": 9
}
```

| Field | Notes |
|---|---|
| `qr_token` | 1–512 chars. The scanner should send the decoded QR payload as-is; the server strips the `ra7al://subscription/` prefix automatically, so sending the bare token also works. |
| `trip_id` | The trip being boarded. |
| `direction` | `OUTBOUND` or `RETURN`. |
| `pickup_point_id` | The gathering point where the scan happens (must be one of the trip's points). |

Success → `200 BoardingResponse`:

```json
{
  "success": true,
  "message": "Boarding verified successfully",
  "student": {
    "id": 42,
    "full_name": "Ahmed Ali",
    "phone_number": "+201012345678",
    "faculty": "Faculty of Engineering",
    "academic_year": "3rd Year"
  },
  "subscription_id": 88,
  "plan_type": "WEEKLY",
  "route_id": 10,
  "direction": "OUTBOUND",
  "pickup_point_id": 9,
  "boarded_at": "2026-09-15T07:35:00Z"
}
```

## 3. Validation Order & Error States (exact server behavior)

The server runs these checks in order; each failure returns `{"detail": "<message>"}`:

| # | Check | Status | Example detail |
|---|---|---|---|
| 1 | Scanner role is SUPERVISOR | 403 | `"Only SUPERVISOR users can perform boarding scans"` |
| 2 | Trip exists | 404 | `"Trip with ID 55 not found"` |
| 3 | Trip not CANCELLED/COMPLETED | 422 | `"Cannot record boarding for trip with status 'COMPLETED'"` |
| 4 | Scanner is the trip's assigned supervisor | 403 | `"You are not assigned as the supervisor for this trip"` |
| 5 | QR token resolves to a subscription (hash match) | 404 | `"Invalid QR token or subscription not found"` |
| 6 | Student account active + role STUDENT | 422 | `"Student account is inactive"` |
| 7 | Subscription date window | 422 | `"Subscription has expired"` / `"Subscription is not yet valid for today's date"` (past `end_date` also auto-flips status to EXPIRED) |
| 8 | Subscription status | 422 | `"Subscription is cancelled"` / `"Subscription has expired"` / `"Subscription is not active (current status: PENDING)"` |
| 9 | Route match | 422 | `"Subscription is for Route 10, but this trip is on Route 11"` |
| 10 | **Total QR allowance not exhausted** | 422 | `"QR usage allowance exhausted: the subscription has used all 14 allowed QR usages (7 days x 2 trips per day)"` |
| 11 | Pickup point matches the student's configured point for the direction | 422 | `"Scanned pickup point does not match student's configured outbound pickup point"` |
| 12 | Pickup point belongs to the trip | 422 | `"Scanned pickup point is not configured for this trip"` |
| 13 | **No duplicate scan** for the same subscription + trip + direction | 409 | `"Student has already boarded OUTBOUND for this trip"` |
| 14 | (re-checked under DB row lock) status, total allowance, **daily allowance** | 422 | `"Daily QR usage limit reached: at most 2 QR usages per day (one outbound and one return)"` |

Concurrent scans are serialized with a database row lock on the subscription, so limits can never be exceeded by parallel scans.

## 4. Usage Allowance Rules (authoritative)

```
max_qr_usages  = duration_days × 2
per calendar day: at most 2 successful scans (1 OUTBOUND + 1 RETURN)
```

| duration_days | max_qr_usages (total) |
|---|---|
| 1 | 2 |
| 5 | 10 |
| 7 | 14 |
| 16 | 32 |

Critical semantics for the frontend:

- **An unused calendar day does NOT consume the allowance.** Only *successful scans* (boarding records) count. A subscription with `duration_days = 7` where the student rides on 3 days has `used_qr_usages = 6`, not 14.
- Each successful scan consumes exactly **one** usage.
- **The backend is the source of truth.** The frontend must NOT implement its own QR counter, must not pre-compute allowances, and must not block scans locally — the scan endpoint decides.
- A duplicate scan (same trip + direction) is rejected with `409` even if usage remains.
- A third scan on the same calendar day is rejected with `422` even for a different trip/direction pairing (the daily cap is 2 regardless).

## 5. Usage Fields & Display Recipe

Available on every subscription detail/list payload (`SubscriptionDetailResponse`):

| Field | Meaning |
|---|---|
| `duration_days` | Plan duration in days (null if plan deleted). |
| `max_qr_usages` | `duration_days × 2` (null if plan deleted). |
| `used_qr_usages` | Total successful scans. |
| `remaining_qr_usages` | `max(0, max_qr_usages − used_qr_usages)`. |
| `qr_usages_today` | Successful scans today (server UTC calendar day). |

Suggested UI:

```
QR remaining: 30 / 32        ← remaining_qr_usages / max_qr_usages
Used today: 2 / 2            ← qr_usages_today / 2 (constant daily cap)
```

- If `qr_usages_today >= 2` → show "daily limit reached — scans resume tomorrow".
- If `remaining_qr_usages == 0` → show "allowance exhausted — renew subscription".
- If the QR/allowance fields are `null` (deleted plan edge case), fall back to showing only dates and `used_qr_usages`.

Poll or refetch `GET /subscriptions/{id}` (or `/my`) after every successful scan to refresh counters.

## 6. Boarding Records & Trip Roster

### Trip roster — `GET /boarding/trips/{trip_id}/students`
Assigned supervisor or CEO. Returns `SupervisorTripStudentResponse[]` including per-trip flags:

```json
{
  "student_id": 42,
  "student_name": "Ahmed Ali",
  "subscription_id": 88,
  "subscription_type": "WEEKLY",
  "subscription_status": "ACTIVE",
  "start_date": "2026-09-14",
  "end_date": "2026-09-20",
  "payment_status": "VERIFIED",
  "outbound_pickup": "Cairo University Gate 3",
  "return_pickup": "Main Gate",
  "boarding_count": 4,
  "outbound_boarding_count": 2,
  "return_boarding_count": 2,
  "outbound_boarded": true,
  "return_boarded": false,
  "last_boarded_at": "2026-09-16T07:35:00Z"
}
```

`outbound_boarded` / `return_boarded` are per-**trip** attendance indicators — ideal for a live checklist.

### Trip records — `GET /boarding/trips/{trip_id}/records`
`BoardingRecordResponse[]` (timestamped, includes supervisor and pickup names).

### System-wide records — `GET /boarding/records`
CEO only; paginated with filters `trip_id`, `student_id`, `supervisor_id`, `subscription_id`, `direction`, `boarded_after`, `boarded_before`.

### Student's own history — `GET /subscriptions/{id}/history`
Owner student / route-assigned supervisor / CEO; array of ride records with `direction`, `pickup_point_name`, `supervisor_name`, `boarded_at`.

## 7. Frontend Handling Summary

| Situation | Detected by | UI action |
|---|---|---|
| Daily limit reached | scan `422` with "Daily QR usage limit…" or `qr_usages_today >= 2` | Show daily-limit notice; roster flags already set |
| Total allowance exhausted | scan `422` with "QR usage allowance exhausted…" or `remaining_qr_usages == 0` | Prompt renewal (`PATCH /subscriptions/{id}/renew`) |
| Duplicate scan | scan `409` "already boarded … for this trip" | Mark that direction as boarded; do not retry |
| Unauthorized scanner | scan `403` "not assigned as the supervisor" | Supervisor picked the wrong trip — fix trip selection |
| Invalid/expired subscription | scan `422` ("expired", "not active", "not yet valid") | Show status-appropriate message; offer nothing further |
| Wrong route/pickup | scan `422` | Show which mismatch; supervisor picks correct trip/pickup |
| Unknown token | scan `404` "Invalid QR token or subscription not found" | Ask student to refresh QR screen |
