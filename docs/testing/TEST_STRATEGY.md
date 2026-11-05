# SocietySphere Test Strategy & QA Framework

## 1. Testing Philosophy & Standards
SocietySphere is a production-grade multi-tenant platform managing critical financial and physical security workflows. The test strategy enforces:
1. **Deterministic Execution**: Zero flakiness; tests must produce consistent, reproducible outcomes without depending on external unmanaged services.
2. **Tenant Boundary Penetration Testing**: Every module from Phase 2 onward must include security tests attempting cross-tenant access to guarantee zero data leakage.
3. **Financial Invariant Verification**: All double-entry ledgers, dues, penalties, and tax calculations must achieve 100% test coverage with edge-case boundary validation.
4. **Accessibility Compliance**: Frontend components must be tested for keyboard navigability, ARIA attributes, and color contrast compliance.

## 2. Test Pyramid & Categorization

```
               / \
              /   \     E2E Journeys (Playwright)
             /-----\    Critical User Flows, Gate Approvals, Payments
            /       \
           /---------\  Integration & API Tests (pytest + httpx / TestClient)
          /           \ Multi-Tenant Isolation, RLS Policies, Database Migrations
         /-------------\
        /               \ Unit Tests (pytest, Vitest)
       /-----------------\ Financial Invariants, DTO Validation, Business Rules
```

### 2.1 Backend Unit & Integration Tests (pytest)
- **Framework**: `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`.
- **Environment**: Isolated `testing` environment initialized via `tests/conftest.py`.
- **Coverage Areas**:
  - Application startup/shutdown lifespan.
  - Health & readiness probes (`/health`, `/health/live`, `/health/ready`).
  - Configuration parsing, type enforcement, and production constraint guards.
  - Correlation ID injection and security response headers.
  - Centralized RFC 7807 error format and exception handlers.

### 2.2 Frontend Quality Gates
- **Type Safety**: `npm run typecheck` (`tsc --noEmit`) under TypeScript strict mode.
- **Code Quality**: `npm run lint` (`next lint` / ESLint).
- **Build Verification**: `npm run build` validating production compilation.

## 3. Test Execution Commands

### Running Backend Tests:
```powershell
# Run complete test suite with verbose output
.\.venv\Scripts\pytest -v

# Run with test coverage report
.\.venv\Scripts\pytest --cov=apps/api/src --cov-report=term-missing
```

### Running Frontend Checks:
```powershell
cd apps/web

# TypeScript type checking
npm run typecheck

# ESLint validation
npm run lint

# Production build verification
npm run build
```
