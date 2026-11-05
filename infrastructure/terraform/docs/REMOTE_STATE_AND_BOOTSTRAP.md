# SocietySphere Remote State & Bootstrap Guide

## Overview

SocietySphere utilizes an S3 backend with customer-managed KMS key (CMK) encryption and native S3 state locking (`use_lockfile = true`), eliminating the need for a separate DynamoDB lock table while providing equivalent atomic lock safety.

---

## 1. Remote State Architecture

```
+-------------------------------------------------------------------------------+
|                             AWS ap-south-1 (Mumbai)                          |
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  | S3 State Bucket: societysphere-terraform-state-${environment}           |  |
|  |                                                                         |  |
|  |  +-------------------------------------------------------------------+  |  |
|  |  | State File: environments/${environment}/terraform.tfstate          |  |  |
|  |  | Native Lock: environments/${environment}/terraform.tfstate.tflock   |  |  |
|  |  +-------------------------------------------------------------------+  |  |
|  |                                                                         |  |
|  |  * Bucket Versioning: Enabled (preserves full historical state)         |  |
|  |  * Public Access Block: All 4 flags set to TRUE                         |  |
|  |  * TLS Enforcement: Denies requests with aws:SecureTransport = false    |  |
|  |  * SSE: aws:kms using dedicated KMS CMK with annual key rotation       |  |
|  |  * Lifecycle: Noncurrent versions expire after 90 days                 |  |
|  +-------------------------------------------------------------------------+  |
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  | KMS CMK: alias/societysphere-terraform-state-${environment}             |  |
|  | * Automatic 365-day rotation enabled                                   |  |
|  | * Multi-service key policy restricting access to admin & IaC roles     |  |
|  +-------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------+
```

---

## 2. Step-by-Step Bootstrap Procedure

The bootstrap configuration resides in `infrastructure/terraform/bootstrap/`. It creates the S3 state bucket and KMS CMK before any environment modules are applied.

### Step 2.1: Initialize Bootstrap Locally
The bootstrap module initially runs with a local state backend because the remote bucket does not exist yet.

```bash
cd infrastructure/terraform/bootstrap
tofu init
```

### Step 2.2: Review Bootstrap Plan
```bash
tofu plan -var="environment=dev" -out=bootstrap.tfplan
```

### Step 2.3: Apply Bootstrap (Create S3 & KMS)
```bash
tofu apply bootstrap.tfplan
```

### Step 2.4: Migrate Bootstrap State to Remote S3 (Optional)
Once the bucket is created, you may optionally configure an S3 backend in `bootstrap/versions.tf` and run:
```bash
tofu init -migrate-state
```

---

## 3. Environment Remote State Configuration

Each environment (`dev`, `qa`, `staging`, `production`) contains a backend block in its `versions.tf`:

```hcl
terraform {
  backend "s3" {
    bucket       = "societysphere-terraform-state-production"
    key          = "environments/production/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

### Native S3 Lockfile Feature (`use_lockfile = true`)
- Supported natively in **OpenTofu >= 1.8.0** and **HashiCorp Terraform >= 1.10.0**.
- Coordinates atomic state locks using S3 conditional writes on `.tflock` objects.
- Completely avoids the operational overhead and provisioning of a DynamoDB state lock table.
- A fallback DynamoDB table resource is provided in the `bootstrap` module if legacy tools (< 1.8) ever require it.

---

## 4. Disaster Recovery & State Recovery

### 4.1 Corrupted State Recovery
Because S3 Bucket Versioning is permanently enabled:
1. List historical versions:
   ```bash
   aws s3api list-object-versions \
     --bucket societysphere-terraform-state-production \
     --prefix environments/production/terraform.tfstate
   ```
2. Download the last known good version:
   ```bash
   aws s3api get-object \
     --bucket societysphere-terraform-state-production \
     --key environments/production/terraform.tfstate \
     --version-id <PREVIOUS_VERSION_ID> \
     recovered_state.tfstate
   ```
3. Push restored state:
   ```bash
   tofu state push recovered_state.tfstate
   ```

### 4.2 Clearing a Stale Lock
If a CI/CD job crashes while holding a lock:
```bash
tofu force-unlock <LOCK_ID>
```
With S3 native locking, removing the lockfile object also releases the lock if required:
```bash
aws s3 rm s3://societysphere-terraform-state-production/environments/production/terraform.tfstate.tflock
```
