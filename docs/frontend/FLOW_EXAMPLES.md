# End-to-End Flow Examples

Complete request sequences per role, using only actual endpoints and fields. `{TOKEN}` = bearer access token.

> **v2 contract reminder:** subscribing (FLOW A) and daily transportation selection (FLOW B) are SEPARATE workflows. A subscription contains NO route/trip/pickup-point data.

---

## 1. Student Flow

### Registration → Pending

```
1. GET  /api/v1/universities?is_active=true          → pick university_id
2. POST /api/v1/auth/upload-id-card                  (multipart, field "file")
   ← 201 { "image_path": "uploads/id_cards/6f1c9e2a8b7d4f0c.png" }
3. POST /api/v1/auth/register
   { "full_name": "Ahmed Ali",
     "phone_number": "+201012345678",
     "password": "SecurePass123!",
     "gender": "MALE",
     "university_id": 1,
     "faculty": "Faculty of Engineering",
     "academic_year": "3rd Year",
     "university_id_card_image": "uploads/id_cards/6f1c9e2a8b7d4f0c.png" }
   ← 201 { "status": "PENDING", "is_active": false, "message": "Registration submitted. Your account is pending CEO approval." }
4. Show "pending approval" screen. Login attempts now return 403 "Account is pending CEO approval."
```

### CEO Approval (external to the student) → Login

```
CEO: PATCH /api/v1/users/{user_id}/approve            → PENDING → APPROVED
5. POST /api/v1/auth/login   (form-urlencoded: username=+201012345678&password=…)
   ← 200 { "access_token": "<JWT>", "token_type": "bearer" }
6. GET  /api/v1/auth/me                               → role: STUDENT
```

### FLOW A — Subscribe to a Plan (NO route, NO trip, NO pickup points)

```
7. GET  /api/v1/subscriptions/plans                   → active plans array
   ← [ { "id": 5, "name": "Weekly Standard", "plan_type": "WEEKLY",
         "duration_days": 7, "days_per_week": 4, "price": "120.00",
         "currency": "EGP", ... } ]
   → the student picks ONLY: plan + start date + payment method
8. POST /api/v1/subscriptions
   { "plan_id": 5,
     "start_date": "2026-09-14",
     "payment_method": "VODAFONE_CASH",
     "transaction_reference": "VC-123456789" }       // required for digital methods
   ← 201 { "id": 88, "status": "PENDING", "price_snapshot": "120.00",
           "duration_days_snapshot": 7, "days_per_week_snapshot": 4,
           "start_date": "2026-09-14", "end_date": "2026-09-20", ... }
   // Cash: { "plan_id": 5, "payment_method": "CASH" } is enough
   // Admin verifies the payment → subscription becomes ACTIVE
```

### FLOW B — Daily Transportation Selection (requires ACTIVE subscription)

```
9. GET  /api/v1/reservations/upcoming-trips          (STUDENT)
   ← ALL upcoming SCHEDULED trips (not only tomorrow): direction OUTBOUND/RETURN,
     ordered "stops" with per-stop departure times, capacity, available_seats,
     "booking_state": "AVAILABLE" | "BOOKED" | "FULL",
     destination per direction (OUTBOUND → the student's university;
     RETURN → null until a drop-off point is selected)
   → let the student pick ONE OUTBOUND trip (selecting a pickup point from the
     trip's stops) and/or ONE RETURN trip (selecting a drop-off point from its stops)
10. POST /api/v1/reservations
   { "trip_id": 55,
     "selected_pickup_point_id": 9,        // ← one of the trip's TripStops
     "service_date": "2026-09-20" }        // optional; defaults to TOMORROW
   ← 201 { "id": 101, "service_date": "2026-09-20", "direction": "OUTBOUND",
           "status": "CONFIRMED", "origin": "Al-Mahatta",
           "destination": "Assiut National University", ... }
   // Max one OUTBOUND + one RETURN per student per service date (409 on a
   // second same-direction booking); other direction stays bookable
   // A point that is not one of the trip's stops → 422
   // No ACTIVE subscription covering the service date → 422
   // Trip FULL and allow_overbooking=false → 409
   // Change of mind: PUT /api/v1/reservations/my/selection with the same body
```

