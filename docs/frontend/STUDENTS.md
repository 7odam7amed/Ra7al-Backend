# Students

The student-facing domain: registration, approval, profile data, subscriptions, reservations, and QR boarding. The full lifecycle in one picture:

```
Register            POST /api/v1/auth/upload-id-card  (public)
   │                POST /api/v1/auth/register        (public) → status PENDING
   ▼
Pending approval    login blocked (403)
   │
   ▼  CEO: PATCH /api/v1/users/{user_id}/approve
Approved            login OK → GET /auth/me (role STUDENT)
   │
   ▼
Browse & buy        GET /api/v1/routes                (read-only)
                    GET /api/v1/subscription-plans    or /api/v1/subscriptions/plans
                    POST /api/v1/subscriptions        → subscription PENDING + payment
   │
   ▼  Payment verified (CEO/SUPERVISOR): PATCH /api/v1/payments/{id}/verify
Subscription ACTIVE GET /api/v1/subscriptions/{id}/qr → QR credential
   │
   ▼
Board buses         supervisor scans QR (POST /api/v1/boarding/scan)
                    2 scans/day max (1 outbound + 1 return)
   │
   ▼
Renew / expire      PATCH /api/v1/subscriptions/{id}/renew
                    auto-EXPIRED after end_date
```

## 1. Registration & Profile

- Registration fields, ID-card upload, and status semantics: [AUTHENTICATION.md](AUTHENTICATION.md).
- The student profile fields (`faculty`, `academic_year`, `university_id`, `university_id_card_image`) are set at registration; only the CEO can modify them afterwards (`PATCH /users/{user_id}`). There is **no self-service profile edit endpoint** for students in the current API.
- Rejection (with reason) and deactivation are CEO actions.

## 2. University Information

- `GET /api/v1/universities` and `GET /api/v1/universities/{id}` are **public** (no auth) — use them to populate the registration form's university picker (filter client-side by `is_active: true`, or pass `?is_active=true`).
- `university_id` must reference an active university at registration time.

## 3. ID Card

- Uploaded before registration (`POST /auth/upload-id-card` → `image_path`).
- Visible only to the owner and the CEO via `GET /users/{user_id}/id-card` or the signed-URL endpoint. Supervisors cannot view ID cards.

## 4. Subscriptions

- Purchase with `POST /subscriptions` (STUDENT only). The subscription starts `PENDING` and becomes `ACTIVE` only when its payment is verified by a CEO/SUPERVISOR.
- View own list: `GET /subscriptions/my` (includes `duration_days`, `max_qr_usages`, `used_qr_usages`, `remaining_qr_usages`, `qr_usages_today`).
- Details: [SUBSCRIPTIONS.md](SUBSCRIPTIONS.md). QR display and rules: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).

## 5. Reservations

- A reservation books a **seat on one scheduled trip** (`POST /reservations { trip_id }`), separate from the route subscription.
- Trips available for booking: `GET /reservations/available-trips`.
- Details: [RESERVATIONS.md](RESERVATIONS.md).

## 6. Payments

- Subscription purchase auto-creates a payment record. Extra payment attempts for reservations: `POST /payments`.
- Students submit references and track status via `GET /payments/my`; verification is administrative.
- Details: [PAYMENTS.md](PAYMENTS.md).

## 7. QR Usage & Boarding

- The QR credential is fetched by the student and shown as a QR image; the **supervisor** scans it.
- Usage accounting fields and all error states: [QR_AND_BOARDING.md](QR_AND_BOARDING.md).
- The student never calls `/boarding/scan` — it is supervisor-only.

## 8. What Students CANNOT Do (verified)

- List buses (`GET /buses` → 403); they may only fetch the image of a bus they hold a CONFIRMED reservation on.
- Manage routes/stations/trips/pickup points/plans (read-only for routes and plans).
- See other students' data; no admin listings.
- Cancel a subscription after it leaves PENDING.
- Access system-wide boarding records.
