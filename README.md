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

## WhatsApp OTP Configuration

| Configuration Variable | Default / Canonical Value | Purpose |
| :--- | :--- | :--- |
| `WHATSAPP_BUSINESS_NUMBER` | `+201222775530` | Company WhatsApp Business / Sender number |
| `WHATSAPP_PROVIDER` | `mock` (dev/test) / `cloud_api` (prod) | WhatsApp integration provider |
| `WHATSAPP_PHONE_NUMBER_ID` | Secret | Cloud API Phone Number ID (Production) |
| `WHATSAPP_API_TOKEN` | Secret | Cloud API Bearer Token (Production) |

> **Note:** The configured WhatsApp business number (`+201222775530`) is strictly the sender. OTP messages are sent FROM this number TO the phone number supplied by the user during registration.


## License

Private — University Bus Management System.
