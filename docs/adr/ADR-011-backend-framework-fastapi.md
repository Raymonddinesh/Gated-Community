# ADR 011: Backend Framework Alignment to Python & FastAPI

## Status
Accepted

## Context
In early Phase 0 drafting, Node.js/NestJS was initially considered. During Phase 1 engineering charter finalization, the platform directives mandate Python with FastAPI, Pydantic v2, and SQLAlchemy 2.x async.
We evaluated the requirements of SocietySphere:
1. Long-term production SaaS with multi-tenancy and high concurrent async I/O.
2. Complex financial algorithms, double-entry ledger calculations, deterministic reporting, and future AI/voice and analytics integration. Python is the industry-standard environment for scientific, financial, and AI/ML processing.
3. FastAPI provides exceptional asynchronous performance, native Pydantic v2 type safety, dependency injection, and automatic OpenAPI 3.0 generation required for web and mobile client code generation.
4. Clean Architecture and modular monolith structures are fully supported in Python via domain, application, and infrastructure package boundaries.

## Decision
1. **Backend Framework**: Adopt **FastAPI** on **Python 3.12** as the standard backend application runtime.
2. **Data & Schema**: Use **Pydantic v2** for DTO validation and domain serialization; **SQLAlchemy 2.x (async)** with **asyncpg** for database persistence; and **Alembic** for non-destructive version-controlled schema migrations.
3. **Caching & Asynchronous Messaging**: Use **Redis 7+** for caching, rate-limiting, and sessions; use **RabbitMQ** (via `aio-pika`/Celery) for reliable distributed background job execution.
4. **Architectural Parity**: All previously approved core architectural principles (Row-Level Security, tenant isolation, append-only ledgers, 13-role RBAC/ABAC, OpenAPI generation for mobile, and zero AI direct database access) remain unchanged and fully enforced.

## Consequences
### Positive
- Unified ecosystem for core accounting rules, deterministic reports, and future AI/voice reasoning.
- Native Pydantic v2 performance (Rust-based core) and validation ergonomics.
- Automatic OpenAPI 3.0 interactive documentation (`/docs`, `/redoc`) and client generation.
- Full async support for PostgreSQL, Redis, RabbitMQ, and S3 object storage.

### Negative / Trade-offs
- Developers must maintain strict discipline around asynchronous event loops (`async`/`await`) to avoid blocking I/O calls in route handlers.
