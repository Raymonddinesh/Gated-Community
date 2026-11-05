variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where ALB target groups and services reside"
  type        = string
  default     = ""
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for internet-facing Application Load Balancer"
  type        = list(string)
  default     = []
}

variable "app_subnet_ids" {
  description = "List of private application subnet IDs for ECS tasks"
  type        = list(string)
}

variable "sg_alb_id" {
  description = "Security group ID for Application Load Balancer"
  type        = string
  default     = ""
}

variable "sg_web_id" {
  description = "Security group ID for Next.js Web Frontend"
  type        = string
}

variable "sg_api_id" {
  description = "Security group ID for FastAPI Backend API"
  type        = string
}

variable "sg_workers_id" {
  description = "Security group ID for Background Workers"
  type        = string
}

variable "execution_role_arn" {
  description = "IAM role ARN for ECS task execution (ECR pull, secrets access)"
  type        = string
}

variable "task_role_arn" {
  description = "Fallback IAM role ARN for ECS tasks"
  type        = string
}

variable "task_role_web_arn" {
  description = "IAM role ARN for Frontend Web ECS tasks"
  type        = string
  default     = null
}

variable "task_role_api_arn" {
  description = "IAM role ARN for Backend API ECS tasks"
  type        = string
  default     = null
}

variable "task_role_workers_arn" {
  description = "IAM role ARN for Background Worker ECS tasks"
  type        = string
  default     = null
}

variable "db_secret_arn" {
  description = "Secrets Manager ARN for database credentials"
  type        = string
  default     = null
}

variable "app_secret_arn" {
  description = "Secrets Manager ARN for application secrets (JWT, Razorpay)"
  type        = string
  default     = null
}

variable "kms_key_arn" {
  description = "KMS Customer Managed Key ARN for ECR and CloudWatch encryption"
  type        = string
  default     = null
}

variable "web_image" {
  description = "Container image URI for Next.js Web Frontend"
  type        = string
  default     = "societysphere-web:latest"
}

variable "api_image" {
  description = "Container image URI for FastAPI API and Workers"
  type        = string
  default     = "societysphere-api:latest"
}

variable "web_desired_count" {
  description = "Desired number of Web Frontend tasks"
  type        = number
  default     = 2
}

variable "api_desired_count" {
  description = "Desired number of Backend API tasks"
  type        = number
  default     = 2
}

variable "workers_desired_count" {
  description = "Desired number of Background Worker tasks"
  type        = number
  default     = 2
}

variable "web_min_capacity" {
  description = "Minimum task count for Web autoscaling"
  type        = number
  default     = 1
}

variable "web_max_capacity" {
  description = "Maximum task count for Web autoscaling"
  type        = number
  default     = 5
}

variable "api_min_capacity" {
  description = "Minimum task count for API autoscaling"
  type        = number
  default     = 1
}

variable "api_max_capacity" {
  description = "Maximum task count for API autoscaling"
  type        = number
  default     = 10
}

variable "workers_min_capacity" {
  description = "Minimum task count for Workers autoscaling"
  type        = number
  default     = 1
}

variable "workers_max_capacity" {
  description = "Maximum task count for Workers autoscaling"
  type        = number
  default     = 5
}

variable "web_cpu" {
  description = "CPU units for Web task (e.g. 512, 1024)"
  type        = string
  default     = "1024"
}

variable "web_memory" {
  description = "Memory for Web task in MiB (e.g. 1024, 2048)"
  type        = string
  default     = "2048"
}

variable "api_cpu" {
  description = "CPU units for API task (e.g. 1024, 2048)"
  type        = string
  default     = "1024"
}

variable "api_memory" {
  description = "Memory for API task in MiB (e.g. 2048, 4096)"
  type        = string
  default     = "2048"
}

variable "workers_cpu" {
  description = "CPU units for Workers task (e.g. 1024, 2048)"
  type        = string
  default     = "1024"
}

variable "workers_memory" {
  description = "Memory for Workers task in MiB (e.g. 2048, 4096)"
  type        = string
  default     = "2048"
}

variable "alb_target_group_web_arn" {
  description = "Pre-existing ARN of ALB target group for Web Frontend (optional override)"
  type        = string
  default     = ""
}

variable "alb_target_group_api_arn" {
  description = "Pre-existing ARN of ALB target group for Backend API (optional override)"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM Certificate ARN for HTTPS listener on ALB"
  type        = string
  default     = null
}

variable "enable_alb" {
  description = "Whether to provision the Application Load Balancer in this module"
  type        = bool
  default     = true
}

variable "enable_autoscaling" {
  description = "Whether to enable Application Auto Scaling policies"
  type        = bool
  default     = true
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection on Application Load Balancer"
  type        = bool
  default     = false
}

variable "enable_docs_routing" {
  description = "Whether to route /docs, /redoc, and /openapi.json through ALB (must be false in production)"
  type        = bool
  default     = false
}

variable "health_check_grace_period_seconds" {
  description = "Seconds to ignore failing load balancer health checks on newly instantiated tasks"
  type        = number
  default     = 60
}
