# SocietySphere — Developer Contribution Guide

**Document Version:** 1.0.0  
**Project:** SocietySphere Multi-Tenant SaaS Platform  

---

## 1. Introduction & Engineering Philosophy

Welcome to the SocietySphere engineering team. SocietySphere is designed for long-term scalability, deterministic financial accounting, and enterprise-grade multi-tenant security.

To maintain architectural integrity, all contributors must adhere to the **Four-Stage Engineering Lifecycle**:
```
┌─────────────────┐     ┌──────────────────────┐     ┌────────────────────────────┐     ┌──────────────────┐
│ 1. Implement    │ ──> │ 2. Validate          │ ──> │ 3. Architect Review        │ ──> │ 4. Lock & Merge  │
│ Strict scope    │     │ Pytest, linters,     │     │ Blast radius, security,    │     │ Formal approval  │
│ boundaries      │     │ Checkov, dual IaC    │     │ edge cases, compliance     │     │ sign-off         │
└─────────────────┘     └──────────────────────┘     └────────────────────────────┘     └──────────────────┘
```

---

## 2. Branching & Git Workflow

### 2.1 Branch Naming Conventions
- Features: `feature/<phase-or-domain>-<short-description>` (e.g., `feature/22g-observability-alarms`)
- Bug Fixes: `fix/<issue-id>-<short-description>` (e.g., `fix/pg-pool-timeout`)
- Infrastructure: `infra/<component>-<change>` (e.g., `infra/cloudwatch-dashboards`)
- Documentation: `docs/<topic>` (e.g., `docs/handover-guide`)

### 2.2 Commit Message Standards (Conventional Commits)
Write imperative, concise commit messages:
```
<type>(<scope>): <short summary>

[optional body explaining rationale and non-obvious trade-offs]
```
Valid types:
- `feat`: New user-facing or domain feature.
- `fix`: Bug fix.
- `infra`: Terraform/OpenTofu or CI/CD modifications.
- `test`: Adding or updating test cases.
- `refactor`: Code refactoring without behavioral alterations.
- `docs`: Documentation updates.
- `chore`: Dependency updates, tooling adjustments.

---

## 3. Strict Development Boundaries

When contributing to SocietySphere:
1. **Never Modify Locked Phases:** Phases 1–21 and Phases 22A–22E are frozen and verified. Any changes to completed domains require an explicit Architecture Change Proposal (ACP).
2. **Never Create Uncoordinated Migrations:** The Alembic migration head is strictly locked at `20261102_0025_saas_billing_automation.py`. New database schema changes must be approved by the Principal Database Architect.
3. **Zero Cloud Provisioning in PRs:** Never execute `tofu apply` or `terraform apply` on developer workstations or in automated PR pipelines. Cloud resource changes must go through approved deployment gates.
4. **Zero Secrets in Code:** Never hardcode credentials, tokens, or environment-specific connection strings. Use `.env.example` as a template and rely on AWS Secrets Manager in cloud environments.

---

## 4. Local Development & Quality Gates

Before opening a pull request, verify all local quality gates:

### 4.1 Backend (Python 3.12)
```powershell
# 1. Run unit & integration tests
pytest -v

# 2. Run Ruff linter
ruff check apps/api tests

# 3. Verify formatting
ruff format --check apps/api tests

# 4. Verify static type checking
mypy apps/api tests
```

### 4.2 Frontend (TypeScript / Next.js)
```powershell
cd apps/web

# 1. TypeScript compilation check
npm run typecheck

# 2. ESLint verification
npm run lint

# 3. Test production build
npm run build
```

### 4.3 Infrastructure as Code (OpenTofu & Terraform)
```powershell
# Run the automated dual validation suite
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1 -IacTool tofu
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1 -IacTool terraform

# Run Checkov security scanning
checkov -d infrastructure/terraform --config-file infrastructure/terraform/.checkov.yaml

# Run compliance tests
python -m pytest infrastructure/terraform/tests/test_compliance.py -v
```

---

## 5. Pull Request Submission Checklist

When opening a Pull Request:
- [ ] PR title adheres to Conventional Commits format.
- [ ] Description clearly references the target milestone/phase and explains the design decisions.
- [ ] No changes to `apps/` or database migrations unless explicitly authorized by the task scope.
- [ ] All automated tests pass (pytest, mypy, ruff, Checkov, compliance suite).
- [ ] No unencrypted secrets, `.env` files, or `.terraform/` directories included in the commit.
- [ ] Architectural impact documented in an implementation report.
