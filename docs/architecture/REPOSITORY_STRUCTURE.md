# SocietySphere Repository Structure

This document details the directory topology and architecture boundaries of the SocietySphere codebase.

```
/
├── .github/
│   └── workflows/
│       └── ci.yml                 # Automated CI quality gate (lint, mypy, pytest, tsc, build)
├── apps/
│   ├── api/                       # Python / FastAPI Backend Service
│   │   ├── alembic/               # Database migration definitions & version history
│   │   │   ├── versions/          # Individual migration revision scripts
│   │   │   ├── env.py             # Migration execution environment (asyncpg)
│   │   │   └── script.py.mako     # Migration template
│   │   ├── src/
│   │   │   ├── api/               # API presentation routers & versioned endpoints
│   │   │   │   └── v1/            # Version 1 API routers (/api/v1)
│   │   │   │       └── endpoints/ # Health, version & future domain routers
│   │   │   ├── cache/             # Redis client, session manager & caching abstractions
│   │   │   ├── core/              # Config (Pydantic v2), logging, exceptions, middleware
│   │   │   ├── database/          # SQLAlchemy 2.x async engine, sessions, declarative Base
│   │   │   ├── events/            # RabbitMQ broker connection & publishing abstractions
│   │   │   ├── storage/           # S3-compatible object storage client (MinIO / AWS S3)
│   │   │   └── main.py            # FastAPI application factory, lifespan & middleware setup
│   │   ├── alembic.ini            # Alembic configuration
│   │   ├── requirements.txt       # Production backend runtime dependencies
│   │   └── requirements-dev.txt   # Development, testing & linting dependencies
│   │
│   └── web/                       # Next.js 14+ Frontend Application
│       ├── src/
│       │   ├── app/               # Next.js App Router (layout, loading, error, not-found, page)
│       │   ├── components/
│       │   │   └── ui/            # Accessible design system primitives (Easy, Standard, Admin)
│       │   └── lib/               # Universal API client with correlation & tenant headers
│       ├── next.config.js         # Next.js production & security headers configuration
│       ├── package.json           # Frontend dependencies & build scripts
│       ├── tailwind.config.js     # Tailwind CSS theme extensions (accessible typography, modes)
│       └── tsconfig.json          # TypeScript strict-mode configuration
│
├── packages/
│   ├── config/                    # Shared linting and build configurations
│   └── shared/                    # Shared domain types, contracts & schemas
│
├── infrastructure/
│   ├── docker/                    # Multi-stage production and dev Dockerfiles
│   │   ├── Dockerfile.api         # Python slim container image
│   │   └── Dockerfile.web         # Next.js alpine container image
│   ├── nginx/
│   │   └── nginx.conf             # Production reverse proxy, rate-limiting & SSL gateway
│   └── scripts/                   # Operations & maintenance helper scripts
│
├── docs/
│   ├── adr/                       # Architectural Decision Records (ADR 001 - 011)
│   ├── api/                       # API standards, versioning & OpenAPI contracts
│   ├── architecture/              # High-level architecture, baseline & component maps
│   ├── database/                  # Schema design, RLS policies & migration guides
│   ├── deployment/                # Local development & production orchestration guides
│   ├── frontend/                  # Design system, accessibility & mode guidelines
│   ├── security/                  # Zero-trust, secret handling & security baseline
│   └── testing/                   # QA strategy, test matrices & test execution
│
├── tests/                         # Backend test suite (pytest, pytest-asyncio, httpx)
├── docker-compose.yml             # Local multi-service development orchestrator
├── pyproject.toml                 # Root Python tooling configurations (pytest, ruff, mypy)
├── .env.example                   # Strongly typed environment variable documentation template
└── README.md                      # Comprehensive developer onboarding & operations guide
```
