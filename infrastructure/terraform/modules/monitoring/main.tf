# CloudWatch Log Groups with KMS Encryption
resource "aws_cloudwatch_log_group" "ecs_web" {
  name              = "/ecs/societysphere-${var.environment}-web"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name        = "societysphere-${var.environment}-ecs-web-logs"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "ecs_api" {
  name              = "/ecs/societysphere-${var.environment}-api"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name        = "societysphere-${var.environment}-ecs-api-logs"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "ecs_workers" {
  name              = "/ecs/societysphere-${var.environment}-workers"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name        = "societysphere-${var.environment}-ecs-workers-logs"
    Environment = var.environment
  }
}

# ==============================================================================
# CLOUDWATCH METRIC ALARMS (SLO & Operational Reliability)
# ==============================================================================

# High API CPU Utilization Alarm
resource "aws_cloudwatch_metric_alarm" "api_cpu_high" {
  alarm_name          = "societysphere-${var.environment}-api-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 75
  alarm_description   = "FastAPI container CPU utilization exceeded 75% for 2 consecutive minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "societysphere-${var.environment}-cluster"
    ServiceName = "societysphere-${var.environment}-api"
  }

  alarm_actions = var.alert_sns_topic_arn != "" ? [var.alert_sns_topic_arn] : []

  tags = {
    Name        = "societysphere-${var.environment}-api-cpu-alarm"
    Environment = var.environment
  }
}

# High API Memory Utilization Alarm
resource "aws_cloudwatch_metric_alarm" "api_memory_high" {
  alarm_name          = "societysphere-${var.environment}-api-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "FastAPI container Memory utilization exceeded 80% for 2 consecutive minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "societysphere-${var.environment}-cluster"
    ServiceName = "societysphere-${var.environment}-api"
  }

  alarm_actions = var.alert_sns_topic_arn != "" ? [var.alert_sns_topic_arn] : []

  tags = {
    Name        = "societysphere-${var.environment}-api-memory-alarm"
    Environment = var.environment
  }
}

# High Database CPU Utilization Alarm
resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "societysphere-${var.environment}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS PostgreSQL CPU utilization exceeded 80% for 3 consecutive minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = "societysphere-${var.environment}-postgres"
  }

  alarm_actions = var.alert_sns_topic_arn != "" ? [var.alert_sns_topic_arn] : []

  tags = {
    Name        = "societysphere-${var.environment}-rds-cpu-alarm"
    Environment = var.environment
  }
}

# Low Database Storage Space Alarm (< 10GB)
resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  alarm_name          = "societysphere-${var.environment}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 10737418240 # 10 GB in bytes
  alarm_description   = "RDS PostgreSQL free storage space is below 10 GB"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = "societysphere-${var.environment}-postgres"
  }

  alarm_actions = var.alert_sns_topic_arn != "" ? [var.alert_sns_topic_arn] : []

  tags = {
    Name        = "societysphere-${var.environment}-rds-storage-alarm"
    Environment = var.environment
  }
}
