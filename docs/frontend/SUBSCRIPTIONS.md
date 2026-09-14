# Subscriptions & Subscription Plans

Verified against `app/api/v1/subscription_plans.py`, `app/api/v1/subscriptions.py`, `app/services/subscription_plan_service.py`, `app/services/subscription_service.py`, `app/models/subscription_plan.py` (including DB constraints), and `app/models/subscription.py`.

> **CORE CONCEPT (v2 contract):** A subscription is ONLY a plan purchase — `plan + start_date + payment_method (+ digital payment reference)`. It contains **NO route, trip, or pickup-point selection**. Daily transportation (trip + outbound pickup point + return pickup point) is chosen separately each day through the **Reservation** workflow — see [RESERVATIONS.md](RESERVATIONS.md).

---

## 1. Subscription Plans

A plan is a purchasable package defined by a **type**, a **CEO-defined duration**, and a **CEO-defined weekly usage allowance**.

`SubscriptionPlanResponse`:

```json
{
  "id": 5,
  "name": "Weekly Standard",
  "plan_type": "WEEKLY",
  "duration_days": 7,
  "days_per_week": 4,
  "price": "120.00",
  "currency": "EGP",
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

### Plan types & the CEO-defined duration rule

`plan_type` enum: `DAILY`, `WEEKLY`, `MONTHLY`, `TERM`.

**`duration_days` is CEO-defined for every type except DAILY.** The type is a label, not a fixed length:

| Plan type | duration_days rule | Examples (all valid) |
|---|---|---|
| `DAILY` | **Fixed: exactly 1** (schema + DB constraint) | DAILY + 1 |
| `WEEKLY` | CEO-defined, 1–730 | WEEKLY + 5, WEEKLY + 7, WEEKLY + 8, WEEKLY + 12 |
| `MONTHLY` | CEO-defined, 1–730 | MONTHLY + 30, MONTHLY + 45 |
| `TERM` | CEO-defined, 1–730 | TERM + 90, TERM + 120 |

- **Do NOT document or assume WEEKLY = 7, MONTHLY = 30, or TERM = 90.** Those are conventional examples only; the plan's `duration_days` field is the single source of truth for validity and renewal.
- `duration_days` bounds: 1 ≤ days ≤ **730** (`MAX_PLAN_DURATION_DAYS`). Server rejects values outside → `422`.

### `days_per_week` — the weekly usage-day allowance

`days_per_week` is the **maximum number of DISTINCT usage DAYS per calendar week (Mon–Sun, UTC)**. It is NOT a QR-scan count:

- 1 ≤ `days_per_week` ≤ 7 (`MAX_PLAN_DAYS_PER_WEEK`) — a week has only 7 days.
- Outbound + return QR scans on the same calendar day count as **ONE** usage day.
- Example: `days_per_week = 4` → Mon/Tue/Wed/Thu allowed, Fri rejected, even if the subscription has validity days and theoretical capacity left.
- **No rollover:** unused allowance does NOT carry into next week. Every Monday the allowance resets to `days_per_week`.
- **Subscription expiration always wins:** after `end_date` nothing is usable regardless of weekly allowance.

Full weekly-rule details and frontend display guidance: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

### Plan lifecycle

- Created `is_active: true` via `POST /subscription-plans` (CEO). Both `duration_days` and `days_per_week` are required.
- Toggled via `PATCH /subscription-plans/{id}/status` or `PATCH /subscription-plans/{id}` (`is_active`).
- Inactive plans cannot be selected for new subscriptions or renewals (`422`).
- **Editing `duration_days`/`days_per_week`/`price` affects FUTURE subscriptions only** — existing subscriptions keep the values **snapshotted at purchase** (`duration_days_snapshot`, `days_per_week_snapshot`, `price_snapshot`).

### Plan endpoints

| Endpoint | Roles |
|---|---|
| `POST /subscription-plans` | CEO |
| `GET /subscription-plans` | 🔓 public (non-CEO callers always receive active only; `is_active` filter honored only for CEO) |
| `GET /subscription-plans/{plan_id}` | 🔓 public |
| `PATCH /subscription-plans/{plan_id}` | CEO |
| `PATCH /subscription-plans/{plan_id}/status` | CEO |
| `GET /subscriptions/plans` | any authenticated — convenience: **array** of active plans for the purchase screen |

## 2. Subscription Model

`SubscriptionResponse`:

```json
{
  "id": 88,
  "student_id": 42,
  "plan_id": 5,
  "price_snapshot": "120.00",
  "currency": "EGP",
  "start_date": "2026-09-14",
  "end_date": "2026-09-20",
  "duration_days_snapshot": 7,
  "days_per_week_snapshot": 4,
  "payment_id": 400,
  "status": "PENDING",
  "created_at": "...",
  "updated_at": "...",
  "student": null,
  "plan": null,
  "payment": null
}
```

> Note: there is **no** `route_id`, `outbound_pickup_point_id`, `return_pickup_point_id`, or `return_pickup_mode` in the subscription contract anymore. Legacy fields were removed from all request/response schemas.

`SubscriptionDetailResponse` adds (populated on detail/list endpoints):

| Field | Type | Meaning |
|---|---|---|
| `plan_type` | string \| null | From the plan. |
| `price` | string \| null | Same as `price_snapshot`. |
| `payment_status` | string \| null | The linked payment's status. |
| `boarding_count` | int | Total successful scans. |
| `outbound_boarding_count` | int | Outbound scans. |
| `return_boarding_count` | int | Return scans. |
| `last_boarded_at` | datetime \| null | |
| `duration_days` | int \| null | Snapshot: validity in calendar days. |
| `days_per_week` | int \| null | Snapshot: weekly usage-day allowance. |
| `usage_days_this_week` | int \| null | **Distinct calendar days used this week (Mon–Sun, UTC)** — DAYS, not scans. |
| `remaining_usage_days_this_week` | int \| null | `max(0, days_per_week − usage_days_this_week)`. |
| `used_qr_usages` | int | Total successful QR scans (both directions). |
| `qr_usages_today` | int | Scans consumed today (max 2: one outbound + one return). |

**Semantics warning:** `usage_days_this_week` counts DAYS. One day with outbound + return = 1. `used_qr_usages` counts SCANS. Never mix them in UI labels.

## 3. End Date Calculation (exact rule)

```
end_date = start_date + duration_days - 1
```

Inclusive of the start date. A DAILY plan (`duration_days = 1`) is valid only on `start_date`. WEEKLY + 5 days starting Sep 14 → valid Sep 14–18.

`start_date` defaults to the current UTC date if omitted; a past `start_date` → `422`.

## 4. Subscription Lifecycle

```
POST /subscriptions (student)
        │
        ▼
   ┌─────────┐   payment verified (CEO/SUPERVISOR: PATCH /payments/{id}/verify)
   │ PENDING │───────────────────────────────┬──────────────►  ┌────────┐
   └────┬────┘                               │                 │ ACTIVE │
        │ student cancels (PENDING only)     │ end_date passed │        │
        ▼                                    ▼                 └───┬────┘
   ┌───────────┐                      auto-expiry on read/scan      │ PATCH /{id}/renew
   │ CANCELLED │                      (status → EXPIRED)             │ (creates new PENDING cycle)
   └───────────┘                                                    ▼
   (terminal)                                             new subscription: PENDING
