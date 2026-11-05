# Database Subnet Group (Isolated Data Tier)
resource "aws_db_subnet_group" "main" {
  name        = "societysphere-${var.environment}-db-subnet-group"
  description = "Isolated database subnets for SocietySphere RDS PostgreSQL"
  subnet_ids  = var.data_subnet_ids

  tags = {
    Name        = "societysphere-${var.environment}-db-subnet-group"
    Environment = var.environment
  }
}

# PostgreSQL 16 Parameter Group (Tuned for SocietySphere SaaS)
resource "aws_db_parameter_group" "main" {
  name        = "societysphere-${var.environment}-pg16-params"
  family      = "postgres16"
  description = "Optimized PostgreSQL 16 parameter group for SocietySphere multi-tenant RLS"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "shared_buffers"
    value = "{DBInstanceClassMemory/4}"
  }

  parameter {
    name  = "work_mem"
    value = "16384" # 16MB
  }

  parameter {
    name  = "maintenance_work_mem"
    value = "262144" # 256MB
  }

  parameter {
    name  = "checkpoint_completion_target"
    value = "0.9"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "250" # Log slow queries > 250ms
  }

  parameter {
    name  = "idle_in_transaction_session_timeout"
    value = var.idle_in_transaction_session_timeout
  }

  parameter {
    name  = "statement_timeout"
    value = var.statement_timeout
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "log_lock_waits"
    value = "1"
  }

  tags = {
    Name        = "societysphere-${var.environment}-pg16-params"
    Environment = var.environment
  }
}

# Amazon RDS PostgreSQL Instance
resource "aws_db_instance" "main" {
  identifier     = "societysphere-${var.environment}-postgres"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  parameter_group_name   = aws_db_parameter_group.main.name
  vpc_security_group_ids = [var.sg_rds_id]
  publicly_accessible    = false

  db_name  = "societysphere"
  username = "app_admin"

  # Native Secrets Manager integration for master credentials (zero plaintext secrets)
  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.kms_key_arn

  iam_database_authentication_enabled = true
  auto_minor_version_upgrade          = true
  allow_major_version_upgrade         = false

  backup_retention_period   = var.backup_retention_period
  backup_window             = "19:00-20:00" # 00:30-01:30 IST
  maintenance_window        = "sun:20:30-sun:21:30"
  copy_tags_to_snapshot     = true
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = "societysphere-${var.environment}-postgres-final-snapshot"

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  performance_insights_enabled    = true
  performance_insights_kms_key_id = var.kms_key_arn

  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  tags = {
    Name        = "societysphere-${var.environment}-postgres"
    Environment = var.environment
  }
}

# IAM Role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0
  name  = "societysphere-${var.environment}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-rds-monitoring-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count      = var.monitoring_interval > 0 ? 1 : 0
  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ==============================================================================
# RDS PROXY: TRANSACTION-LEVEL CONNECTION POOLING (PgBouncer-Compatible)
# ==============================================================================

# IAM Role for RDS Proxy to access database master credentials in Secrets Manager
resource "aws_iam_role" "db_proxy" {
  count = var.enable_db_proxy ? 1 : 0
  name  = "societysphere-${var.environment}-db-proxy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DbProxyAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-db-proxy-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "db_proxy" {
  count = var.enable_db_proxy ? 1 : 0
  name  = "societysphere-${var.environment}-db-proxy-policy"
  role  = aws_iam_role.db_proxy[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GetDatabaseSecret"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_db_instance.main.master_user_secret[0].secret_arn
        ]
      },
      {
        Sid    = "DecryptDatabaseSecretKms"
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = [
          var.kms_key_arn
        ]
      }
    ]
  })
}

# Amazon RDS Proxy for PostgreSQL
resource "aws_db_proxy" "main" {
  count                  = var.enable_db_proxy ? 1 : 0
  name                   = "societysphere-${var.environment}-db-proxy"
  debug_logging          = var.environment != "production"
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = true
  role_arn               = aws_iam_role.db_proxy[0].arn
  vpc_security_group_ids = [var.sg_rds_id]
  vpc_subnet_ids         = var.data_subnet_ids

  auth {
    auth_scheme = "SECRETS"
    description = "Secrets Manager authentication for RDS Proxy"
    iam_auth    = "DISABLED"
    secret_arn  = aws_db_instance.main.master_user_secret[0].secret_arn
  }

  tags = {
    Name        = "societysphere-${var.environment}-db-proxy"
    Environment = var.environment
  }
}

# RDS Proxy Default Target Group (Configured for transaction pooling behavior)
resource "aws_db_proxy_default_target_group" "main" {
  count         = var.enable_db_proxy ? 1 : 0
  db_proxy_name = aws_db_proxy.main[0].name

  connection_pool_config {
    connection_borrow_timeout    = 120
    max_connections_percent      = 90
    max_idle_connections_percent = 50
    session_pinning_filters      = ["EXCLUDE_VARIABLE_SETS"]
  }
}

# RDS Proxy Target Association
resource "aws_db_proxy_target" "main" {
  count                  = var.enable_db_proxy ? 1 : 0
  db_proxy_name          = aws_db_proxy.main[0].name
  target_group_name      = aws_db_proxy_default_target_group.main[0].name
  db_instance_identifier = aws_db_instance.main.id
}
