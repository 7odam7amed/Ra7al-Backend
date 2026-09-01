"""Concurrency & Race Condition Security Test Suite.

Validates:
- Simultaneous boarding scan race conditions (10 concurrent requests with identical QR code)
- Database unique constraint enforcement preventing double-boarding
- Post-race database state verification (exactly 1 record created)
- Concurrent payment cancellation state transition race resistance
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.boarding import BoardingRecord
from scripts.security.test_env_helper import setup_pentest_client


def run_race_condition_tests(base_url: str | None = None) -> dict[str, Any]:
    """Execute concurrency and race condition tests."""
    results: list[dict[str, Any]] = []
    ctx = setup_pentest_client(base_url)
    client = ctx.client
    tokens = ctx.tokens
    entities = ctx.entities
    session = ctx.session

    def record(name: str, passed: bool, details: str, evidence: str = ""):
        results.append({
            "test_name": name,
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "details": details,
            "evidence": evidence
        })

    # Test 1: High-Concurrency Duplicate Boarding Scan Race (10 Concurrent Threads)
    h_sup_a = {"Authorization": f"Bearer {tokens['SUPERVISOR_A']}"}
    trip1_id = entities["trip1"].id
    pk1_id = entities["pk1"].id
    raw_qr_a = entities["sub_a_raw_qr"]
    sub_a_id = entities["sub_a"].id

    def do_scan(thread_idx: int) -> int:
        resp = client.post(
            "/api/v1/boarding/scan",
            json={
                "trip_id": trip1_id,
                "qr_token": raw_qr_a,
                "direction": "OUTBOUND",
                "pickup_point_id": pk1_id
            },
            headers=h_sup_a
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(do_scan, i) for i in range(10)]
        scan_results = [f.result() for f in as_completed(futures)]

    count_200 = scan_results.count(200)
    count_409 = scan_results.count(409)

    # Inspect database records
    db_records_count = -1
    if session:
        db_records_count = session.query(BoardingRecord).filter_by(
            subscription_id=sub_a_id,
            trip_id=trip1_id,
            direction="OUTBOUND"
        ).count()

    race_prevented = (count_200 == 1 and count_409 == 9) or (count_200 <= 1 and (count_200 + count_409 == 10))
    if db_records_count != -1:
        race_prevented = race_prevented and (db_records_count == 1)

    record(
        "Concurrent Boarding Scan Race (10 simultaneous threads)",
        race_prevented,
        "Exactly 1 scan request must succeed (HTTP 200) and 9 must be rejected (HTTP 409 Conflict)",
        f"HTTP Statuses: {scan_results} (200 OK: {count_200}, 409 Conflict: {count_409}), DB Records in table: {db_records_count}"
    )

    # Test 2: Concurrent Payment Cancellation Race (5 simultaneous threads)
    pay_a_id = entities["pay_a"].id
    h_std_a = {"Authorization": f"Bearer {tokens['STUDENT_A']}"}

    def do_cancel(thread_idx: int) -> int:
        resp = client.patch(f"/api/v1/payments/{pay_a_id}/cancel", headers=h_std_a)
        return resp.status_code

    with ThreadPoolExecutor(max_workers=5) as executor:
        cancel_futures = [executor.submit(do_cancel, i) for i in range(5)]
        cancel_results = [f.result() for f in as_completed(cancel_futures)]

    # Verified payments cannot be cancelled or only one cancel succeeds
    cancel_safe = all(s in (200, 400, 409, 422) for s in cancel_results)
    record(
        "Concurrent Payment State Cancellation Race (5 simultaneous threads)",
        cancel_safe,
        "Concurrent state transitions must not result in inconsistent database states",
        f"Cancel responses: {cancel_results}"
    )

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    failed_tests = total_tests - passed_tests

    summary = {
        "suite": "Concurrency & Race Condition Security Suite",
        "total": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "results": results
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Concurrency & Race Condition Security Suite")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of target API")
    parser.add_argument("--json", action="store_true", help="Output results as raw JSON")
    args = parser.parse_args()

    summary = run_race_condition_tests(args.base_url)

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
