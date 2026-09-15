# Payments (Post-Refactor)

Verified against `app/api/v1/payments.py`, `app/services/payment_service.py`, and the `Payment` model.

Payments are created automatically with each subscription request. **Reservation payments are retired** — trips no longer carry a fare; transportation is covered by the subscription.

---

## 1. Payment Model

`PaymentResponse`:

```json
{
  "id": 301,
  "reservation_id": null,
  "subscription_id": 9,
  "student_id": 42,
  "amount": "750.00",
  "currency": "EGP",
  "method": "VODAFONE_CASH",
  "status": "SUBMITTED",
  "transaction_reference": "VC-123456789",
  "receipt_image_path": "uploads/payment_receipts/6f2a….png",
  "notes": null,
  "paid_at": "2026-09-10T12:05:00Z",
  "verified_at": null,
  "verified_by": null,
  "created_at": "…",
  "updated_at": "…",
  "subscription": { "…": "SubscriptionResponse or null" },
  "student": { "…": "UserResponse" },
  "verifier": { "…": "UserResponse or null" }
}
```

| Field | Notes |
|---|---|
| `subscription_id` | Set for subscription payments (the only kind created today). |
| `amount` | Server-derived from the plan price. The client never sets it. |
| `method` | `VODAFONE_CASH`, `INSTAPAY`, or `CASH`. |
| `transaction_reference` | REQUIRED for digital methods (`VODAFONE_CASH`, `INSTAPAY`); optional/tolerated for CASH. |
| `receipt_image_path` | Object reference in the PRIVATE `payment-receipts` storage namespace. REQUIRED for digital methods before verification. |
| `status` | Lifecycle below. |

## 2. Status Lifecycle

```
PENDING ──(receipt uploaded + reference set)──► SUBMITTED ──(admin verify)──► VERIFIED
   │                                                │
   └──────────────────── admin cancel ──────────────┴──► CANCELLED / REJECTED (terminal)
```

- Digital payments are born **PENDING** and advance to `SUBMITTED` when the receipt image is uploaded (the reference is provided at subscription time).
- `VERIFIED`, `REJECTED`, `CANCELLED` are terminal.
- At most one active payment per subscription (partial unique index → `409`).

## 3. Digital payment receipt (REQUIRED)

For digital methods the student MUST provide **both**:

1. `transaction_reference` (payment code) — at subscription creation,
2. a receipt image — uploaded after creation.

### Upload

`POST /api/v1/payments/{payment_id}/receipt` (owner STUDENT only, multipart):

```
image: (binary) — JPEG / PNG / WEBP, ≤ 5 MB
```

Response `201`:

```json
{
  "payment_id": 301,
  "receipt_image_path": "uploads/payment_receipts/6f2a….png",
  "status": "SUBMITTED",
  "message": "Payment receipt uploaded successfully"
}
```

Rules:

- Only the payment's owner student can upload (`403` otherwise).
- Only digital methods accept receipts (`422` for CASH).
- Only while the payment is `PENDING`/`SUBMITTED`.
- Invalid files (wrong type, executable content, > 5 MB) are rejected with `422`.
- The image is stored via the storage abstraction in the **private** `payment-receipts` bucket (Supabase) or the local `uploads/payment_receipts/` directory in development.

### View (authorized backend flow only)

`GET /api/v1/payments/{payment_id}/receipt`

- Accessible to the owner student, and to CEO/SUPERVISOR for review.
- Streams the image (`image/png` etc.) — **never** a public URL. Access is re-checked on every request.
- `404` before any upload; `403` for unrelated students; `401` unauthenticated.

## 4. Endpoints

| Method | Path | Roles | Purpose |
|---|---|---|---|
| `POST /payments` | STUDENT | **Retired**: always `422` — payments are created with subscriptions. |
| `GET /payments/my` | STUDENT | Own payment history (`page`, `page_size`, `status`, `method`). |
| `GET /payments` | CEO, SUPERVISOR | All payments with filters. |
| `GET /payments/{payment_id}` | CEO, SUPERVISOR, owner student | Single payment. |
| `POST /payments/{payment_id}/receipt` | owner STUDENT | Upload the required digital receipt image. |
| `GET /payments/{payment_id}/receipt` | owner STUDENT, CEO, SUPERVISOR | Stream the receipt image (authorized flow). |
| `PATCH /payments/{payment_id}/submit` | owner STUDENT | Submit reference/notes; digital payments without a receipt stay `PENDING`. |
| `PATCH /payments/{payment_id}/cancel` | CEO, SUPERVISOR, owner student | Cancel an unsettled attempt. |
| `PATCH /payments/{payment_id}/verify` | CEO, SUPERVISOR | Verify: **requires reference + receipt for digital methods**; activates the subscription. |
| `PATCH /payments/{payment_id}/reject` | CEO, SUPERVISOR | Reject with optional reason. |

## 5. Subscription Activation Rule (critical)

`PATCH /payments/{payment_id}/verify` on a subscription payment:

1. For digital methods: rejects with `422` unless BOTH `transaction_reference` and `receipt_image_path` are present.
2. Validates the payment belongs to the subscription and is its current payment attempt.
3. If the subscription is `PENDING`:
   - `end_date` already passed → subscription set to `EXPIRED`.
   - otherwise → subscription set to **`ACTIVE`**.

This verify action is the **only** way a subscription becomes ACTIVE.

## 6. Frontend Flow (digital payment)

```
POST /subscriptions { plan_id, start_date, payment_method: "VODAFONE_CASH", transaction_reference: "VC-…" }
   → 201 { id, payment_id, status: "PENDING" }
   ↓
POST /payments/{payment_id}/receipt  (multipart image)
   → 201 { status: "SUBMITTED" }
   ↓
Wait for admin → poll GET /payments/my until VERIFIED/REJECTED
   ↓ VERIFIED
GET /subscriptions/{id} → status: "ACTIVE"
```

### Admin (CEO/SUPERVISOR)

```
GET /payments?status=SUBMITTED   (review queue)
GET /payments/{id}/receipt       (view the receipt image)
   ↓
PATCH /payments/{id}/verify      → VERIFIED (+ activates subscription)
   or
PATCH /payments/{id}/reject { rejection_reason }
```

## 7. Error Reference

| Status | Causes |
|---|---|
| 401 | Unauthenticated receipt access. |
| 403 | Acting on another student's payment; non-student uploading receipts; student attempting verify/reject. |
| 404 | Payment not found; receipt not uploaded yet. |
| 409 | Active payment already exists for the subscription. |
| 422 | Terminal-status actions; digital verify without reference or receipt; CASH receipt upload; invalid image file; retired reservation-payment creation. |
