variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "qa"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zones" {
  description = "Target availability zones"
  type        = list(string)
  default     = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs"
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
}

variable "app_subnet_cidrs" {
  description = "Application subnet CIDRs"
  type        = list(string)
  default     = ["10.20.10.0/22", "10.20.14.0/22", "10.20.18.0/22"]
}

variable "data_subnet_cidrs" {
  description = "Data subnet CIDRs"
  type        = list(string)
  default     = ["10.20.30.0/24", "10.20.31.0/24", "10.20.32.0/24"]
}

variable "rds_instance_class" {
  description = "RDS compute class for QA"
  type        = string
  default     = "db.t4g.medium"
}

variable "redis_node_type" {
  description = "Redis compute class for QA"
  type        = string
  default     = "cache.t4g.small"
}

variable "mq_instance_type" {
  description = "Amazon MQ compute class for QA"
  type        = string
  default     = "mq.t3.micro"
}
