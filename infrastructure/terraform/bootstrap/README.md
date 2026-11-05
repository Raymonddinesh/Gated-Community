# SocietySphere — Terraform Remote State Bootstrap

## Purpose
This bootstrap configuration provisions the foundational, chicken-and-egg AWS resources required to store and protect remote Terraform/OpenTofu state:
1. An S3 bucket with versioning, customer-managed KMS encryption, public access block, TLS-only policy, and version expiration lifecycle.
2. An AWS KMS Customer Managed Key (CMK) with annual rotation for envelope encryption of state files.
3. An optional DynamoDB table for environments requiring legacy table locking instead of S3 native lockfiles (`use_lockfile = true`).

## Important Notice
* **Do NOT run `terraform apply` or `tofu apply` on this module during Phase 22B.**
* This module is maintained for infrastructure documentation and one-time initial provisioning once cloud access authorization is formally granted in Phase 22C.

## Bootstrap Procedure (When Authorized)
1. Navigate to `infrastructure/terraform/bootstrap`.
2. Initialize with local state:
   ```bash
   tofu init
   ```
3. Plan and apply to create the state bucket and KMS key:
   ```bash
   tofu plan -out=bootstrap.tfplan
   tofu apply bootstrap.tfplan
   ```
4. Note the output `state_bucket_name` and `kms_key_arn`.
5. Populate backend configuration in `environments/{dev,qa,staging,production}`.
6. Migrate bootstrap's own state into the newly created S3 bucket if desired.
