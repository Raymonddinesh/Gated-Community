variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of KMS Customer Managed Key for S3 bucket encryption"
  type        = string
}

variable "enable_object_lock" {
  description = "Enable S3 Object Lock for statutory compliance (GST invoice preservation)"
  type        = bool
  default     = false
}

variable "object_lock_retention_days" {
  description = "Default retention period in days for Object Lock (e.g., 2190 days = 6 years)"
  type        = number
  default     = 2190
}

variable "object_lock_mode" {
  description = "Object lock mode: GOVERNANCE for non-prod, COMPLIANCE for production"
  type        = string
  default     = "GOVERNANCE"
}

variable "cors_allowed_origins" {
  description = "Allowed origins for S3 presigned upload/download direct browser CORS"
  type        = list(string)
  default     = ["https://*.societysphere.com"]
}
