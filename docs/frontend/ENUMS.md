# Enums Reference

All frontend-facing enums extracted verbatim from `app/models/enums.py` (single source of truth — schemas import from here). All values are strings, compared case-sensitively (send and expect them exactly as listed).

---

## RoleEnum

User roles (RBAC). Used on: `UserResponse.role`, login behavior, every role-restricted endpoint.

| Value | Meaning |
|---|---|
| `CEO` | Full administrative access |
| `SUPERVISOR` | Trip operations: QR scanning, rosters, assigned data |
| `STUDENT` | Self-service: subscriptions, reservations, QR, payments |

## UserStatus

Account lifecycle status. Used on: `UserResponse.status`, user filters, login gating.

| Value | Meaning | Can log in? |
|---|---|---|
| `PENDING` | Registered, awaiting CEO approval | No (403) |
| `APPROVED` | Active, approved by CEO | Yes |
| `REJECTED` | Rejected by CEO (see `rejection_reason`) | No (403) |
| `INACTIVE` | Deactivated by CEO | No (403) |
| `ACTIVE` | ⚠️ **Legacy input alias only** — the enum maps incoming `"ACTIVE"` to `APPROVED`. **Never** expect `ACTIVE` in responses; the API always returns `APPROVED`. | — |

## GenderEnum

Used on: registration, supervisor creation, `UserResponse.gender`.

| Value | Meaning |
|---|---|
| `MALE` | |
| `FEMALE` | |

## BusStatus

Bus operational status. Used on: `BusResponse.status`, `GET /buses?status=`.

| Value | Meaning |
|---|---|
| `ACTIVE` | In service (required for trip assignment) |
| `INACTIVE` | Out of service |
| `MAINTENANCE` | Under maintenance |

## TripStatus

Trip lifecycle. Used on: `TripResponse.status`, `GET /trips?status=`, status transitions.

| Value | Meaning |
|---|---|
| `SCHEDULED` | Bookable; accepts scans |
| `IN_PROGRESS` | Running; accepts scans |
| `COMPLETED` | Terminal |
| `CANCELLED` | Terminal |

Valid transitions (enforced server-side): `SCHEDULED → IN_PROGRESS | CANCELLED`; `IN_PROGRESS → COMPLETED | CANCELLED`.

## ReservationStatus

Used on: `ReservationResponse.status`, reservation filters.

| Value | Meaning |
|---|---|
| `CONFIRMED` | Seat held |
| `CANCELLED` | Released (terminal) |

## PaymentMethod

Used on: `PaymentResponse.method`, payment create/submit, subscription purchase (`payment_method`), payment filters (`method`).

| Value | Meaning |
|---|---|
| `VODAFONE_CASH` | Digital wallet — requires transaction reference when submitting |
| `INSTAPAY` | Digital transfer — requires transaction reference when submitting |
| `CASH` | Physical cash — reference optional |

## PaymentStatus

Payment lifecycle. Used on: `PaymentResponse.status`, `payment_status` on subscription details, roster entries, payment filters.

| Value | Meaning |
|---|---|
| `PENDING` | Awaiting proof/reference |
| `SUBMITTED` | Proof/reference submitted, awaiting verification |
| `VERIFIED` | Verified by CEO/SUPERVISOR (terminal; activates subscriptions) |
| `REJECTED` | Rejected by admin (terminal) |
| `CANCELLED` | Cancelled (terminal) |

## SubscriptionPlanType

Plan duration label. Used on: `SubscriptionPlanResponse.plan_type`, plan filters, roster/QR payloads.

| Value | Meaning |
|---|---|
| `DAILY` | Fixed: `duration_days` = exactly 1 |
| `WEEKLY` | **CEO-defined duration** (1–730) — do NOT assume 7 |
| `MONTHLY` | **CEO-defined duration** (1–730) |
| `TERM` | **CEO-defined duration** (1–730) |

The plan's `duration_days` field — not the type — determines validity (`end_date = start_date + duration_days − 1`) and QR allowance (`duration_days × 2`).

## SubscriptionStatus

Subscription lifecycle. Used on: `SubscriptionResponse.status`, QR credential, subscription filters.

| Value | Meaning |
|---|---|
| `PENDING` | Created; waiting for payment verification |
| `ACTIVE` | Payment verified; QR usable |
| `EXPIRED` | `end_date` passed (auto-set) or superseded by renewal |
| `CANCELLED` | Cancelled (terminal) |

## BoardingDirection

Travel direction. Used on: `POST /boarding/scan` request, boarding records/history, CEO record filters.

| Value | Meaning |
|---|---|
| `OUTBOUND` | Going trip scan |
| `RETURN` | Return trip scan |

## ReturnPickupMode

How the return pickup point is chosen at subscription purchase. Used on: `SubscriptionCreateRequest.return_pickup_mode`, `SubscriptionResponse.return_pickup_mode`.

| Value | Meaning |
|---|---|
| `SAME_AS_OUTBOUND` | Return point = outbound point (default) |
| `DIFFERENT` | Requires explicit `return_pickup_point_id` |

---

## Not Enums (but constrained values worth knowing)

| Concept | Values / range | Where |
|---|---|---|
| Plan `currency` | `"EGP"` (default; any 3-char string accepted) | Plans, subscriptions, payments |
| `duration_days` | Integer 1–730 (DAILY: exactly 1) | Plans |
| Bus `capacity` / trip `passenger_capacity` | Integer 1–150 | Buses, trips |
| Bus `year` | Integer 1990–2050 | Buses |
| Station `latitude` / `longitude` | −90…90 / −180…180 | Stations |
| ID-card upload MIME | `image/jpeg`, `image/png`, `image/webp` | Uploads |
| QR payload prefix | `ra7al://subscription/<token>` | QR credential |

## Query-Parameter Enum Usage

Several list endpoints accept enum values as filters — pass the exact string:

```
GET /api/v1/users?role=STUDENT&status=PENDING
GET /api/v1/buses?status=MAINTENANCE
GET /api/v1/trips?status=SCHEDULED
GET /api/v1/reservations?status=CONFIRMED
GET /api/v1/reservations/my?status=CANCELLED
GET /api/v1/payments?method=INSTAPAY&status=SUBMITTED
GET /api/v1/subscriptions?plan_type=WEEKLY&status=ACTIVE
GET /api/v1/boarding/records?direction=OUTBOUND
```
