# SOCIETYSPHERE — DEPLOYMENT & OPERATIONS RUNBOOK

**Target Audience**: DevOps Engineers, System Administrators, and SREs  

---

## 1. ENVIRONMENT & PREREQUISITES
- Python 3.11+
- Node.js 18+ / npm
- PostgreSQL 15+ with RLS support
- Redis 7+
- RabbitMQ 3.11+

---

## 2. BACKEND API SETUP & DATABASE MIGRATION
```bash
# 1. Activate Python virtual environment
cd c:\SocApp
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Run Alembic Database Migrations (0001 to 0020)
.venv\Scripts\python.exe -m alembic upgrade head

# 3. Seed Development & Initial Permission Data
.venv\Scripts\python.exe infrastructure/scripts/seed_dev_data.py

# 4. Start FastAPI Backend Server
.venv\Scripts\python.exe -m uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000
```

---

## 3. FRONTEND NEXT.JS BUILD & STARTUP
```bash
# 1. Install frontend dependencies
npm --prefix apps/web install

# 2. Execute Production Build
npm --prefix apps/web run build

# 3. Start Production Next.js Server
npm --prefix apps/web start -- -p 3000
```

---

## 4. HEALTH CHECKS & VERIFICATION
- Backend Health Probe: `curl http://localhost:8000/api/v1/health`
- Backend Version Probe: `curl http://localhost:8000/api/v1/version`
- Test Suite Execution: `.venv\Scripts\python.exe -m pytest`

---

## 5. BACKUP & RECOVERY CONSIDERATIONS
- Daily PostgreSQL `pg_dump` of society databases.
- Database backups preserve RLS policies and foreign key integrity.