```

- **PENDING → ACTIVE** happens exclusively when a CEO/SUPERVISOR verifies the subscription's payment (`PATCH /payments/{payment_id}/verify`).
- **Auto-expiry:** if `today > end_date`, an ACTIVE subscription is flipped to `EXPIRED` lazily whenever it is read or scanned. The frontend should treat any subscription whose `end_date` has passed as expired regardless of the reported status.
- **Cancellation:** student = own subscription while `PENDING` only; CEO = any non-terminal.
- **Uniqueness:** at most **one** PENDING/ACTIVE subscription per student (any date overlap → `409`).

## 5. Purchasing (Student)

`POST /api/v1/subscriptions` (STUDENT only) — full field table and examples in [API_REFERENCE.md — Subscriptions](API_REFERENCE.md#subscriptions).

The ENTIRE request:

```json
{
  "plan_id": 5,
  "start_date": "2026-09-15",
  "payment_method": "VODAFONE_CASH",
  "transaction_reference": "VF-123456789"
}
```

- `plan_id` — required, must be an ACTIVE plan.
- `start_date` — optional, defaults to today; cannot be in the past (`422`).
- `payment_method` — `CASH` (default), `VODAFONE_CASH`, or `INSTAPAY`.
- `transaction_reference` — **REQUIRED for digital methods** (`VODAFONE_CASH`, `INSTAPAY`) → `422` if missing. Optional/tolerated for `CASH`.
- **There is NO route, trip, or pickup-point field.** Do not send them; extra fields are ignored and never persisted.
- **Price is snapshotted** from the plan; the amount is server-calculated (client cannot set it).
- A payment record is auto-created: digital methods start as `SUBMITTED` (reference provided upfront); `CASH` starts `PENDING`.
- QR token is generated server-side and never needs client input.
- Response `201` with `status: "PENDING"`.

> **FLOW A (subscribe):** GET plans → choose plan → choose start date → choose payment method → (digital only) enter transaction reference → POST /subscriptions. Then, separately per day, use the reservation workflow (FLOW B in [RESERVATIONS.md](RESERVATIONS.md)).

## 6. Renewal & Cancellation

### Renew — `PATCH /subscriptions/{id}/renew` (owner student or CEO) → `201`

- New cycle starts at `end_date + 1` (bumped to today if in the past).
- Duration/days_per_week/price are re-snapshotted from the plan's **current** configuration.
- Old ACTIVE subscription is expired; the renewal starts `PENDING` with a `CASH` payment.
- Requires old status `ACTIVE`/`EXPIRED` and an active plan (`422` otherwise); overlap → `409`.

### Cancel — `PATCH /subscriptions/{id}/cancel` → `200`

- Student: own + `PENDING` only (`422` otherwise).
- CEO: `PENDING`/`ACTIVE` (terminal statuses → `422`).

## 7. Listing Endpoints

| Endpoint | Roles | Filters |
|---|---|---|
| `GET /subscriptions/my` | STUDENT | `page`, `page_size`, `status` |
| `GET /subscriptions` | CEO | `page`, `page_size`, `student_id`, `university_id`, `route_id` (legacy rows only), `plan_type`, `status`, `start_date_from/to`, `end_date_from/to` |
| `GET /subscriptions/{id}` | CEO / route-assigned supervisor / owner | — |
| `GET /subscriptions/{id}/history` | same | `page`, `page_size` (default 50); returns a plain array |

All detail/list payloads are `SubscriptionDetailResponse` (weekly usage fields included).

## 8. QR Credential

`GET /subscriptions/{id}/qr` — owner student, ACTIVE subscription only → `SubscriptionQRResponse`:

```json
{
  "subscription_id": 88,
  "plan_type": "WEEKLY",
  "valid_from": "2026-09-14",
  "valid_until": "2026-09-20",
  "qr_payload": "ra7al://subscription/<opaque-token>",
  "status": "ACTIVE"
}
```

Render `qr_payload` as a QR image. **Important:** a valid QR credential is necessary but NOT sufficient for boarding — the student must also have a confirmed daily reservation for the trip being scanned. Complete usage rules: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

## 9. Frontend Notes

- Display subscription state from `status` + `payment_status` + dates; do not compute validity client-side beyond the simple `today > end_date` check (the server is authoritative).
- The weekly usage block (`days_per_week` / `usage_days_this_week` / `remaining_usage_days_this_week`) is the **only** sanctioned source for weekly-limit UI — label them as DAYS. Raw scan counters (`used_qr_usages`, `qr_usages_today`) are for history/detail views only.
- After purchase, the subscription stays PENDING until an admin verifies payment; build the UI to reflect "awaiting payment verification" via `payment_status`.
- The purchase screen does NOT ask for route/trip/pickup points anymore. Remove those pickers from the subscribe flow.
