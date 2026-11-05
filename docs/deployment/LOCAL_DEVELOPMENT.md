# Local Development & Orchestration Guide

This guide walks you through setting up and running SocietySphere in your local development environment.

## 1. Prerequisites
- **Python**: Version 3.12 (Standardized runtime)
- **Node.js**: Version 20+ LTS (with npm 10+)
- **Docker & Docker Compose**: Docker Desktop 24+
- **Git**: 2.40+

## 2. Initial Setup

### 2.1 Clone and Environment Configuration
```powershell
# Copy environment template
cp .env.example .env
```

Review `.env` and adjust database credentials, ports, or service endpoints if necessary.

### 2.2 Backend Environment Setup
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r apps/api/requirements-dev.txt
```

### 2.3 Frontend Environment Setup
```powershell
cd apps/web
npm install
cd ../..
```

## 3. Running via Docker Compose (Recommended)

Docker Compose starts all backing services (PostgreSQL, Redis, RabbitMQ, MinIO) as well as the API and Web applications:

```powershell
# Build and start all services in the background
docker-compose up -d

# View service logs
docker-compose logs -f

# Verify service health
docker-compose ps
```

### Exposed Service Endpoints:
- **Web Frontend**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Backend**: [http://localhost:8000](http://localhost:8000)
- **API Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL**: `localhost:5432` (`societysphere_dev`)
- **Redis**: `localhost:6379`
- **RabbitMQ Management Dashboard**: [http://localhost:15672](http://localhost:15672) (user: `guest`, pass: `guest`)
- **MinIO Object Storage Console**: [http://localhost:9001](http://localhost:9001) (user: `minioadmin`, pass: `minioadminpassword`)

## 4. Running Standalone (Without Full Docker)

If you have native or containerized backing services running locally:

### Run Backend API:
```powershell
.\.venv\Scripts\uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run Frontend Web:
```powershell
cd apps/web
npm run dev
```

## 5. Running Database Migrations (Alembic)
```powershell
# Apply latest migrations
.\.venv\Scripts\alembic -c apps/api/alembic.ini upgrade head

# Revert previous migration
.\.venv\Scripts\alembic -c apps/api/alembic.ini downgrade -1

# Generate a new migration (Phase 2+)
.\.venv\Scripts\alembic -c apps/api/alembic.ini revision --autogenerate -m "describe_migration"
```

## 6. Running Tests & Quality Checks
```powershell
# Backend lint, typecheck and pytest
.\.venv\Scripts\ruff check apps\api tests
.\.venv\Scripts\mypy apps\api tests
.\.venv\Scripts\pytest -v

# Frontend lint and typecheck
cd apps/web
npm run lint
npm run typecheck
npm run build
cd ../..
```
