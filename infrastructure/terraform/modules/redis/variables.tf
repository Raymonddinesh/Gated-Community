variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "data_subnet_ids" {
  description = "List of isolated data subnet IDs for ElastiCache"
  type        = list(string)
}

variable "sg_redis_id" {
  description = "Security group ID for Redis"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS Customer Managed Key ARN for Redis encryption at rest"
  type        = string
}

variable "node_type" {
  description = "ElastiCache instance node type"
  type        = string
  default     = "cache.m6g.large"
}

variable "multi_az" {
  description = "Enable Multi-AZ replication and auto-failover"
  type        = bool
  default     = true
}

variable "num_cache_clusters" {
  description = "Number of cache nodes in the replication group"
  type        = number
  default     = 2
}

variable "auth_token" {
  description = "Optional AUTH token for Redis in-transit authentication (min 16 chars)"
  type        = string
  default     = null
  sensitive   = true
}
