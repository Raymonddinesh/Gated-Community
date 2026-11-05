# SocietySphere — QA Environment

## Overview
Deploys an automated, isolated QA environment for integration testing, PR regression suites, and load validation:
* **Network:** Independent VPC (`10.20.0.0/16`) to guarantee complete isolation from dev and prod.
* **Storage:** Ephemeral documents bucket with teardown permission (`force_destroy = true`).
* **Validation:** Used by CI/CD pipelines to run end-to-end integration tests.

## Validation
```bash
tofu init -backend=false
tofu validate
```
