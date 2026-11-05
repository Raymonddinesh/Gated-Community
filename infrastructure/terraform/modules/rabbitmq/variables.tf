variable "environment" {
  description = "Environment identifier (e.g., dev, qa, staging, production)"
  type        = string
}

variable "data_subnet_ids" {
  description = "List of isolated data subnet IDs across AZs"
  type        = list(string)
}

variable "sg_rabbitmq_id" {
  description = "Security group ID for Amazon MQ RabbitMQ"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS Customer Managed Key ARN for message broker encryption"
  type        = string
}

variable "host_instance_type" {
  description = "Broker host instance type (e.g. mq.m5.large, mq.t3.micro)"
  type        = string
  default     = "mq.m5.large"
}

variable "deployment_mode" {
  description = "Broker deployment mode: SINGLE_INSTANCE or CLUSTER_MULTI_AZ"
  type        = string
  default     = "CLUSTER_MULTI_AZ"
}

variable "auto_minor_version_upgrade" {
  description = "Enable automatic minor version upgrades"
  type        = bool
  default     = true
}
