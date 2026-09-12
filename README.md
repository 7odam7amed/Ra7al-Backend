# University Bus Management System — Backend

Production-ready backend foundation for a University Bus Management System. This repository currently contains **Phase 0** infrastructure only — no business features or authentication yet.

## Project Overview

This API will power bus route management, trip scheduling, student bookings, and supervisor operations for a university transport system. Phase 0 establishes the core architecture, database connectivity, Docker environment, migrations, logging, testing, and health checks that future sprints will build upon.

## Technology Stack

- **Python 3.12+**
- **FastAPI** — web framework
- **PostgreSQL 16** — relational database
- **SQLAlchemy 2.0** — ORM
- **Alembic** — database migrations
- **Pydantic v2** — data validation
- **pydantic-settings** — configuration management
- **psycopg2-binary** — PostgreSQL driver
- **Uvicorn** — ASGI server
- **Docker & Docker Compose** — containerization
- **Pytest** — testing

## Requirements

- Python 3.12 or newer
- Docker
- Docker Compose

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd backend
```

### 2. Create environment file

```bash
cp .env.example .env
```

Edit `.env` if needed. For local development without Docker, set:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/bus_system
```

### 3. Start PostgreSQL (Docker)

```bash
docker compose up db -d
```

### 4. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Start the API

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Docker

Run the full stack (API + PostgreSQL):

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432` (development only)

The API service waits for PostgreSQL to become healthy before starting.

## Migrations

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
```

Apply migrations:

```bash
alembic upgrade head
```

## Testing

Start PostgreSQL first (integration tests require a live database):

```bash
docker compose up db -d
```

Run all tests:

```bash
pytest
```

Run with verbose output:

```bash
pytest -v
```

Integration tests are skipped automatically when PostgreSQL is unavailable.

> **Git Bash / MSYS2 note (Windows):** MSYS2 path conversion can rewrite values of
> environment variables that look like Unix paths before native processes receive them
> (e.g. `API_V1_PREFIX=/api/v1` may reach Python as `C:/Program Files/Git/api/v1`).
> If pytest fails at collection with `AssertionError: A path prefix must start with '/'`,
> run the suite with path conversion disabled — the `.env` file itself needs no change:
>
> ```bash
> MSYS_NO_PATHCONV=1 pytest -q
> ```

## API Documentation

When the application is running:

| Documentation | URL |
|---------------|-----|
| Swagger UI    | http://localhost:8000/docs |
| ReDoc         | http://localhost:8000/redoc |
| OpenAPI JSON  | http://localhost:8000/openapi.json |

## Available Endpoints (Phase 0)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/health`    | API health check         |
| GET    | `/health/db` | Database connectivity    |

Future business endpoints will be versioned under `/api/v1/...`.

## Architecture

```
app/
├── api/          # HTTP routes (API layer)
├── schemas/      # Pydantic request/response models
├── services/     # Business logic
├── repositories/ # Data access
├── models/       # SQLAlchemy models
├── core/         # Config, database, logging
├── exceptions/   # Exception hierarchy & handlers
└── utils/        # Shared utilities
```

## Environment Separation

Configuration is centralized in `app/core/config.py` and driven by environment variables:

| Environment   | `APP_ENV` value  |
|---------------|------------------|
| Development   | `development`    |
| Testing       | `testing`        |
| Production    | `production`     |

## Account Registration & CEO Approval Flow

1. Student registers via `/api/v1/auth/register` (created with `status = PENDING`, `role = STUDENT`, `is_active = false`).
2. Pending students cannot log in until approved.
3. CEO reviews pending students via `GET /api/v1/users/pending` (or `GET /api/v1/users?status=PENDING`).
4. CEO approves account via `PATCH /api/v1/users/{user_id}/approve` (transitions to `status = APPROVED`, `is_active = true`).
5. Approved student logs in normally with JWT access tokens.
6. CEO may optionally reject an account via `PATCH /api/v1/users/{user_id}/reject` or promote/demote via `PATCH /api/v1/users/{user_id}/role`.


## License

Private — University Bus Management System.
