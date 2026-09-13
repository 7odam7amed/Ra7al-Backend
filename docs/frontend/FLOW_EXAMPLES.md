# End-to-End Flow Examples

Complete request sequences per role, using only actual endpoints and fields. `{TOKEN}` = bearer access token.

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

### Browse & Purchase a Subscription

```
7. GET  /api/v1/routes?is_active=true                 → choose route_id (e.g. 10)
8. GET  /api/v1/subscriptions/plans                   → active plans array
   ← [ { "id": 5, "name": "Weekly Standard", "plan_type": "WEEKLY",
         "duration_days": 7, "price": "120.00", "currency": "EGP", ... } ]
9. POST /api/v1/subscriptions
   { "route_id": 10, "plan_id": 5,
     "outbound_pickup_point_id": 9,
     "return_pickup_mode": "SAME_AS_OUTBOUND",
     "payment_method": "VODAFONE_CASH",
     "transaction_reference": "VC-123456789" }
   ← 201 { "id": 88, "status": "PENDING", "price_snapshot": "120.00",
           "start_date": "2026-09-14", "end_date": "2026-09-20", ... }
   // Admin verifies the payment → subscription becomes ACTIVE
```

### View Subscription & QR

```
10. GET /api/v1/subscriptions/88
   ← 200 { "status": "ACTIVE", "payment_status": "VERIFIED",
           "duration_days": 7, "max_qr_usages": 14, "used_qr_usages": 0,
           "remaining_qr_usages": 14, "qr_usages_today": 0, ... }
11. GET /api/v1/subscriptions/88/qr
   ← 200 { "qr_payload": "ra7al://subscription/Xk9fQ2s...", "valid_from": "2026-09-14",
           "valid_until": "2026-09-20", "status": "ACTIVE", ... }
   → render qr_payload as QR image
```

### Outbound Boarding (supervisor scans)

```
12. Supervisor: POST /api/v1/boarding/scan
    { "qr_token": "ra7al://subscription/Xk9fQ2s...", "trip_id": 55,
      "direction": "OUTBOUND", "pickup_point_id": 9 }
    ← 200 { "success": true, "message": "Boarding verified successfully",
            "student": { "id": 42, "full_name": "Ahmed Ali", ... }, "boarded_at": "…" }
```

### Return Boarding

```
13. POST /api/v1/boarding/scan (same token, direction "RETURN", return pickup point)
    ← 200 BoardingResponse
```

### Daily Limit

```
14. Third scan attempt the same calendar day (any trip/direction):
    ← 422 { "detail": "Daily QR usage limit reached: at most 2 QR usages per day (one outbound and one return)" }
```

### Remaining Allowance

```
15. GET /api/v1/subscriptions/88
    ← "used_qr_usages": 2, "remaining_qr_usages": 12, "qr_usages_today": 2
    → UI: "QR remaining: 12 / 14" · "Used today: 2 / 2"
    // Unused calendar days never consume allowance; refetch after each scan.
```

### Renewal / Expiry

```
16. After end_date: GET /subscriptions/88 → status "EXPIRED" (auto-set)
17. PATCH /api/v1/subscriptions/88/renew
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
7. POST /api/v1/routes { "route_number": "R-101", "name": "Campus Express",
                         "origin_station_id": 1, "destination_station_id": 2,
                         "distance_km": 15.5, "estimated_duration_minutes": 35 }
8. POST /api/v1/routes/10/stops { "station_id": 4, "stop_order": 1 }
   POST /api/v1/routes/10/stops { "station_id": 5, "stop_order": 2 }
   (or batch: PATCH /api/v1/routes/10/stops/reorder)

Bus with image:
9. POST /api/v1/buses   (multipart: bus_number, license_plate, capacity, image)
   ← 201 BusResponse { "image_url": "uploads/bus_images/9ab7d3e1.png", "status": "ACTIVE" }
   // Without an image part → "image_url": null

Supervisor & trip:
10. POST /api/v1/users/supervisors { "full_name": "Sara Supervisor",
        "phone_number": "+201098765432", "password": "SuperSecret123!", "gender": "FEMALE" }
11. POST /api/v1/trips { "route_id": 10, "bus_id": 3, "supervisor_id": 7,
        "departure_time": "2026-09-15T07:30:00Z",
        "estimated_arrival_time": "2026-09-15T08:05:00Z",
        "pickup_points": [ { "name": "Cairo University Gate 3", "sequence": 1 } ] }
    // 409 here = bus or supervisor has an overlapping trip

Plan with CEO-defined duration:
12. POST /api/v1/subscription-plans
    { "name": "Weekly Standard", "plan_type": "WEEKLY", "duration_days": 7, "price": "120.00" }
    // duration_days is CEO-defined (1–730; DAILY fixed at 1)
    // e.g. WEEKLY+5, WEEKLY+12, MONTHLY+45, TERM+90 are all valid

Payment verification (activates student subscriptions):
13. GET  /api/v1/payments?status=SUBMITTED
14. PATCH /api/v1/payments/{payment_id}/verify         → subscription PENDING → ACTIVE

Monitoring:
15. GET /api/v1/boarding/records?student_id=42         (paginated, CEO only)
16. GET /api/v1/subscriptions?status=ACTIVE&plan_type=WEEKLY
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

6. GET  /api/v1/trips/55/pickup-points                → scan form options
7. GET  /api/v1/boarding/trips/55/students            → roster
   ← [ { "student_id": 42, "student_name": "Ahmed Ali", "subscription_id": 88,
         "outbound_pickup": "Cairo University Gate 3", "outbound_boarded": false,
         "return_boarded": false, "payment_status": "VERIFIED", ... } ]

8. POST /api/v1/boarding/scan   (per boarding; 60 scans/min limit)
   { "qr_token": "ra7al://subscription/…", "trip_id": 55,
     "direction": "OUTBOUND", "pickup_point_id": 9 }
   ← 200 BoardingResponse | 409 duplicate | 422 limit/invalid

9. Refetch roster → "outbound_boarded": true
10. GET /api/v1/boarding/trips/55/records             → audit log of scans
```

Supervisor boundaries: cannot scan for trips they aren't assigned to (403), cannot advance trip status (CEO-only), cannot view ID cards or system-wide boarding records.
