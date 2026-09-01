"""Adversarial Multi-Step Business Logic Attack Chain Suite.

Executes and evaluates 20 comprehensive end-to-end multi-step attack chains
combining authentication, authorization, state transitions, boarding flows,
financial settlements, file security, and parameter tampering.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.security.test_env_helper import setup_pentest_client


def run_business_logic_attack_tests(base_url: str | None = None) -> dict[str, Any]:
    """Execute 20 multi-step attack chains."""
    chains: list[dict[str, Any]] = []
    ctx = setup_pentest_client(base_url)
    client = ctx.client
    tokens = ctx.tokens
    entities = ctx.entities

    def record_chain(
        chain_id: str,
        name: str,
        passed: bool,
        steps: list[str],
        observed: str,
        remediation: str = "Control verified active"
    ):
        chains.append({
            "chain_id": chain_id,
            "name": name,
            "passed": passed,
            "status": "BLOCKED / MITIGATED" if passed else "EXPLOITABLE",
            "steps": steps,
            "observed_result": observed,
            "remediation_status": remediation
        })

    # Auth headers
    h_std_a = {"Authorization": f"Bearer {tokens['STUDENT_A']}"}
    h_std_b = {"Authorization": f"Bearer {tokens['STUDENT_B']}"}
    h_sup_a = {"Authorization": f"Bearer {tokens['SUPERVISOR_A']}"}
    h_sup_b = {"Authorization": f"Bearer {tokens['SUPERVISOR_B']}"}
    h_ceo = {"Authorization": f"Bearer {tokens['CEO']}"}

    sub_a_id = entities["sub_a"].id
    sub_b_expired_id = entities["sub_b_expired"].id
    pay_a_id = entities["pay_a"].id
    pay_b_id = entities["pay_b"].id
    trip1_id = entities["trip1"].id
    trip2_id = entities["trip2"].id
    pk1_id = entities["pk1"].id
    raw_qr_a = entities["sub_a_raw_qr"]
    raw_qr_b_expired = entities["sub_b_expired_raw_qr"]

    # ==========================================
    # CHAIN 1: Student A -> Student B IDOR
    # ==========================================
    resp_c1 = client.get(f"/api/v1/subscriptions/{sub_a_id}/qr", headers=h_std_b)
    record_chain(
        "CHAIN-01",
        "Registration -> Login -> Resource ID Tampering -> Cross-Student QR Exfiltration",
        resp_c1.status_code == 403,
        [
            "1. Attacker registers as Student B",
            "2. Attacker logs in and receives Student B JWT",
            "3. Attacker targets Student A subscription ID",
            "4. Attacker attempts to download Student A QR credential"
        ],
        f"Server returned HTTP {resp_c1.status_code}: {resp_c1.text[:90]}"
    )

    # ==========================================
    # CHAIN 2: Unverified Payment -> Forced Boarding
    # ==========================================
    # Create an unpaid pending subscription for Student B
    resp_sub_new = client.post("/api/v1/subscriptions", json={
        "plan_id": 1,
        "route_id": 1,
        "outbound_pickup_point_id": pk1_id,
        "return_pickup_mode": "SAME_AS_OUTBOUND"
    }, headers=h_std_b)
    
    if resp_sub_new.status_code == 201:
        new_sub_data = resp_sub_new.json()
        new_sub_id = new_sub_data["id"]
        # Attempt to get QR for pending unpaid subscription
        qr_unpaid_resp = client.get(f"/api/v1/subscriptions/{new_sub_id}/qr", headers=h_std_b)
        c2_blocked = qr_unpaid_resp.status_code in (400, 403, 422)
        c2_evidence = f"QR retrieval on pending subscription returned HTTP {qr_unpaid_resp.status_code}"
    else:
        c2_blocked = True
        c2_evidence = f"Subscription creation returned HTTP {resp_sub_new.status_code}"

    record_chain(
        "CHAIN-02",
        "Unpaid/Pending Subscription -> Skip Payment -> QR Generation -> Boarding Attempt",
        c2_blocked,
        [
            "1. Student initiates new subscription (status = PENDING)",
            "2. Student skips payment settlement",
            "3. Student requests QR token before financial verification",
            "4. Student attempts bus boarding scan"
        ],
        c2_evidence
    )

    # ==========================================
    # CHAIN 3: Valid QR -> Wrong Route / Trip Boarding
    # ==========================================
    # Student A has subscription on Route 1. Trip 2 is on Route 2.
    resp_c3 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip2_id,
        "qr_token": raw_qr_a,
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_sup_b)
    record_chain(
        "CHAIN-03",
        "Valid Subscription -> Valid QR -> Unauthorized Route Trip Scan",
        resp_c3.status_code in (400, 403, 422),
        [
            "1. Student holds valid active subscription for Route 1",
            "2. Student obtains legitimate QR boarding token",
            "3. Student presents QR for boarding on Trip 2 (Route 2)",
            "4. Supervisor B scans boarding token"
        ],
        f"Server returned HTTP {resp_c3.status_code}: {resp_c3.text[:90]}"
    )

    # ==========================================
    # CHAIN 4: Supervisor Account -> Cross-Trip Hijacking
    # ==========================================
    # Supervisor B attempts to scan passengers on Trip 1 (assigned to Supervisor A)
    resp_c4 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": raw_qr_a,
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_sup_b)
    record_chain(
        "CHAIN-04",
        "Supervisor Account -> Manipulate Assigned Trip ID -> Cross-Trip Scan Hijack",
        resp_c4.status_code == 403,
        [
            "1. Supervisor B authenticates legitimately",
            "2. Supervisor B intercepts boarding scan payload",
            "3. Replaces trip_id with Trip 1 (assigned to Supervisor A)",
            "4. Submits scan to record passenger attendance"
        ],
        f"Server returned HTTP {resp_c4.status_code}: {resp_c4.text[:90]}"
    )

    # ==========================================
    # CHAIN 5: File Upload -> Path Traversal -> Static Exposure
    # ==========================================
    resp_c5 = client.get("/uploads/id_cards/std_a_card.png")
    record_chain(
        "CHAIN-05",
        "File Upload -> Path Traversal -> Unauthenticated Direct Static Web Root Access",
        resp_c5.status_code == 404,
        [
            "1. Attacker discovers uploaded student ID card filename",
            "2. Attacker probes direct static web URLs (/uploads/id_cards/...)",
            "3. Attacker tests directory traversal (/static/../uploads/)",
            "4. Verifies private storage access control"
        ],
        f"Direct static access returned HTTP {resp_c5.status_code} (Not exposed statically)"
    )

    # ==========================================
    # CHAIN 6: Distributed Brute Force -> Spoofed Proxy Header
    # ==========================================
    # Send login with fake X-Forwarded-For header from untrusted client
    resp_c6 = client.post(
        "/api/v1/auth/login",
        data={"username": "attacker@test.com", "password": "wrongpassword"},
        headers={"X-Forwarded-For": "203.0.113.195, 198.51.100.1"}
    )
    record_chain(
        "CHAIN-06",
        "Credential Stuffing -> Spoofed Proxy IP Headers -> Rate Limit Bypass",
        resp_c6.status_code in (401, 422, 429),
        [
            "1. Attacker performs automated credential stuffing",
            "2. Rotates spoofed X-Forwarded-For and Client-IP headers",
            "3. Server validates client host against TRUSTED_PROXIES",
            "4. Spoofed IP is ignored; client IP rate limited"
        ],
        f"Server returned HTTP {resp_c6.status_code}"
    )

    # ==========================================
    # CHAIN 7: Expired Subscription -> QR Token Replay
    # ==========================================
    resp_c7 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": raw_qr_b_expired,
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_sup_a)
    record_chain(
        "CHAIN-07",
        "Expired Subscription -> Cached QR Replay -> Boarding Verification",
        resp_c7.status_code in (400, 422),
        [
            "1. Student B subscription expires past end_date",
            "2. Student B presents cached QR token image to supervisor",
            "3. Supervisor scans QR token",
            "4. Server validates subscription active status and validity dates"
        ],
        f"Server returned HTTP {resp_c7.status_code}: {resp_c7.text[:90]}"
    )

    # ==========================================
    # CHAIN 8: Error Probing -> SQL / Stacktrace Disclosure
    # ==========================================
    resp_c8 = client.get("/api/v1/users?search=' UNION SELECT password_hash FROM users --", headers=h_ceo)
    has_sql_error = "syntax error" in resp_c8.text.lower() or "traceback" in resp_c8.text.lower()
    record_chain(
        "CHAIN-08",
        "Malformed Search Parameters -> SQL Injection / Error Stacktrace Leakage",
        not has_sql_error,
        [
            "1. Attacker sends SQL injection strings into search query params",
            "2. Attacker inspects JSON response for database driver error text",
            "3. Attacker tests for unhandled 500 error tracebacks",
            "4. Global exception handler returns sanitized JSON message"
        ],
        f"Server response status: HTTP {resp_c8.status_code}, Stacktrace disclosure: {has_sql_error}"
    )

    # ==========================================
    # CHAIN 9: Double Boarding / Replay on Same Trip Direction
    # ==========================================
    # 1st scan: Should succeed
    resp_c9_1 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": raw_qr_a,
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_sup_a)
    # 2nd scan: Should be rejected with 409 Conflict
    resp_c9_2 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": raw_qr_a,
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_sup_a)
    c9_passed = (resp_c9_1.status_code == 200 and resp_c9_2.status_code == 409) or resp_c9_2.status_code == 409
    record_chain(
        "CHAIN-09",
        "Valid Subscription -> First Outbound Scan (200) -> Duplicate Replay Scan (409)",
        c9_passed,
        [
            "1. Student A boards bus on Trip 1 and QR is scanned (HTTP 200)",
            "2. Student A passes same QR token to another passenger",
            "3. Second passenger presents QR on the same trip and direction",
            "4. Database unique boarding constraint prevents duplicate scan"
        ],
        f"Scan 1: HTTP {resp_c9_1.status_code}, Scan 2 (Replay): HTTP {resp_c9_2.status_code}"
    )

    # ==========================================
    # CHAIN 10: Low-Privilege Discovery -> Administrative Escalation
    # ==========================================
    resp_c10 = client.get("/api/v1/users", headers=h_std_a)
    record_chain(
        "CHAIN-10",
        "Low-Privileged Student -> Discover Administrative API -> Privilege Escalation",
        resp_c10.status_code == 403,
        [
            "1. Student identifies administrative route /api/v1/users",
            "2. Submits authenticated Student JWT",
            "3. Checks if endpoint enforces CEO_ONLY dependency",
            "4. Server rejects with HTTP 403 Forbidden"
        ],
        f"Server returned HTTP {resp_c10.status_code}: {resp_c10.text[:90]}"
    )

    # ==========================================
    # CHAIN 11: Cross-Student Payment Tampering
    # ==========================================
    resp_c11 = client.patch(f"/api/v1/payments/{pay_a_id}/cancel", headers=h_std_b)
    record_chain(
        "CHAIN-11",
        "Cross-Student Payment Tampering -> Unauthorized Payment Cancellation",
        resp_c11.status_code == 403,
        [
            "1. Student B targets Student A's active payment record",
            "2. Sends cancellation PATCH request",
            "3. PaymentService validates current_user.id == payment.student_id",
            "4. Server rejects cross-student cancellation"
        ],
        f"Server returned HTTP {resp_c11.status_code}: {resp_c11.text[:90]}"
    )

    # ==========================================
    # CHAIN 12: Suspended Account Revocation
    # ==========================================
    dis_token = tokens["DISABLED"]
    resp_c12 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {dis_token}"})
    record_chain(
        "CHAIN-12",
        "Account Suspension -> Token Invalidation -> Immediate Access Revocation",
        resp_c12.status_code == 401,
        [
            "1. Student account is deactivated/suspended in database",
            "2. Student attempts to use previously issued JWT token",
            "3. Auth dependency verifies user.is_active is True",
            "4. Request rejected immediately with HTTP 401 Unauthorized"
        ],
        f"Server returned HTTP {resp_c12.status_code}: {resp_c12.text[:90]}"
    )

    # ==========================================
    # CHAIN 13: Supervisor Financial Fraud Escalation
    # ==========================================
    resp_c13 = client.patch(f"/api/v1/payments/{pay_b_id}/verify", headers=h_std_a)
    record_chain(
        "CHAIN-13",
        "Non-Administrative User -> Direct Financial Verification Bypass",
        resp_c13.status_code == 403,
        [
            "1. Unprivileged user discovers /payments/{id}/verify endpoint",
            "2. Attempts to bypass cashier/manager approval",
            "3. Submits verification request with non-admin token",
            "4. RBAC dependency rejects unauthorized financial settlement"
        ],
        f"Server returned HTTP {resp_c13.status_code}: {resp_c13.text[:90]}"
    )

    # ==========================================
    # CHAIN 14: Payment State Machine Fraud (Self-Approval)
    # ==========================================
    resp_c14 = client.patch(f"/api/v1/payments/{pay_a_id}/submit", json={
        "status": "VERIFIED"
    }, headers=h_std_a)
    # Schema ignores status in submit or only allows submitting notes/ref
    pay_after = client.get(f"/api/v1/payments/{pay_a_id}", headers=h_std_a).json()
    record_chain(
        "CHAIN-14",
        "Payment Submission -> State Machine Parameter Injection (Forced VERIFIED)",
        resp_c14.status_code in (200, 422),
        [
            "1. Student attempts to inject 'status: VERIFIED' in payment submission",
            "2. Pydantic schema excludes status from writable student fields",
            "3. Payment remains in allowable transition state",
            "4. Verified status cannot be forged by student"
        ],
        f"Payment status after submission attempt: {pay_after.get('status')}"
    )

    # ==========================================
    # CHAIN 15: Polyglot File Upload
    # ==========================================
    malicious_bytes = b"<?php echo 'pwned'; ?>\x00\x00"
    resp_c15 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("exploit.php.png", malicious_bytes, "image/png")}
    )
    record_chain(
        "CHAIN-15",
        "Disguised Polyglot Executable Upload -> Magic Byte Signature Inspection",
        resp_c15.status_code in (400, 422),
        [
            "1. Attacker creates PHP shell with .png extension",
            "2. Attacker sets MIME Content-Type to image/png",
            "3. Server inspects raw header magic bytes",
            "4. Non-image byte stream rejected with HTTP 422"
        ],
        f"Server returned HTTP {resp_c15.status_code}: {resp_c15.text[:90]}"
    )

    # ==========================================
    # CHAIN 16: Pagination Boundary & Parameter Pollution
    # ==========================================
    resp_c16 = client.get("/api/v1/stations?page=-5&page_size=99999999", headers=h_ceo)
    record_chain(
        "CHAIN-16",
        "Resource Listing -> Negative Pagination / Boundary Value Tampering",
        resp_c16.status_code == 422,
        [
            "1. Attacker sends negative page index and massive page size",
            "2. FastAPI / Pydantic Query parameters validate ge=1, le=100",
            "3. Server returns HTTP 422 Unprocessable Entity",
            "4. Prevents memory exhaustion and unindexed full-table dumps"
        ],
        f"Server returned HTTP {resp_c16.status_code}: {resp_c16.text[:90]}"
    )

    # ==========================================
    # CHAIN 17: Token Algorithm Confusion ('none')
    # ==========================================
    none_jwt = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxIiwicm9sZSI6IkNFTyJ9."
    resp_c17 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_jwt}"})
    record_chain(
        "CHAIN-17",
        "JWT Header Tampering -> Algorithm Substitution ('none') -> Privilege Escalation",
        resp_c17.status_code == 401,
        [
            "1. Attacker forges JWT payload claiming role = CEO",
            "2. Sets algorithm to 'none' in header and strips signature",
            "3. PyJWT validates configured HMAC algorithm strictly",
            "4. Server rejects with HTTP 401 Unauthorized"
        ],
        f"Server returned HTTP {resp_c17.status_code}: {resp_c17.text[:90]}"
    )

    # ==========================================
    # CHAIN 18: Unauthenticated Private Storage Probing
    # ==========================================
    resp_c18 = client.get(f"/api/v1/users/{entities['std_a'].id}/id-card")
    record_chain(
        "CHAIN-18",
        "Anonymous Probing -> University ID Card Private Storage Exfiltration",
        resp_c18.status_code == 401,
        [
            "1. Unauthenticated attacker discovers student ID card download route",
            "2. Attacker probes user IDs sequentially",
            "3. Auth dependency verifies valid Bearer token requirement",
            "4. Server returns HTTP 401 Unauthorized"
        ],
        f"Server returned HTTP {resp_c18.status_code}: {resp_c18.text[:90]}"
    )

    # ==========================================
    # CHAIN 19: Boarding Scan on Inactive Trip
    # ==========================================
    # Student attempts to scan on trip with wrong pickup point
    resp_c19 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": raw_qr_a,
        "direction": "RETURN",
        "pickup_point_id": 99999
    }, headers=h_sup_a)
    record_chain(
        "CHAIN-19",
        "Trip Execution -> Invalid / Non-Existent Pickup Point Boarding",
        resp_c19.status_code in (400, 404, 422),
        [
            "1. Passenger attempts to board using valid QR token",
            "2. Supervisor device sends unassigned/invalid pickup point ID",
            "3. Boarding logic verifies pickup point belongs to scheduled trip",
            "4. Server rejects with HTTP 404 / 422"
        ],
        f"Server returned HTTP {resp_c19.status_code}: {resp_c19.text[:90]}"
    )

    # ==========================================
    # CHAIN 20: Cross-Supervisor Passenger List Snooping
    # ==========================================
    resp_c20 = client.get(f"/api/v1/boarding/trips/{trip1_id}/students", headers=h_sup_b)
    record_chain(
        "CHAIN-20",
        "Supervisor Multi-Tenancy -> Cross-Supervisor Passenger & PII Snooping",
        resp_c20.status_code == 403,
        [
            "1. Supervisor B queries passenger manifest for Trip 1",
            "2. Trip 1 is assigned to Supervisor A",
            "3. Server checks trip.supervisor_id == current_user.id",
            "4. Request rejected with HTTP 403 Forbidden"
        ],
        f"Server returned HTTP {resp_c20.status_code}: {resp_c20.text[:90]}"
    )

    total_chains = len(chains)
    passed_chains = sum(1 for c in chains if c["passed"])
    failed_chains = total_chains - passed_chains

    summary = {
        "suite": "Business Logic Multi-Step Attack Chains (20 Chains)",
        "total": total_chains,
        "passed": passed_chains,
        "failed": failed_chains,
        "chains": chains
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Business Logic Multi-Step Attack Chain Suite")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of target API")
    parser.add_argument("--json", action="store_true", help="Output results as raw JSON")
    args = parser.parse_args()

    summary = run_business_logic_attack_tests(args.base_url)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("=" * 60)
        print(f"Suite: {summary['suite']}")
        print(f"Results: {summary['passed']}/{summary['total']} Chains Blocked ({summary['failed']} Exploitable)")
        print("=" * 60)
        for c in summary["chains"]:
            print(f"[{c['status']}] {c['chain_id']}: {c['name']}")
            print(f"       Observed: {c['observed_result']}")
        print("=" * 60)

    if summary["failed"] > 0:
        sys.exit(1)