### View Subscription & QR

```
11. GET /api/v1/subscriptions/88
   ← 200 { "status": "ACTIVE", "payment_status": "VERIFIED",
           "duration_days": 7, "days_per_week": 4,
           "usage_days_this_week": 0, "remaining_usage_days_this_week": 4,
           "used_qr_usages": 0, "qr_usages_today": 0, ... }
12. GET /api/v1/subscriptions/88/qr
   ← 200 { "qr_payload": "ra7al://subscription/Xk9fQ2s...", "valid_from": "2026-09-14",
           "valid_until": "2026-09-27", "status": "ACTIVE", ... }
   → render qr_payload as QR image (a QR alone is NOT enough to board —
     the daily reservation from step 10 is also required)
```

### Outbound Boarding (supervisor scans, real-time on the travel day)

```
13. Supervisor: POST /api/v1/boarding/scan
    { "qr_token": "ra7al://subscription/Xk9fQ2s...", "trip_id": 55,
      "direction": "OUTBOUND", "pickup_point_id": 9 }
    ← 200 { "success": true, "message": "Boarding verified successfully",
            "student": { "id": 42, "full_name": "Ahmed Ali", ... },
            "usage_days_this_week": 1, "remaining_usage_days_this_week": 3,
            "boarded_at": "…" }
```

### Return Boarding

```
14. POST /api/v1/boarding/scan (same token, direction "RETURN", return pickup point)
    ← 200 BoardingResponse
    // usage_days_this_week stays 1: outbound + return on the SAME day = ONE usage day
```

### Daily Scan Limit

```
15. Third scan attempt the same calendar day (any trip/direction):
    ← 422 { "detail": "Daily QR limit reached: at most 2 scans per day (one outbound and one return)" }
```

### Weekly Usage-Day Limit (days_per_week = 4)

```
16. Student uses Mon, Tue, Wed, Thu (out + return each day)
    → usage_days_this_week = 4, remaining_usage_days_this_week = 0
17. Friday scan attempt:
    ← 422 { "detail": "Weekly usage limit reached: the subscription allows at most 4 usage days per week and all of them have been consumed. Unused weekly allowance does not roll over." }
18. Next Monday:
    → usage_days_this_week resets to 0, allowance is 4 again (NO rollover)
```

### Renewal / Expiry

```
19. After end_date: GET /subscriptions/88 → status "EXPIRED" (auto-set)
    // Expiration always wins over remaining weekly allowance
20. PATCH /api/v1/subscriptions/88/renew
    ← 201 new subscription { "status": "PENDING", "start_date": "2026-09-21", "end_date": "2026-09-27" }
```

---

## 2. CEO Flow

