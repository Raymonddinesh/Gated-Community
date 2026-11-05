variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "data_subnet_ids" {
  description = "List of isolated data subnet IDs for the database subnet group"
  type        = list(string)
}

variable "sg_rds_id" {
  description = "Security group ID for RDS PostgreSQL"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS Customer Managed Key ARN for RDS storage encryption"
  type        = string
}

variable "instance_class" {
  description = "Database instance compute class"
  type        = string
  default     = "db.m6g.large"
}

variable "allocated_storage" {
  description = "Initial allocated storage in GB"
  type        = number
  default     = 100
}

variable "max_allocated_storage" {
  description = "Maximum storage limit in GB for autoscaling"
  type        = number
  default     = 500
}

variable "multi_az" {
  description = "Enable Multi-AZ synchronous replication across availability zones"
  type        = bool
  default     = true
}

variable "backup_retention_period" {
  description = "Automated backup retention window in days"
  type        = number
  default     = 35
}

variable "deletion_protection" {
  description = "Prevent accidental database deletion"
  type        = bool
  default     = true
}

variable "enable_db_proxy" {
  description = "Whether to provision an Amazon RDS Proxy for connection pooling"
  type        = bool
  default     = true
}

variable "idle_in_transaction_session_timeout" {
  description = "Time in milliseconds to terminate idle transactions"
  type        = string
  default     = "60000"
}

variable "statement_timeout" {
  description = "Time in milliseconds to terminate long-running queries"
  type        = string
  default     = "30000"
}

variable "monitoring_interval" {
  description = "Interval in seconds for RDS Enhanced Monitoring (0 to disable, 1, 5, 10, 15, 30, 60)"
  type        = number
  default     = 60
}
