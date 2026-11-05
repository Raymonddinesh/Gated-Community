variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of KMS Customer Managed Key for CloudWatch Log Group encryption"
  type        = string
}

variable "log_retention_days" {
  description = "Log retention in days"
  type        = number
  default     = 30
}

variable "alert_sns_topic_arn" {
  description = "ARN of SNS topic for critical operational alarms"
  type        = string
  default     = ""
}
