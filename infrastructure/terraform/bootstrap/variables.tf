variable "aws_region" {
  description = "AWS deployment region for remote state infrastructure"
  type        = string
  default     = "ap-south-1"
}

variable "bucket_prefix" {
  description = "Prefix for the remote state S3 bucket"
  type        = string
  default     = "societysphere-terraform-state"
}

variable "kms_key_alias" {
  description = "Alias for the KMS key used to encrypt remote state"
  type        = string
  default     = "alias/societysphere-terraform-state-key"
}

variable "enable_dynamodb_lock" {
  description = "Whether to provision an optional DynamoDB lock table (if not using S3 native lockfile)"
  type        = bool
  default     = false
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table for state locking if enabled"
  type        = string
  default     = "societysphere-terraform-locks"
}

variable "environment" {
  description = "Environment identifier (e.g., bootstrap, shared)"
  type        = string
  default     = "bootstrap"
}
