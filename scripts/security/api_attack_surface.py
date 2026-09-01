"""API Attack Surface Enumeration & Inventory Tool.

Discovers and catalogs all routes, methods, path parameters, query parameters,
role requirements, and legacy field checks against the FastAPI OpenAPI schema.
Supports both live staging endpoint inspection and in-process FastAPI TestClient execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def discover_attack_surface(base_url: str | None = None) -> dict[str, Any]:
    """Fetch OpenAPI specification from target or in-process app and generate inventory."""
    schema: dict[str, Any] = {}
    target_info = ""
    client = None

    if base_url:
        import httpx
        try:
            client = httpx.Client(base_url=base_url, timeout=10.0)
            resp = client.get("/openapi.json")
            if resp.status_code == 200:
                schema = resp.json()
                target_info = f"Live HTTP target ({base_url})"
            else:
                client = None
        except Exception as e:
            print(f"Warning: Could not connect to live target {base_url} ({e}). Falling back to in-process app.", file=sys.stderr)
            client = None

    if not schema or client is None:
        from fastapi.testclient import TestClient
        from app.main import create_app
        app = create_app()
        client = TestClient(app)
        resp = client.get("/openapi.json")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch openapi.json from in-process app: HTTP {resp.status_code}")
        schema = resp.json()
        target_info = "In-Process FastAPI Application (TestClient)"

    paths = schema.get("paths", {})

    inventory: dict[str, Any] = {
        "target_mode": target_info,
        "base_url": base_url or "http://testserver",
        "openapi_version": schema.get("openapi", "3.1.0"),
        "total_paths": len(paths),
        "total_endpoints": 0,
        "by_category": {},
        "by_method": {"GET": 0, "POST": 0, "PUT": 0, "PATCH": 0, "DELETE": 0, "OPTIONS": 0, "HEAD": 0},
        "role_mapped_endpoints": {
            "PUBLIC": [],
            "AUTHENTICATED": [],
            "STUDENT": [],
            "SUPERVISOR": [],
            "CEO": [],
        },
        "undocumented_routes_tested": [],
        "legacy_fields_present": {
            "DRIVER_enum": "DRIVER" in str(schema),
            "driver_id": "driver_id" in str(schema),
        },
        "endpoints": []
    }

    for path, path_item in sorted(paths.items()):
        for method, op in path_item.items():
            if method.upper() in inventory["by_method"]:
                inventory["by_method"][method.upper()] += 1
            inventory["total_endpoints"] += 1

            tags = op.get("tags", ["General"])
            tag = tags[0] if tags else "General"
            inventory["by_category"].setdefault(tag, 0)
            inventory["by_category"][tag] += 1

            summary = op.get("summary", "")
            security = op.get("security", [])

            # Classify role requirements based on summary/tags/security
            summary_lower = summary.lower()
            if "ceo only" in summary_lower:
                role = "CEO"
            elif "supervisor only" in summary_lower:
                role = "SUPERVISOR"
            elif "public" in summary_lower or not security:
                role = "PUBLIC"
            else:
                role = "AUTHENTICATED"

            inventory["role_mapped_endpoints"][role].append(f"{method.upper()} {path}")

            inventory["endpoints"].append({
                "path": path,
                "method": method.upper(),
                "summary": summary,
                "tags": tags,
                "parameters": [p.get("name") for p in op.get("parameters", [])],
                "has_request_body": "requestBody" in op,
                "role_inferred": role
            })

    # Check for hidden or undocumented route probes
    probe_routes = [
        "/admin",
        "/admin/login",
        "/metrics",
        "/debug",
        "/env",
        "/actuator",
        "/api/v1/drivers",
        "/api/v1/admin",
        "/uploads",
        "/static",
        "/docs",
        "/redoc",
        "/health",
        "/backup",
        "/db",
        "/config",
    ]

    for probe in probe_routes:
        probe_resp = client.get(probe)
        inventory["undocumented_routes_tested"].append({
            "path": probe,
            "status_code": probe_resp.status_code,
            "accessible": probe_resp.status_code not in (404, 405)
        })

    return inventory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="API Attack Surface Discovery Tool")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of target API")
    parser.add_argument("--json", action="store_true", help="Output results as raw JSON")
    args = parser.parse_args()

    inv = discover_attack_surface(args.base_url)

    if args.json:
        print(json.dumps(inv, indent=2))
    else:
        print("=" * 60)
        print(f"API Attack Surface Discovery: {inv['target_mode']}")
        print("=" * 60)
        print(f"Total Paths: {inv['total_paths']}")
        print(f"Total Endpoint Operations: {inv['total_endpoints']}")
        print("\nBreakdown by HTTP Method:")
        for m, count in inv["by_method"].items():
            if count > 0:
                print(f"  - {m}: {count}")
        print("\nBreakdown by Category / Tag:")
        for cat, count in inv["by_category"].items():
            print(f"  - {cat}: {count}")
        print("\nRole Requirements Mapped:")
        for role, routes in inv["role_mapped_endpoints"].items():
            print(f"  - {role}: {len(routes)} endpoints")
        print(f"\nLegacy Schema Residuals:")
        print(f"  - DRIVER Enum Present: {inv['legacy_fields_present']['DRIVER_enum']}")
        print(f"  - driver_id Present: {inv['legacy_fields_present']['driver_id']}")
        print("\nUndocumented Route Probing:")
        for p in inv["undocumented_routes_tested"]:
            status_desc = "ACCESSIBLE" if p["accessible"] else "PROTECTED / NOT FOUND"
            print(f"  - {p['path']:20} -> HTTP {p['status_code']} ({status_desc})")
        print("=" * 60)
