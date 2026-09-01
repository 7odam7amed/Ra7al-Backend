from pathlib import Path
import re
import pytest


def test_gitignore_protects_database_dumps_and_backups() -> None:
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists(), ".gitignore file must exist"

    content = gitignore_path.read_text(encoding="utf-8")
    required_patterns = ["*.sql", "*.dump", "*.backup", "*.bak", "backups/", "dumps/"]

    for pattern in required_patterns:
        assert pattern in content, f"Missing required sensitive pattern '{pattern}' in .gitignore"


def test_production_compose_does_not_expose_backup_mounts() -> None:
    compose_path = Path("docker-compose.prod.yml")
    assert compose_path.exists(), "docker-compose.prod.yml must exist"

    content = compose_path.read_text(encoding="utf-8")
    forbidden_terms = ["backups", "dumps", "*.sql", "*.dump", "5432:5432"]

    for term in forbidden_terms:
        assert term not in content, f"Forbidden term '{term}' detected in docker-compose.prod.yml"


def test_backup_script_contains_no_hardcoded_credentials() -> None:
    script_path = Path("scripts/backup_db.py")
    assert script_path.exists(), "scripts/backup_db.py must exist"

    content = script_path.read_text(encoding="utf-8")

    # Ensure no hardcoded secret assignments
    assert not re.search(r'password\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE)
    assert not re.search(r'postgresql://[a-zA-Z0-9]+:[a-zA-Z0-9]+@', content)
    assert "os.getenv(\"DATABASE_URL\")" in content or "os.environ" in content


def test_backup_and_dump_files_not_accessible_via_http() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    unauthorized_paths = [
        "/backups/ra7al_backup.dump",
        "/backups/backup.sql",
        "/dumps/db.dump",
        "/dumps/database.sql",
        "/app/backups/dump.sql",
        "/uploads/backups/dump.sql",
    ]

    for path in unauthorized_paths:
        res = client.get(path)
        assert res.status_code in (404, 405), f"Path '{path}' should not be accessible via HTTP"

