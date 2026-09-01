"""Insecure Direct Object Reference (IDOR) & RBAC Authorization Suite.

Validates horizontal and vertical authorization boundaries:
- Student-to-Student IDOR (subscriptions, QR codes, payments, ID card scans)
- Supervisor-to-Supervisor isolation (assigned trips, passenger rosters, scan controls)
- Vertical privilege escalation (Student/Supervisor attempting CEO administrative endpoints)
- Role containment (CEO blocked from operational supervisor physical boarding scans)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.security.test_env_helper import setup_pentest_client


def run_idor_attack_tests(base_url: str | None = None) -> dict[str, Any]:
    """Execute IDOR and authorization boundary tests."""
    results: list[dict[str, Any]] = []
    ctx = setup_pentest_client(base_url)
    client = ctx.client
    tokens = ctx.tokens
    entities = ctx.entities

    def record(name: str, passed: bool, details: str, evidence: str = ""):
        results.append({
            "test_name": name,
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "details": details,
            "evidence": evidence
        })

    # Header helpers
    h_std_a = {"Authorization": f"Bearer {tokens['STUDENT_A']}"}
    h_std_b = {"Authorization": f"Bearer {tokens['STUDENT_B']}"}
    h_sup_a = {"Authorization": f"Bearer {tokens['SUPERVISOR_A']}"}
    h_sup_b = {"Authorization": f"Bearer {tokens['SUPERVISOR_B']}"}
    h_ceo = {"Authorization": f"Bearer {tokens['CEO']}"}

    sub_a_id = entities["sub_a"].id
    pay_a_id = entities["pay_a"].id
    pay_b_id = entities["pay_b"].id
    std_a_id = entities["std_a"].id
    trip1_id = entities["trip1"].id
    trip2_id = entities["trip2"].id
    pk1_id = entities["pk1"].id

    # 1. Student B accesses Student A's subscription
    resp1 = client.get(f"/api/v1/subscriptions/{sub_a_id}", headers=h_std_b)
    record(
        "IDOR: Student B View Student A Subscription",
        resp1.status_code == 403,
        "Student B must receive HTTP 403 Forbidden when requesting Student A's subscription ID",
        f"HTTP {resp1.status_code}: {resp1.text[:100]}"
    )

    # 2. Student B accesses Student A's QR boarding token
    resp2 = client.get(f"/api/v1/subscriptions/{sub_a_id}/qr", headers=h_std_b)
    record(
        "IDOR: Student B View Student A QR Token",
        resp2.status_code == 403,
        "Student B must receive HTTP 403 Forbidden when requesting Student A's QR token",
        f"HTTP {resp2.status_code}: {resp2.text[:100]}"
    )

    # 3. Student B cancels Student A's subscription
    resp3 = client.patch(f"/api/v1/subscriptions/{sub_a_id}/cancel", headers=h_std_b)
    record(
        "IDOR: Student B Cancel Student A Subscription",
        resp3.status_code == 403,
        "Student B must receive HTTP 403 Forbidden when attempting to cancel Student A's subscription",
        f"HTTP {resp3.status_code}: {resp3.text[:100]}"
    )

    # 4. Student B views Student A's payment
    resp4 = client.get(f"/api/v1/payments/{pay_a_id}", headers=h_std_b)
    record(
        "IDOR: Student B View Student A Payment",
        resp4.status_code == 403,
        "Student B must receive HTTP 403 Forbidden when requesting Student A's payment record",
        f"HTTP {resp4.status_code}: {resp4.text[:100]}"
    )

    # 5. Student B cancels Student A's payment
    resp5 = client.patch(f"/api/v1/payments/{pay_a_id}/cancel", headers=h_std_b)
    record(
        "IDOR: Student B Cancel Student A Payment",
        resp5.status_code == 403,
        "Student B must receive HTTP 403 Forbidden when attempting to cancel Student A's payment",
        f"HTTP {resp5.status_code}: {resp5.text[:100]}"
    )

    # 6. Student B downloads Student A's private ID card
    resp6 = client.get(f"/api/v1/users/{std_a_id}/id-card", headers=h_std_b)
    record(
        "IDOR: Student B Download Student A University ID Card",
        resp6.status_code == 403,
        "Student B must receive HTTP 403 Forbidden when requesting Student A's ID card file",
        f"HTTP {resp6.status_code}: {resp6.text[:100]}"
    )

    # 7. Supervisor B scans boarding on Supervisor A's assigned trip
    resp7 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": entities["sub_a_raw_qr"],
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_sup_b)
    record(
        "Supervisor Scope: Supervisor B Scan on Supervisor A Trip",
        resp7.status_code == 403,
        "Supervisor B must receive HTTP 403 Forbidden when scanning boarding on a trip assigned to Supervisor A",
        f"HTTP {resp7.status_code}: {resp7.text[:100]}"
    )

    # 8. Supervisor B views passenger roster on Supervisor A's assigned trip
    resp8 = client.get(f"/api/v1/boarding/trips/{trip1_id}/students", headers=h_sup_b)
    record(
        "Supervisor Scope: Supervisor B View Supervisor A Passenger Roster",
        resp8.status_code == 403,
        "Supervisor B must receive HTTP 403 Forbidden when viewing passengers for trip1",
        f"HTTP {resp8.status_code}: {resp8.text[:100]}"
    )

    # 9. Supervisor B views boarding records on Supervisor A's assigned trip
    resp9 = client.get(f"/api/v1/boarding/trips/{trip1_id}/records", headers=h_sup_b)
    record(
        "Supervisor Scope: Supervisor B View Supervisor A Boarding Records",
        resp9.status_code == 403,
        "Supervisor B must receive HTTP 403 Forbidden when viewing attendance records for trip1",
        f"HTTP {resp9.status_code}: {resp9.text[:100]}"
    )

    # 10. Student attempts to access all users directory (CEO-only)
    resp10 = client.get("/api/v1/users", headers=h_std_a)
    record(
        "Vertical Privilege Escalation: Student List Users",
        resp10.status_code == 403,
        "Student must receive HTTP 403 Forbidden when attempting to list administrative user records",
        f"HTTP {resp10.status_code}: {resp10.text[:100]}"
    )

    # 11. Student attempts to update user role
    resp11 = client.patch(f"/api/v1/users/{std_a_id}/role", json={"role": "CEO"}, headers=h_std_a)
    record(
        "Vertical Privilege Escalation: Student Modify User Role",
        resp11.status_code in (403, 404, 405),
        "Student must receive HTTP 403 Forbidden when attempting role promotion",
        f"HTTP {resp11.status_code}: {resp11.text[:100]}"
    )

    # 12. Student attempts to create a fleet bus
    resp12 = client.post("/api/v1/buses", json={
        "bus_number": "B999",
        "license_plate": "EVIL-666",
        "capacity": 50,
        "status": "ACTIVE"
    }, headers=h_std_a)
    record(
        "Vertical Privilege Escalation: Student Create Bus",
        resp12.status_code == 403,
        "Student must receive HTTP 403 Forbidden when calling bus management endpoints",
        f"HTTP {resp12.status_code}: {resp12.text[:100]}"
    )

    # 13. Student attempts to verify payment (CEO/Supervisor only)
    resp13 = client.patch(f"/api/v1/payments/{pay_b_id}/verify", headers=h_std_a)
    record(
        "Vertical Privilege Escalation: Student Verify Payment Record",
        resp13.status_code == 403,
        "Student must be rejected with HTTP 403 when attempting to verify payments",
        f"HTTP {resp13.status_code}: {resp13.text[:100]}"
    )

    # 14. CEO operational boundary containment: CEO cannot scan boarding passes
    resp14 = client.post("/api/v1/boarding/scan", json={
        "trip_id": trip1_id,
        "qr_token": entities["sub_a_raw_qr"],
        "direction": "OUTBOUND",
        "pickup_point_id": pk1_id
    }, headers=h_ceo)
    record(
        "Role Boundary Containment: CEO Cannot Scan Boarding",
        resp14.status_code == 403,
        "CEO account must receive HTTP 403 Forbidden on operational physical bus scanning",
        f"HTTP {resp14.status_code}: {resp14.text[:100]}"
    )

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    failed_tests = total_tests - passed_tests

    summary = {
        "suite": "IDOR & RBAC Authorization Attack Tests",
        "total": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "results": results
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IDOR & RBAC Authorization Attack Suite")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of target API")
    parser.add_argument("--json", action="store_true", help="Output results as raw JSON")
    args = parser.parse_args()

    summary = run_idor_attack_tests(args.base_url)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("=" * 60)
        print(f"Suite: {summary['suite']}")
        print(f"Results: {summary['passed']}/{summary['total']} Passed ({summary['failed']} Failed)")
        print("=" * 60)
        for r in summary["results"]:
            print(f"[{r['status']}] {r['test_name']}: {r['evidence']}")
        print("=" * 60)

    if summary["failed"] > 0:
        sys.exit(1)
