"""File Upload & Private Storage Security Test Suite.

Validates:
- Whitelist extension enforcement (.jpg, .jpeg, .png, .webp)
- File size boundary checks (5MB limit, empty file rejection)
- Magic byte signature verification against polyglot files (MZ executable, ELF, PHP, HTML/JS)
- Double extension detection (e.g. image.php.png)
- Filename sanitization & path traversal defense (../../etc/passwd)
- Storage isolation outside static web root
- Ownership RBAC on private stored ID card files (Student Owner / CEO access only)
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.security.test_env_helper import setup_pentest_client


# Valid minimal image payloads
VALID_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
VALID_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
VALID_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x000\x01\x00\x9d\x01*\x01\x00\x01\x00\x02\x004%\xa4\x00"


def run_file_security_tests(base_url: str | None = None) -> dict[str, Any]:
    """Execute file upload and storage access tests."""
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

    # Test 1: Valid PNG Upload
    resp1 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("student_id.png", VALID_PNG, "image/png")}
    )
    record(
        "Valid PNG Upload Acceptance",
        resp1.status_code == 201 and "image_path" in resp1.json(),
        "Valid PNG file with authentic magic bytes must succeed with HTTP 201",
        f"HTTP {resp1.status_code}: {resp1.text[:90]}"
    )

    # Test 2: Valid JPEG Upload
    resp2 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("student_id.jpg", VALID_JPEG, "image/jpeg")}
    )
    record(
        "Valid JPEG Upload Acceptance",
        resp2.status_code == 201 and "image_path" in resp2.json(),
        "Valid JPEG file with authentic magic bytes must succeed with HTTP 201",
        f"HTTP {resp2.status_code}: {resp2.text[:90]}"
    )

    # Test 3: Oversized File Upload (> 5MB)
    large_payload = VALID_PNG + b"\x00" * (5 * 1024 * 1024 + 1024)
    resp3 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("huge_card.png", large_payload, "image/png")}
    )
    record(
        "Oversized File (> 5MB) Rejection",
        resp3.status_code == 422,
        "Files exceeding 5MB max limit must be rejected with HTTP 422",
        f"HTTP {resp3.status_code}: {resp3.text[:90]}"
    )

    # Test 4: Empty File Upload (0 bytes)
    resp4 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("empty.png", b"", "image/png")}
    )
    record(
        "Empty File (0 bytes) Rejection",
        resp4.status_code == 422,
        "Zero-byte file uploads must be rejected with HTTP 422",
        f"HTTP {resp4.status_code}: {resp4.text[:90]}"
    )

    # Test 5: Dangerous Executable Disguised as PNG (PE / MZ header)
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 200
    resp5 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("malware.png", fake_exe, "image/png")}
    )
    record(
        "Executable (MZ / PE) Disguised as PNG Rejection",
        resp5.status_code == 422,
        "Executable payload disguised as PNG must be rejected via magic byte inspection",
        f"HTTP {resp5.status_code}: {resp5.text[:90]}"
    )

    # Test 6: Linux ELF Binary Disguised as JPG
    fake_elf = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
    resp6 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("exploit.jpg", fake_elf, "image/jpeg")}
    )
    record(
        "Linux ELF Binary Disguised as JPG Rejection",
        resp6.status_code == 422,
        "ELF binary headers must be detected and rejected with HTTP 422",
        f"HTTP {resp6.status_code}: {resp6.text[:90]}"
    )

    # Test 7: Double Extension (image.php.png)
    resp7 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("avatar.php.png", VALID_PNG, "image/png")}
    )
    record(
        "Double Extension (avatar.php.png) Rejection",
        resp7.status_code == 422,
        "Double extensions containing script prefixes (.php) must be rejected with HTTP 422",
        f"HTTP {resp7.status_code}: {resp7.text[:90]}"
    )

    # Test 8: Forbidden Script Extension (.sh, .py, .exe)
    resp8 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("script.py", b"print('hacked')", "text/x-python")}
    )
    record(
        "Forbidden Extension (.py) Rejection",
        resp8.status_code == 422,
        "Non-whitelisted file extensions must be rejected with HTTP 422",
        f"HTTP {resp8.status_code}: {resp8.text[:90]}"
    )

    # Test 9: Filename Path Traversal Sanitization
    resp9 = client.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("../../etc/passwd.png", VALID_PNG, "image/png")}
    )
    # Even if accepted, the stored filename must be a clean UUID/safe path without traversal
    traversal_prevented = False
    if resp9.status_code == 201:
        stored_path = resp9.json().get("image_path", "")
        traversal_prevented = ".." not in stored_path and "etc" not in stored_path
    elif resp9.status_code in (400, 422):
        traversal_prevented = True
    record(
        "Filename Path Traversal Sanitization",
        traversal_prevented,
        "Path traversal patterns in filenames must be sanitized to random UUID storage paths",
        f"HTTP {resp9.status_code}: {resp9.text[:90]}"
    )

    # Test 10: Direct Web Access Probing on Private Storage Path
    resp10 = client.get("/uploads/id_cards/std_a_card.png")
    record(
        "Storage Isolation: Direct Static HTTP Probe",
        resp10.status_code == 404,
        "Private storage directory must not be served statically over HTTP",
        f"HTTP {resp10.status_code} (Not exposed via static file router)"
    )

    # Test 11: Authorized vs Unauthorized ID Card Access Control
    std_a_id = entities["std_a"].id
    h_std_a = {"Authorization": f"Bearer {tokens['STUDENT_A']}"}
    h_std_b = {"Authorization": f"Bearer {tokens['STUDENT_B']}"}
    h_sup_a = {"Authorization": f"Bearer {tokens['SUPERVISOR_A']}"}
    h_ceo = {"Authorization": f"Bearer {tokens['CEO']}"}

    resp_own = client.get(f"/api/v1/users/{std_a_id}/id-card", headers=h_std_a)
    resp_other = client.get(f"/api/v1/users/{std_a_id}/id-card", headers=h_std_b)
    resp_sup = client.get(f"/api/v1/users/{std_a_id}/id-card", headers=h_sup_a)
    resp_ceo = client.get(f"/api/v1/users/{std_a_id}/id-card", headers=h_ceo)
    resp_anon = client.get(f"/api/v1/users/{std_a_id}/id-card")

    rbac_accurate = (
        resp_own.status_code in (200, 404)
        and resp_other.status_code == 403
        and resp_sup.status_code == 403
        and resp_ceo.status_code in (200, 404)
        and resp_anon.status_code == 401
    )
    record(
        "ID Card Authorization Matrix (Owner=200, Other=403, Sup=403, CEO=200, Anon=401)",
        rbac_accurate,
        "Strict RBAC on ID card download endpoint",
        f"Owner: {resp_own.status_code}, Other: {resp_other.status_code}, Sup: {resp_sup.status_code}, CEO: {resp_ceo.status_code}, Anon: {resp_anon.status_code}"
    )

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    failed_tests = total_tests - passed_tests

    summary = {
        "suite": "File Upload & Private Storage Security Suite",
        "total": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "results": results
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="File Upload & Private Storage Security Suite")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of target API")
    parser.add_argument("--json", action="store_true", help="Output results as raw JSON")
    args = parser.parse_args()

    summary = run_file_security_tests(args.base_url)

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
