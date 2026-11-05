# Master Broker Password Generation
resource "random_password" "mq_password" {
  length  = 24
  special = false # Avoid special characters that break AMQP connection URI encoding
}

# AWS Secrets Manager Secret for RabbitMQ Credentials
resource "aws_secretsmanager_secret" "mq_credentials" {
  name                    = "societysphere/${var.environment}/rabbitmq"
  description             = "Amazon MQ RabbitMQ credentials for SocietySphere ${var.environment}"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 0

  tags = {
    Name        = "societysphere-${var.environment}-mq-secret"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "mq_credentials" {
  secret_id = aws_secretsmanager_secret.mq_credentials.id
  secret_string = jsonencode({
    username = "mq_admin"
    password = random_password.mq_password.result
  })
}

# Amazon MQ RabbitMQ Broker (Managed Quorum Cluster)
resource "aws_mq_broker" "main" {
  broker_name        = "societysphere-${var.environment}-rabbitmq"
  engine_type        = "RabbitMQ"
  engine_version     = "3.13"
  host_instance_type = var.host_instance_type
  deployment_mode    = var.deployment_mode

  # Single instance uses 1 subnet; Quorum cluster uses multiple subnets
  subnet_ids = var.deployment_mode == "CLUSTER_MULTI_AZ" ? var.data_subnet_ids : [var.data_subnet_ids[0]]

  security_groups     = [var.sg_rabbitmq_id]
  publicly_accessible = false

  encryption_options {
    use_aws_owned_key = false
    kms_key_id        = var.kms_key_arn
  }

  auto_minor_version_upgrade = var.auto_minor_version_upgrade

  logs {
    general = true
    audit   = true
  }

  user {
    username = "mq_admin"
    password = random_password.mq_password.result
  }

  tags = {
    Name        = "societysphere-${var.environment}-rabbitmq"
    Environment = var.environment
  }
}
