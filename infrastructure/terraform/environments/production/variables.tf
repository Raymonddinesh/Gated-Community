variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "production"
}

variable "production_apply_authorized" {
  description = "Explicit safety gate. Must be set to true to authorize execution in production. Defaults to false to prevent accidental provisioning."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "Production VPC CIDR block (Phase 22A: 10.0.0.0/16)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Target availability zones across 3 Mumbai AZs"
  type        = list(string)
  default     = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs across 3 AZs"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "app_subnet_cidrs" {
  description = "Application subnet CIDRs across 3 AZs (/22 allocating 1022 IPs each)"
  type        = list(string)
  default     = ["10.0.10.0/22", "10.0.14.0/22", "10.0.18.0/22"]
}

variable "data_subnet_cidrs" {
  description = "Isolated data subnet CIDRs across 3 AZs"
  type        = list(string)
  default     = ["10.0.30.0/24", "10.0.31.0/24", "10.0.32.0/24"]
}

variable "rds_instance_class" {
  description = "RDS PostgreSQL compute class (Option B: db.m6g.xlarge 4 vCPU / 16 GB)"
  type        = string
  default     = "db.m6g.xlarge"
}

variable "redis_node_type" {
  description = "ElastiCache Redis compute class (cache.m6g.large 2 vCPU / 6.38 GB)"
  type        = string
  default     = "cache.m6g.large"
}

variable "mq_instance_type" {
  description = "Amazon MQ RabbitMQ compute class (mq.m5.large 2 vCPU / 8 GB)"
  type        = string
  default     = "mq.m5.large"
}
