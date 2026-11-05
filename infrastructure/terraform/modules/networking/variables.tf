variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of Availability Zones in the region"
  type        = list(string)
  default     = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "app_subnet_cidrs" {
  description = "CIDR blocks for private application subnets"
  type        = list(string)
  default     = ["10.0.10.0/22", "10.0.14.0/22", "10.0.18.0/22"]
}

variable "data_subnet_cidrs" {
  description = "CIDR blocks for isolated data subnets"
  type        = list(string)
  default     = ["10.0.30.0/24", "10.0.31.0/24", "10.0.32.0/24"]
}

variable "single_nat_gateway" {
  description = "Deploy a single NAT Gateway across all AZs to optimize costs in non-production"
  type        = bool
  default     = true
}

variable "enable_vpc_flow_logs" {
  description = "Enable CloudWatch VPC Flow Logs for network traffic auditing"
  type        = bool
  default     = true
}

variable "flow_logs_retention_days" {
  description = "Retention period for VPC Flow Logs in CloudWatch"
  type        = number
  default     = 30
}

variable "kms_key_arn" {
  description = "ARN of KMS Customer Managed Key for CloudWatch Log Group encryption"
  type        = string
  default     = null
}

variable "enable_interface_endpoints" {
  description = "Enable AWS PrivateLink VPC Interface Endpoints for private AWS service communication"
  type        = bool
  default     = false
}

variable "interface_endpoints_services" {
  description = "List of AWS services to create VPC Interface Endpoints for when enabled"
  type        = list(string)
  default     = ["ecr.api", "ecr.dkr", "logs", "secretsmanager"]
}