```
1. POST /api/v1/auth/login                            → token (role CEO)
2. GET  /api/v1/users/pending                         → approval queue
3. GET  /api/v1/users/{user_id}/id-card               → verify ID card (blob)
4. PATCH /api/v1/users/{user_id}/approve              → student activated
   (or PATCH /users/{user_id}/reject { "reason": "…" })

Fleet & network setup:
5. POST /api/v1/universities { "name": "Cairo University" }        (if needed)
6. POST /api/v1/stations { "name": "Main Campus Gate", "code": "ST-CAMPUS-01",
                           "latitude": 30.0444, "longitude": 31.2357 }
   // Stations are standalone depot/landmark records (they keep coordinates);
   // they are NOT linked to routes anymore
7. POST /api/v1/routes { "name": "Route A" }
   // A route is ONLY a named container of pickup points — no origin,
   // destination, distance, duration, or supervisor
8. POST /api/v1/routes/10/pickup-points { "name": "Al-Mahatta", "sequence": 1 }
   POST /api/v1/routes/10/pickup-points { "name": "Al-Walidiyah", "sequence": 2 }
   // PickupPoint belongs to exactly ONE route; no latitude/longitude

Bus with image:
9. POST /api/v1/buses   (multipart: bus_number, license_plate, capacity, image)
   ← 201 BusResponse { "image_url": "uploads/bus_images/9ab7d3e1.png", "status": "ACTIVE" }
   // Without an image part → "image_url": null

Supervisor & trip:
10. POST /api/v1/users/supervisors { "full_name": "Sara Supervisor",
        "phone_number": "+201098765432", "password": "SuperSecret123!", "gender": "FEMALE" }
11. GET  /api/v1/routes/10/pickup-points       → the route's points to select from
12. POST /api/v1/trips
    { "route_id": 10, "direction": "OUTBOUND", "bus_id": 3, "supervisor_id": 7,
      "stops": [
        { "pickup_point_id": 9,  "stop_order": 1, "departure_time": "2026-09-20T06:30:00Z" },
        { "pickup_point_id": 10, "stop_order": 2, "departure_time": "2026-09-20T06:40:00Z" } ],
      "passenger_capacity": 45, "allow_overbooking": false }
    ← 201 TripResponse (departure_time = first stop time,
       estimated_arrival_time = last stop time; no fare)
    // 409 here = bus or supervisor has an overlapping trip
    // 422 if a stop references a point from another route or duplicates onePlan with CEO-defined duration AND weekly usage-day allowance:
13. POST /api/v1/subscription-plans
    { "name": "Weekly Standard", "plan_type": "WEEKLY", "duration_days": 7,
      "days_per_week": 4, "price": "120.00" }
    // duration_days is CEO-defined (1–730; DAILY fixed at 1)
    // days_per_week = max DISTINCT usage DAYS per week (1–7)
    // e.g. WEEKLY+5, WEEKLY+12, MONTHLY+45, TERM+90 are all valid

Payment verification (activates student subscriptions):
14. GET  /api/v1/payments?status=PENDING
    // digital payments (VODAFONE_CASH/INSTAPAY) stay PENDING until the student
    // uploads the receipt: POST /api/v1/payments/{id}/receipt (multipart image)
    // upload sets status SUBMITTED + requires the transaction_reference

Monitoring:
16. GET /api/v1/boarding/records?student_id=42         (paginated, CEO only)
17. GET /api/v1/subscriptions?status=ACTIVE&plan_type=WEEKLY
18. GET /api/v1/trips/history                          → completed trips (RBAC-scoped)
```

---

## 3. Supervisor Flow

```
1. POST /api/v1/auth/login                            → token (role SUPERVISOR)
   // Supervisor accounts are created by the CEO and are immediately APPROVED

2. GET  /api/v1/trips?supervisor_id={me}&status=SCHEDULED   → assigned trips
3. GET  /api/v1/trips/55                              → full trip incl. route/bus
4. GET  /api/v1/buses/3/image/metadata                → { "has_image": true,
                                                        "image_stream_url": "/api/v1/buses/3/image" }
5. GET  /api/v1/buses/3/image (blob)                  → display bus photo
   // Allowed: supervisor is assigned to a trip using this bus

6. GET  /api/v1/trips/55/stops                        → ordered stop sequence
7. GET  /api/v1/boarding/trips/55/students            → roster (students who
   booked this trip for its service date)
   ← [ { "student_id": 42, "student_name": "Ahmed Ali", "subscription_id": 88,
         "service_date": "2026-09-20", "direction": "OUTBOUND",
         "selected_point": "Al-Mahatta", "outbound_boarded": false,
         "return_boarded": false, "payment_status": "VERIFIED", ... } ]

8. POST /api/v1/boarding/scan   (per boarding; 60 scans/min limit)
   { "qr_token": "ra7al://subscription/…", "trip_id": 55,
     "direction": "OUTBOUND", "pickup_point_id": 9 }
   ← 200 BoardingResponse | 409 duplicate | 422 weekly-limit / no-selection / invalid

9. Refetch roster → "outbound_boarded": true
10. GET /api/v1/boarding/trips/55/records             → audit log of scans
```

Supervisor boundaries: cannot scan for trips they aren't assigned to (403), cannot advance trip status (CEO-only), cannot view ID cards or system-wide boarding records.
