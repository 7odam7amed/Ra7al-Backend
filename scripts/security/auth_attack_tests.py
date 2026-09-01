"""Authentication & Session Security Attack Suite.

Validates resistance against JWT tampering, algorithm confusion, credential stuffing,
password policy bypass, disabled account access, SQL injection in auth endpoints,
and role privilege escalation during registration.
Supports both live staging endpoint execution and in-process FastAPI TestClient.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any
import jwt

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from scripts.security.test_env_helper import setup_pentest_client


def run_auth_attack_tests(base_url: str | None = None) -> dict[str, Any]:
    """Execute adversarial authentication and token validation tests."""
    results: list[dict[str, Any]] = []
    settings = get_settings()
    ctx = setup_pentest_client(base_url)
    client = ctx.client

    def record(name: str, passed: bool, details: str, evidence: str = ""):
        results.append({
            "test_name": name,
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "details": details,
            "evidence": evidence
        })

    # Test 1: Weak password in registration (< 8 chars)
    weak_reg = client.post("/api/v1/auth/register", json={
        "full_name": "Weak Pass User",
        "phone_number": "01000000099",
        "password": "123",
        "gender": "MALE",
        "university_id": 1,
        "faculty": "Engineering",
        "academic_year": "3rd Year",
        "university_id_card_image": "uploads/id_cards/test.png",
    })
    record(
        "Weak Password Registration (< 8 chars)",
        weak_reg.status_code == 422,
        "Registration should reject passwords under 8 characters with HTTP 422",
        f"HTTP {weak_reg.status_code}: {weak_reg.text[:120]}"
    )

    # Test 2: Role privilege escalation in registration payload
    reg_with_role = client.post("/api/v1/auth/register", json={
        "full_name": "Escalation Candidate",
        "phone_number": "01011112233",
        "password": "StrongPassword123!",
        "gender": "FEMALE",
        "university_id": 1,
        "faculty": "Engineering",
        "academic_year": "3rd Year",
        "university_id_card_image": "uploads/id_cards/test.png",
        "role": "CEO"
    })
    if reg_with_role.status_code == 201:
        data = reg_with_role.json()
        escalation_prevented = data.get("role") == "STUDENT"
        record(
            "Registration Role Escalation Attempt",
            escalation_prevented,
            "Passed 'role: CEO' in registration body must be ignored or assigned 'STUDENT'",
            f"Assigned role in response: {data.get('role')}"
        )
    else:
        record(
            "Registration Role Escalation Attempt",
            reg_with_role.status_code in (422, 400),
            "Schema strictly rejects unrecognized fields or role override",
            f"HTTP {reg_with_role.status_code}: {reg_with_role.text[:120]}"
        )

    # Test 3: SQL Injection in login credentials
    sqli_login = client.post("/api/v1/auth/login", data={
        "username": "' OR '1'='1' --",
        "password": "' OR '1'='1' --"
    })
    sqli_safe = sqli_login.status_code in (401, 422) and "syntax error" not in sqli_login.text.lower()
    record(
        "SQL Injection Probe in Login",
        sqli_safe,
        "SQL injection in login payload must return 401/422 without syntax/database error disclosure",
        f"HTTP {sqli_login.status_code}: {sqli_login.text[:120]}"
    )

    # Test 4: Expired JWT Token
    expired_payload = {
        "sub": "1",
        "role": "STUDENT",
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=3)).timestamp())
    }
    expired_token = jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    expired_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    record(
        "Expired JWT Token Rejection",
        expired_resp.status_code == 401,
        "Expired JWT token must return HTTP 401 Unauthorized",
        f"HTTP {expired_resp.status_code}: {expired_resp.text[:120]}"
    )

    # Test 5: Tampered JWT Signature
    tampered_payload = {
        "sub": "1",
        "role": "CEO",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp()),
    }
    fake_token = jwt.encode(tampered_payload, "wrong-forged-secret-key-1234567890", algorithm="HS256")
    fake_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    record(
        "Tampered JWT Signature Rejection",
        fake_resp.status_code == 401,
        "JWT signed with untrusted key must be rejected with HTTP 401 Unauthorized",
        f"HTTP {fake_resp.status_code}: {fake_resp.text[:120]}"
    )

    # Test 6: Algorithm 'none' token confusion
    try:
        none_token = jwt.encode(tampered_payload, key="", algorithm="none")
    except Exception:
        none_token = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTYiLCJyb2xlIjoiQ0VPIn0."
    none_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_token}"})
    record(
        "Algorithm 'none' Confusion Rejection",
        none_resp.status_code == 401,
        "Token with alg=none must be rejected with HTTP 401 Unauthorized",
        f"HTTP {none_resp.status_code}: {none_resp.text[:120]}"
    )

    # Test 7: Missing and malformed Authorization header
    missing_resp = client.get("/api/v1/auth/me")
    malformed_resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-token-string"})
    no_bearer_resp = client.get("/api/v1/auth/me", headers={"Authorization": "Basic 12345"})
    all_rejected = missing_resp.status_code == 401 and malformed_resp.status_code == 401 and no_bearer_resp.status_code == 401
    record(
        "Missing / Malformed Authorization Headers",
        all_rejected,
        "Missing, malformed, or non-Bearer schemes must return HTTP 401",
        f"Missing: HTTP {missing_resp.status_code}, Malformed: HTTP {malformed_resp.status_code}, Basic: HTTP {no_bearer_resp.status_code}"
    )

    # Test 8: Password hash leakage verification in auth responses
    login_valid = client.post("/api/v1/auth/login", data={
        "username": "ceo@ra7al.edu.eg",
        "password": "Password123!"
    })
    hash_leaked = False
    if login_valid.status_code == 200:
        token = login_valid.json().get("access_token")
        me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        body_text = f"{login_valid.text} {me_resp.text}"
        hash_leaked = "password_hash" in body_text or "$argon2" in body_text
    record(
        "Password Hash / Argon2 Redaction in API Responses",
        not hash_leaked,
        "password_hash and cryptographic hashes must be absent from responses",
        f"Login Status: {login_valid.status_code}, Hash Leaked: {hash_leaked}"
    )

    # Test 9: Disabled account login and access attempt
    dis_login = client.post("/api/v1/auth/login", data={
        "username": "disabled_student@ra7al.edu.eg",
        "password": "Password123!"
    })
    dis_token = ctx.tokens.get("DISABLED", "")
    dis_access = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {dis_token}"})
    disabled_blocked = dis_login.status_code in (401, 403) and dis_access.status_code in (401, 403)
    record(
        "Suspended / Inactive User Login & Token Blocking",
        disabled_blocked,
        "Suspended user must be denied login and blocked from authenticated endpoints",
        f"Login: HTTP {dis_login.status_code}, Token Access: HTTP {dis_access.status_code}"
    )

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    failed_tests = total_tests - passed_tests

    summary = {
        "suite": "Authentication & Session Attack Tests",
        "total": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "results": results
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Authentication & Session Security Attack Suite")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of target API")
    parser.add_argument("--json", action="store_true", help="Output results as raw JSON")
    args = parser.parse_args()

    summary = run_auth_attack_tests(args.base_url)

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
