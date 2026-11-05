variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "staging"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.30.0.0/16"
}

variable "availability_zones" {
  description = "Target availability zones"
  type        = list(string)
  default     = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs"
  type        = list(string)
  default     = ["10.30.1.0/24", "10.30.2.0/24", "10.30.3.0/24"]
}

variable "app_subnet_cidrs" {
  description = "Application subnet CIDRs"
  type        = list(string)
  default     = ["10.30.10.0/22", "10.30.14.0/22", "10.30.18.0/22"]
}

variable "data_subnet_cidrs" {
  description = "Data subnet CIDRs"
  type        = list(string)
  default     = ["10.30.30.0/24", "10.30.31.0/24", "10.30.32.0/24"]
}

variable "rds_instance_class" {
  description = "RDS compute class for staging"
  type        = string
  default     = "db.m6g.large"
}

variable "redis_node_type" {
  description = "Redis compute class for staging"
  type        = string
  default     = "cache.m6g.large"
}

variable "mq_instance_type" {
  description = "Amazon MQ compute class for staging"
  type        = string
  default     = "mq.m5.large"
}
