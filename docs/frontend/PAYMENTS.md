# Payments

Verified against `app/api/v1/payments.py`, `app/services/payment_service.py`, the `Payment` model, and `app/models/enums.py`. **Payment functionality exists** — for both trip reservations and route subscriptions.

---

## 1. Payment Model

`PaymentResponse`:

```json
{
  "id": 301,
  "reservation_id": 101,
  "subscription_id": null,
  "student_id": 42,
  "amount": "50.00",
  "currency": "EGP",
  "method": "VODAFONE_CASH",
  "status": "SUBMITTED",
  "transaction_reference": "VC-123456789",
  "notes": "Paid via Vodafone Cash number 01012345678",
  "paid_at": "2026-09-10T12:05:00Z",
  "verified_at": null,
  "verified_by": null,
  "created_at": "…",
  "updated_at": "…",
  "reservation": { "…": "ReservationResponse or null" },
  "student": { "…": "UserResponse" },
  "verifier": { "…": "UserResponse or null" }
}
```

| Field | Notes |
|---|---|
| `reservation_id` / `subscription_id` | Exactly **one** must be set (DB constraint `chk_payment_target_exclusive`); the other is `null`. |
| `amount` | Server-derived: trip `fare_amount` for reservation payments, plan price for subscription payments. The client never sets it. |
| `currency` | Always `"EGP"`. |
| `method` | `VODAFONE_CASH`, `INSTAPAY`, or `CASH`. |
| `status` | Lifecycle below. |
| `transaction_reference` | ≤ 100 chars; optional for CASH, effectively required for digital methods. |
| `notes` | ≤ 500 chars; rejection reasons are appended here. |
| `paid_at` / `verified_at` / `verified_by` | Set by the server during submit/verify/reject. |

## 2. Status Lifecycle (exact transitions)

```
                 ┌──────────────────────────────────────────┐
                 │            (admin verify)                │
                 ▼                                          │
   ┌─────────┐  submit   ┌───────────┐  verify    ┌──────────┴─┐
   │ PENDING │─────────► │ SUBMITTED │──────────► │  VERIFIED  │ (terminal)
   └────┬────┘           └─────┬─────┘            └────────────┘
        │  admin verify        │  admin reject/cancel
        │      ┌───────────────┼──────────────┐
        ▼      ▼               ▼              ▼
  ┌──────────┐        ┌──────────┐    ┌───────────┐
  │ VERIFIED │        │ REJECTED │    │ CANCELLED │   (both terminal)
  └──────────┘        └──────────┘    └───────────┘
```

- `VERIFIED`, `REJECTED`, `CANCELLED` are **terminal** — any action on them → `422`.
- Transitions are enforced in `PaymentService.VALID_TRANSITIONS` and re-checked per endpoint.
- Uniqueness: at most one **active** (`PENDING`/`SUBMITTED`/`VERIFIED`) payment per reservation, and per subscription (partial unique indexes → `409` on violation).

## 3. Endpoints

| Method | Path | Roles | Purpose |
|---|---|---|---|
| `POST /payments` | STUDENT | Create a payment attempt for own CONFIRMED reservation. |
| `GET /payments/my` | STUDENT | Own payment history (`page`, `page_size`, `status`, `method`, `reservation_id`). |
| `GET /payments` | CEO, SUPERVISOR | All payments (`page`, `page_size`, `reservation_id`, `student_id`, `method`, `status`, `created_after`, `created_before`). |
| `GET /payments/{payment_id}` | CEO, SUPERVISOR, owner student | Single payment. |
| `PATCH /payments/{payment_id}/submit` | **owner STUDENT only** (route enforces `STUDENT_ONLY`; admins get 403) | Submit proof/reference: `PENDING → SUBMITTED`. |
| `PATCH /payments/{payment_id}/cancel` | CEO, SUPERVISOR, owner student | Cancel an unsettled attempt. |
| `PATCH /payments/{payment_id}/verify` | CEO, SUPERVISOR | Verify: settles the record; **activates the subscription** if it targets one. |
| `PATCH /payments/{payment_id}/reject` | CEO, SUPERVISOR | Reject with optional reason. |

## 4. Request Schemas

### `POST /payments` (`PaymentCreateRequest`)

```json
{
  "reservation_id": 101,
  "method": "VODAFONE_CASH",
  "transaction_reference": "VC-123456789",
  "notes": "Paid via Vodafone Cash 01012345678"
}
```

- `method` required; `transaction_reference`/`notes` optional.
- Server validations: reservation exists (`404`), belongs to the student (`403`), is `CONFIRMED` (`422`), trip not departed (`422`), no active payment on the reservation (`409`).
- Initial status: `SUBMITTED` (+`paid_at`) if method is digital **and** a reference was provided; otherwise `PENDING`.

### `PATCH /{id}/submit` (`PaymentSubmitRequest`)

```json
{ "transaction_reference": "IP-987654321", "notes": "optional" }
```

- Only from `PENDING` (`422` otherwise).
- For `VODAFONE_CASH`/`INSTAPAY`, a reference is required — the new one or one already stored on the payment — otherwise `422`.
- Sets `status: "SUBMITTED"`, `paid_at = now`.

### `PATCH /{id}/reject` (`PaymentRejectRequest`)

```json
{ "rejection_reason": "Transaction reference not found in statement" }
```

- Only from `PENDING`/`SUBMITTED`. Body optional. Reason is appended to `notes`; sets `verified_at`/`verified_by` to the admin.

## 5. Subscription Activation Rule (critical)

`PATCH /payments/{payment_id}/verify` on a **subscription** payment:

1. Validates the payment belongs to the subscription and is its current payment attempt.
2. If the subscription is `PENDING`:
   - `end_date` already passed → subscription set to `EXPIRED`.
   - otherwise → subscription set to **`ACTIVE`**.

This verify action is the **only** way a subscription becomes ACTIVE. Rejected/cancelled subscription payments leave the subscription PENDING (the student can retry by renewing or contacting the CEO).

## 6. Frontend Flow

### Student (reservation payment)

```
Book seat → POST /reservations → 201 (CONFIRMED)
   ↓
POST /payments { reservation_id, method, transaction_reference? } → 201
   ↓ status PENDING (or SUBMITTED if reference given for digital method)
If PENDING: PATCH /payments/{id}/submit { transaction_reference }
   ↓
Wait for admin → poll GET /payments/my until status VERIFIED/REJECTED
```

### Student (subscription payment)

Created automatically with the subscription (`POST /subscriptions`). If paid digitally with a reference at purchase time it starts `SUBMITTED`; otherwise the student waits for admin verification. Track via `payment_status` on `GET /subscriptions/{id}` / `GET /subscriptions/my`.

### Admin (CEO/SUPERVISOR)

```
GET /payments?status=SUBMITTED   (review queue)
   ↓
PATCH /payments/{id}/verify      → VERIFIED (+ activates subscription)
   or
PATCH /payments/{id}/reject { rejection_reason }
```

## 7. Error Reference

| Status | Causes |
|---|---|
| 403 | Acting on another student's payment/reservation; non-student creating/submitting; student attempting verify/reject |
| 404 | Payment/reservation/trip not found |
| 409 | Active payment already exists for the reservation/subscription |
| 422 | Terminal-status actions; submit without reference (digital); reservation not CONFIRMED; departed trip |
