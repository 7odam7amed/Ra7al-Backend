# Subscriptions & Subscription Plans

Verified against `app/api/v1/subscription_plans.py`, `app/api/v1/subscriptions.py`, `app/services/subscription_plan_service.py`, `app/services/subscription_service.py`, `app/models/subscription_plan.py` (including DB constraints), and `app/models/subscription.py`.

---

## 1. Subscription Plans

A plan is a purchasable package defined by a **type** and a **CEO-defined duration**.

`SubscriptionPlanResponse`:

```json
{
  "id": 5,
  "name": "Weekly Standard",
  "plan_type": "WEEKLY",
  "duration_days": 7,
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

- **Do NOT document or assume WEEKLY = 7.** 7 is just the conventional example; the plan's `duration_days` field is the single source of truth for validity, renewal, and QR allowance.
- `duration_days` bounds: 1 ≤ days ≤ **730** (`MAX_PLAN_DURATION_DAYS`). Server rejects values outside → `422`.
- Duplicate guard: same (plan_type, name, duration_days) already exists → `409`.
- `price`: Decimal > 0 (2 decimal places), `currency`: default `"EGP"`.

### Plan lifecycle

- Created `is_active: true` via `POST /subscription-plans` (CEO).
- Toggled via `PATCH /subscription-plans/{id}/status` or `PATCH /subscription-plans/{id}` (`is_active`).
- Inactive plans cannot be selected for new subscriptions or renewals (`422`).
- Editing `duration_days`/`price` affects **future** subscriptions only — existing subscriptions keep their start/end dates and their `price_snapshot`.

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
  "route_id": 10,
  "plan_id": 5,
  "price_snapshot": "120.00",
  "currency": "EGP",
  "start_date": "2026-09-14",
  "end_date": "2026-09-20",
  "outbound_pickup_point_id": 9,
  "return_pickup_point_id": 9,
  "return_pickup_mode": "SAME_AS_OUTBOUND",
  "payment_id": 400,
  "status": "PENDING",
  "created_at": "...",
  "updated_at": "...",
  "student": null,
  "route": null,
  "plan": null,
  "payment": null,
  "outbound_pickup_point": null,
  "return_pickup_point": null
}
```

`SubscriptionDetailResponse` adds (populated on detail/list endpoints):

| Field | Type | Meaning |
|---|---|---|
| `plan_type` | string \| null | From the plan. |
| `price` | string \| null | Same as `price_snapshot`. |
| `payment_status` | string \| null | The linked payment's status. |
| `boarding_count` | int | Total successful boardings (QR usages). |
| `outbound_boarding_count` | int | Outbound boardings. |
| `return_boarding_count` | int | Return boardings. |
| `last_boarded_at` | datetime \| null | |
| `duration_days` | int \| null | Plan duration (null only if plan was deleted). |
| `max_qr_usages` | int \| null | **`duration_days × 2`**. |
| `used_qr_usages` | int | Total QR usages consumed. |
| `remaining_qr_usages` | int \| null | `max(0, max − used)`. |
| `qr_usages_today` | int | Usages consumed today (server's UTC date). |

## 3. End Date Calculation (exact rule)

```
end_date = start_date + duration_days - 1
```

Inclusive of the start date. A DAILY plan (`duration_days = 1`) is valid only on `start_date`. WEEKLY + 5 days starting Sep 14 → valid Sep 14–18.

`start_date` defaults to the current UTC date if omitted; a past `start_date` → `422`. `service_date` is accepted as an alias and must equal `start_date` if both are sent.

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
- **Uniqueness:** at most **one** PENDING/ACTIVE subscription per (student, route). Overlap attempts → `409`.

## 5. Purchasing (Student)

`POST /api/v1/subscriptions` (STUDENT only) — full field table and examples in [API_REFERENCE.md — Subscriptions](API_REFERENCE.md#subscriptions).

Minimal request:

```json
{
  "route_id": 10,
  "plan_id": 5,
  "outbound_pickup_point_id": 9
}
```

Key server-side behaviors:
- Route and plan must be active; the outbound pickup point must belong to the chosen route (pickup points are per-trip → the frontend should let the student pick a trip's points; error `422` if the point isn't on the route).
- `return_pickup_mode`: `SAME_AS_OUTBOUND` (default) reuses the outbound point; `DIFFERENT` requires `return_pickup_point_id` (also on the route).
- **Price is snapshotted** from the plan; the amount is server-calculated (client cannot set it).
- A payment record is auto-created: digital methods (VODAFONE_CASH/INSTAPAY) with a `transaction_reference` start as `SUBMITTED`; otherwise `PENDING`.
- QR token is generated server-side and never needs client input.
- Response `201` with `status: "PENDING"`.

## 6. Renewal & Cancellation

### Renew — `PATCH /subscriptions/{id}/renew` (owner student or CEO) → `201`

- New cycle starts at `end_date + 1` (bumped to today if in the past).
- Duration from the plan's current `duration_days`; **price re-snapshotted** from the plan's current price.
- Old ACTIVE subscription is expired; the renewal starts `PENDING` with a `CASH` payment.
- Requires old status `ACTIVE`/`EXPIRED` and an active plan (`422` otherwise); overlap → `409`.

### Cancel — `PATCH /subscriptions/{id}/cancel` → `200`

- Student: own + `PENDING` only (`422` otherwise).
- CEO: `PENDING`/`ACTIVE` (terminal statuses → `422`).

## 7. Listing Endpoints

| Endpoint | Roles | Filters |
|---|---|---|
| `GET /subscriptions/my` | STUDENT | `page`, `page_size`, `status`, `route_id` |
| `GET /subscriptions` | CEO | `page`, `page_size`, `student_id`, `university_id`, `route_id`, `plan_type`, `status`, `start_date_from/to`, `end_date_from/to` |
| `GET /subscriptions/{id}` | CEO / route-assigned supervisor / owner | — |
| `GET /subscriptions/{id}/history` | same | `page`, `page_size` (default 50); returns a plain array |

All detail/list payloads are `SubscriptionDetailResponse` (QR accounting fields included).

## 8. QR Credential

`GET /subscriptions/{id}/qr` — owner student, ACTIVE subscription only → `SubscriptionQRResponse`:

```json
{
  "subscription_id": 88,
  "plan_type": "WEEKLY",
  "route_id": 10,
  "route_name": "Campus Express",
  "valid_from": "2026-09-14",
  "valid_until": "2026-09-20",
  "qr_payload": "ra7al://subscription/<opaque-token>",
  "status": "ACTIVE"
}
```

Render `qr_payload` as a QR image. Complete usage rules and display guidance: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

## 9. Frontend Notes

- Display subscription state from `status` + `payment_status` + dates; do not compute validity client-side beyond the simple `today > end_date` check (the server is authoritative).
- The QR usage block (`max/used/remaining/today`) is the **only** sanctioned source for usage UI — see the display recipe in [QR_AND_BOARDING.md](QR_AND_BOARDING.md).
- After purchase, the subscription stays PENDING until an admin verifies payment; build the UI to reflect "awaiting payment verification" via `payment_status`.
