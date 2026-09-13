# Users & User Management

Covers the CEO administrative user lifecycle: listing, approval, rejection, role/status changes, and student ID-card access. Auth endpoints themselves are in [AUTHENTICATION.md](AUTHENTICATION.md); the permissions matrix is in [RBAC.md](RBAC.md).

---

## 1. User Lifecycle

```
                 POST /auth/register (public, STUDENT only)
                              │
                              ▼
                       ┌──────────────┐
                       │   PENDING    │   is_active = false
                       └──────┬───────┘
              PATCH /users/{id}/approve
              (CEO)                    PATCH /users/{id}/reject (CEO)
                              │                    │
                              ▼                    ▼
                       ┌──────────────┐     ┌──────────────┐
                       │   APPROVED   │     │   REJECTED   │
                       │ is_active =  │     │ rejection_   │
                       │    true      │     │ reason set   │
                       └──────┬───────┘     └──────────────┘
              PATCH /users/{id}/status
              (CEO)        │
                   ┌───────┴────────┐
                   ▼                ▼
            ┌──────────────┐  ┌──────────────┐
            │ INACTIVE     │  │  APPROVED    │
            │ is_active =  │  │ (reactivate) │
            │    false     │  └──────────────┘
            └──────────────┘
```

- Only students self-register. Supervisors are created directly as `APPROVED` by the CEO (`POST /users/supervisors`).
- A rejected account **cannot** be approved later (`422`). Reactivation is via the status endpoint only for accounts that were deactivated (INACTIVE), not rejected.
- Login is blocked for every status except `APPROVED` (see [AUTHENTICATION.md](AUTHENTICATION.md)).

## 2. CEO Endpoints

All under `/api/v1/users`, all CEO-only except ID-card access.

| Endpoint | Purpose |
|---|---|
| `GET /users` | Paginated list with filters `role`, `is_active`, `status`. |
| `GET /users/pending` | Paginated list of `PENDING` accounts awaiting review. |
| `GET /users/{user_id}` | Single user details. |
| `PATCH /users/{user_id}` | Update `full_name`, `gender`, `phone_number`, `faculty`, `academic_year` (all optional). |
| `PATCH /users/{user_id}/role` | Change role — **only `STUDENT` ↔ `SUPERVISOR`**; assigning `CEO` returns 422. CEO cannot change their own role; the last active CEO cannot be demoted. |
| `PATCH /users/{user_id}/status` | Activate/deactivate (`is_active` and/or `status`). Last active CEO cannot be deactivated. |
| `PATCH /users/{user_id}/approve` | `PENDING → APPROVED` (sets active, clears rejection reason). |
| `PATCH /users/{user_id}/reject` | `PENDING → REJECTED` with optional `{ "reason": "..." }` (≤ 500 chars). |
| `POST /users/supervisors` | Create supervisor (`full_name`, `phone_number`, `password`, `gender`) — created `APPROVED` + active. |

Request/response schemas: [API_REFERENCE.md — Users](API_REFERENCE.md#users).

## 3. ID-Card Access (student identity verification)

The uploaded university ID-card image is private storage. Two access methods, both restricted to the **owner student** or the **CEO** (supervisors are always forbidden):

### Stream bytes

```
GET /api/v1/users/{user_id}/id-card
Authorization: Bearer <token>
```

Response: raw image bytes (`image/jpeg|png|webp`). Fetch as a blob and display via object URL.

### Temporary signed URL (production/Supabase only)

```
GET /api/v1/users/{user_id}/id-card/signed-url?expires_in=60
```

- `expires_in`: 1–300 seconds (default 60).
- Response: `{ "url": "...", "signed_url": "...", "expires_in": 60 }` — both fields hold the same URL.
- Returns **501** when the backend uses the local storage backend (development). Use the streaming endpoint in that case.
- The URL is usable directly in `<img src>` without auth, until it expires.

Errors for both: `403` (supervisor, or student accessing someone else's card), `404` (no user / no stored card).

## 4. Frontend Notes

- The CEO "pending approvals" screen should combine `GET /users/pending` with `GET /users/{id}/id-card` (blob preview) so the CEO can verify the ID card before approving/rejecting.
- `rejection_reason` from `UserResponse` should be shown to the student after a rejected login attempt? No — rejected users cannot log in. Instead, surface it in CEO tools; if your product shows it to the student, it must be communicated outside the API (e.g. a support channel), since the login response only returns the generic rejection message.
- After approval, the student can log in immediately — no re-registration required.
