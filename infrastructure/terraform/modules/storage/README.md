# SocietySphere — Storage Module

## Overview
Provisions an enterprise, regulatory-compliant S3 object store for maintenance invoices, payment receipts, and resident KYC uploads:
* **KMS CMK Encryption:** Encrypted with dedicated customer-managed key.
* **Public Access Block:** 100% private bucket; public access blocked.
* **TLS Transport Enforced:** Plain HTTP requests denied via bucket policy.
* **S3 Object Lock (Statutory Retention):** Compliance mode (6-year immutability) in production meeting Indian GST Act Section 36 requirements.
* **Lifecycle Rules:** Archives noncurrent invoice versions to Glacier after 90 days.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment name |
| `kms_key_arn` | string | n/a | CMK ARN for server-side encryption |
| `enable_object_lock` | bool | `false` | Enable statutory WORM immutability |
| `object_lock_retention_days` | number | `2190` | Retention duration in days (6 years) |
| `object_lock_mode` | string | `"GOVERNANCE"` | Mode: GOVERNANCE or COMPLIANCE |

## Outputs
* `bucket_id`: Bucket name.
* `bucket_arn`: Bucket ARN.
