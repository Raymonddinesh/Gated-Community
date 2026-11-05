# SocietySphere Infrastructure as Code Upgrade Procedure

## 1. Engine & Provider Version Pinning Strategy

SocietySphere strictly pins all IaC toolchain versions and provider constraints to ensure deterministic, reproducible infrastructure deployments across all environments.

### 1.1 Toolchain & Provider Constraints
- **OpenTofu Engine:** `>= 1.9.0, < 2.0.0`
- **Terraform Engine:** `>= 1.10.0, < 2.0.0`
- **AWS Provider:** `~> 5.80` (allows non-breaking patch/minor upgrades within 5.x)
- **Random Provider:** `~> 3.6`
- **Dependency Lock File:** `.terraform.lock.hcl` committed to source control for each module and environment to lock cryptographic hashes.

---

## 2. Upgrading OpenTofu / Terraform

When a new minor or patch version of OpenTofu is released:

1. **Local Developer Verification:**
   - Update `tofu` in a local branch.
   - Run the validation suite:
     ```powershell
     powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1 -IacTool tofu
     ```
2. **State Format Compatibility Check:**
   - Review release notes for any state format schema changes.
   - Run `tofu plan` across `dev` to verify zero unexpected drift.
3. **Engine Constraint Update:**
   - Update `required_version` across all `versions.tf` files.
4. **CI/CD Pipeline Update:**
   - Update the container image or runner tool version in the GitHub Actions / GitLab CI pipeline.

---

## 3. Upgrading AWS Provider Versions

Provider upgrades must be systematically tested against non-production environments before staging or production.

### Step 3.1: Check Provider Changelog
Review [terraform-provider-aws releases](https://github.com/hashicorp/terraform-provider-aws/releases) for:
- Deprecated attributes or resource schema alterations.
- Bug fixes affecting VPC, RDS, ECS, ElastiCache, or Amazon MQ resources.

### Step 3.2: Update Provider Lock Files
1. Update constraint in `versions.tf` if bumping minor/major version (e.g., `~> 5.90` or `~> 6.0`).
2. Re-generate lock hashes across all target architectures:
   ```bash
   tofu providers lock -platform=windows_amd64 -platform=linux_amd64 -platform=darwin_arm64
   ```
3. Run `tofu init -upgrade -backend=false` in each module and environment.

### Step 3.3: Lint & Security Re-verification
Execute TFLint and tfsec to ensure no newly introduced deprecations or security rules are triggered:
```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1
```

### Step 3.4: Plan Verification
Run `tofu plan` in `dev` and inspect output:
- **No changes expected** for existing unchanged resources.
- If in-place updates or resource replacements are detected, investigate parameter diffs before proceeding.

---

## 4. Module Versioning & Refactoring Rules

1. **Interface Stability:** Input variable names and types in `modules/*` are considered public contracts. Renaming or removing variables is a breaking change.
2. **Output Additions:** Adding new outputs to modules is non-breaking and encouraged for inter-module composability.
3. **Decoupled Security Group Rules:** Any new network port or inter-service connection must be added as a standalone `aws_security_group_rule` resource rather than inline within `aws_security_group` to maintain an acyclic dependency graph.
4. **Strict RLS & Data Protection:** Never alter `manage_master_user_password = true`, `rds.force_ssl = 1`, or S3 Object Lock retention parameters without explicit Security Architect sign-off.
