variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "documents_bucket_arn" {
  description = "ARN of the S3 documents bucket for scoped IAM access"
  type        = string
  default     = ""
}

variable "ses_sender_email" {
  description = "Verified SES email address for transaction notifications"
  type        = string
  default     = "noreply@societysphere.com"
}
