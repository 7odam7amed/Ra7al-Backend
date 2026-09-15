# QR Code & Boarding

The most behavior-critical section. Verified against `app/services/boarding_service.py`, `app/services/subscription_service.py`, `app/services/reservation_service.py`, `app/api/v1/boarding.py`, `app/api/v1/subscriptions.py`, the `BoardingRecord` model, and `app/utils/dates.py`.

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
  "valid_from": "2026-09-14",
  "valid_until": "2026-09-20",
  "qr_payload": "ra7al://subscription/Xk9fQ2s...",
  "status": "ACTIVE"
}
```

### ⚠️ A valid QR is necessary but NOT sufficient

Boarding also requires a **confirmed DAILY reservation** for the trip being scanned ([RESERVATIONS.md](RESERVATIONS.md)). The QR credential only proves "which plan did the student buy"; the daily selection proves "which trip and pickup points did the student choose for today".

### Display (Student app)
- Render `qr_payload` **verbatim** into a QR image (any standard QR library). The `ra7al://subscription/` URI prefix is part of the payload.
- Show alongside: `valid_from`/`valid_until` dates and the weekly usage counters from the subscription detail (section 5).

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
| `pickup_point_id` | The gathering point where the scan happens (must be one of the trip's points AND the student's selected point for the direction). |

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
  "route_id": 10,
  "direction": "OUTBOUND",
  "pickup_point_id": 9,
  "boarded_at": "2026-09-15T07:35:00Z",
  "usage_days_this_week": 3,
  "remaining_usage_days_this_week": 1
}
```

`usage_days_this_week` / `remaining_usage_days_this_week` are the weekly accounting AFTER this scan — in DAYS, not scans.

## 3. Validation Order & Error States (exact server behavior)

The server runs these checks in order; each failure returns `{"detail": "<message>"}`:

| # | Check | Status | Example detail |
|---|---|---|---|
| 1 | Scanner role is SUPERVISOR | 403 | `"Only SUPERVISOR users can perform boarding scans"` |
| 2 | Trip exists | 404 | `"Trip with ID 55 not found"` |
| 3 | Scanner is the trip's assigned supervisor | 403 | `"You are not assigned as the supervisor for this trip"` |
| 4 | Trip not CANCELLED/COMPLETED | 422 | `"Cannot record boarding for trip with status 'COMPLETED'"` |
| 5 | Real-time boarding: trip's service date is TODAY | 422 | `"Boarding can only be recorded on the trip's service date"` |
| 6 | QR token resolves to a subscription (hash match) | 404 | `"Invalid QR token or subscription not found"` |
| 7 | Student account active + role STUDENT | 422 | `"Student account is inactive"` |
| 8 | Subscription date window | 422 | `"Subscription has expired"` / `"Subscription is not yet valid for today's date"` (past `end_date` also auto-flips status to EXPIRED) |
| 9 | Subscription status | 422 | `"Subscription is cancelled"` / `"Subscription has expired"` / `"Subscription is not active (current status: PENDING)"` |
| 10 | **Confirmed reservation exists** for the trip's service date, belongs to this student, and is for THIS trip | 422 | `"No confirmed reservation found for this trip's date"` / `"Reservation is not for this trip"` |
| 11 | Reservation direction matches the scanned direction (trip direction) | 422 | `"Reservation direction does not match the trip direction"` |
| 12 | Scanned pickup point matches the reservation's `selected_pickup_point_id` | 422 | `"Scanned pickup point does not match the selected pickup point for this trip"` |
| 13 | Pickup point belongs to the trip | 422 | `"Scanned pickup point is not configured for this trip"` |
| 14 | **No duplicate scan** for the same subscription + trip + direction | 409 | `"Student has already boarded OUTBOUND for this trip"` |
| 15 | (re-checked under DB row lock) status, duplicate, **daily 2-scan cap**, **weekly distinct-day allowance** | 409/422 | `"Daily QR limit reached: at most 2 scans per day (one outbound and one return)"` / `"Weekly usage limit reached: the subscription allows at most 4 usage days per week…"` |

Concurrent scans are serialized with a database row lock on the subscription; the weekly limit is re-checked against committed data **inside** the lock, so parallel scans can never bypass the weekly allowance.

## 4. THE WEEKLY USAGE-DAY RULE (authoritative)

```
days_per_week   = maximum DISTINCT usage DAYS per calendar week (Mon–Sun, UTC)
per usage day:  exactly 1 OUTBOUND + 1 RETURN scan (2 scans max)
outbound + return on the SAME day = ONE usage day
```

- A **usage day** is a calendar date with at least one successful scan. Scanning outbound and return on Monday consumes ONE usage day, not two.
- With `days_per_week = 4`: Mon ✓ Tue ✓ Wed ✓ Thu ✓ → **Fri ✗** (weekly limit), even if the subscription has remaining validity days and remaining total capacity.
- **No rollover:** unused allowance does NOT carry into another week. Week 1 with 2 used days does NOT give week 2 six days — every week gets a fresh `days_per_week`.
- **Week definition (deterministic):** MONDAY → SUNDAY in the project's business timezone (UTC). The same definition is used by QR validation, subscription usage responses, and tests. Week-start constant lives in `app/utils/dates.py` (`WEEK_START_WEEKDAY = 0`, `BUSINESS_TIMEZONE = UTC`).
- **Subscription expiration always wins:** after `end_date` nothing is usable — expired overrides any remaining weekly allowance.
- **The backend is the source of truth.** The frontend must NOT implement its own usage counter or block scans locally — the scan endpoint decides.

Worked example (`days_per_week = 4`):

| Day | Scans | usage_days_this_week | Result |
|---|---|---|---|
| Mon | OUT + RET | 1 | allowed |
| Tue | OUT only | 2 | allowed |
| Wed | OUT + RET | 3 | allowed |
| Thu | OUT + RET | 4 | allowed (reaches limit) |
| Fri | — | 4 | **rejected 422 "Weekly usage limit reached…"** |
| next Mon | — | 1 | allowed again (fresh allowance, no rollover) |

## 5. Usage Fields & Display Recipe

Available on every subscription detail/list payload (`SubscriptionDetailResponse`):

| Field | Meaning |
|---|---|
| `days_per_week` | Snapshot of the weekly usage-day allowance. |
| `usage_days_this_week` | **Distinct calendar days used this week** — DAYS, not scans. |
| `remaining_usage_days_this_week` | `max(0, days_per_week − usage_days_this_week)`. |
| `used_qr_usages` | Total successful scans over the whole subscription (history/statistic). |
| `qr_usages_today` | Successful scans today (max 2). |

**Label warning:** `usage_days_this_week` counts DAYS. Never label it "scans" and never add it to `used_qr_usages`.

Suggested UI:

```
Weekly usage: 3 / 4 days     ← usage_days_this_week / days_per_week
Used today: 1 / 2 scans      ← qr_usages_today / 2 (daily scan cap)
```

- If `remaining_usage_days_this_week == 0` → show "weekly limit reached — resets Monday".
- If `qr_usages_today >= 2` → show "daily scan limit reached — scans resume tomorrow".
- Poll or refetch `GET /subscriptions/{id}` (or `/my`) after every successful scan to refresh counters.

## 6. Boarding Records & Trip Roster

### Trip roster — `GET /boarding/trips/{trip_id}/students`
Assigned supervisor or CEO. Returns the students who SELECTED this trip for the trip's service date (`SupervisorTripStudentResponse[]`):

```json
{
  "student_id": 42,
  "student_name": "Ahmed Ali",
  "subscription_id": 88,
  "subscription_status": "ACTIVE",
  "service_date": "2026-09-20",
  "direction": "OUTBOUND",
  "payment_status": "VERIFIED",
  "selected_point": "Al-Mahatta",
  "outbound_boarded": true,
  "return_boarded": false,
  "last_boarded_at": "2026-09-15T07:35:00Z"
}
```

`outbound_boarded` / `return_boarded` are per-**trip** attendance indicators — ideal for a live checklist. The roster is built from confirmed reservations, so a student only appears after booking that trip for its service date.

### Trip records — `GET /boarding/trips/{trip_id}/records`
`BoardingRecordResponse[]` (timestamped, includes supervisor and pickup names).

### System-wide records — `GET /boarding/records`
CEO only; paginated with filters `trip_id`, `student_id`, `supervisor_id`, `subscription_id`, `direction`, `boarded_after`, `boarded_before`.

### Student's own history — `GET /subscriptions/{id}/history`
Owner student / route-assigned supervisor / CEO; array of ride records with `direction`, `pickup_point_name`, `supervisor_name`, `boarded_at`.

## 7. Frontend Handling Summary

| Situation | Detected by | UI action |
|---|---|---|
| Weekly limit reached | scan `422` "Weekly usage limit reached…" or `remaining_usage_days_this_week == 0` | Show weekly-limit notice ("resets Monday") |
| Daily scan cap reached | scan `422` "Daily QR limit reached…" or `qr_usages_today >= 2` | Show daily-limit notice |
| No daily selection | scan `422` "No confirmed reservation found…" | Student must book the trip ([RESERVATIONS.md](RESERVATIONS.md)) |
| Selection mismatch (trip/pickup/direction) | scan `422` "…selection is not for this trip" / "does not match the selected pickup point" | Supervisor picked the wrong trip/point, or student changed selection |
| Duplicate scan | scan `409` "already boarded … for this trip" | Mark that direction as boarded; do not retry |
| Unauthorized scanner | scan `403` "not assigned as the supervisor" | Supervisor picked the wrong trip — fix trip selection |
| Invalid/expired subscription | scan `422` ("expired", "not active", "not yet valid") | Show status-appropriate message; offer renewal |
| Unknown token | scan `404` "Invalid QR token or subscription not found" | Ask student to refresh QR screen |
