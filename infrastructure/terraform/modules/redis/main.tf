# ElastiCache Subnet Group (Isolated Data Tier)
resource "aws_elasticache_subnet_group" "main" {
  name        = "societysphere-${var.environment}-redis-subnet-group"
  description = "Isolated data subnets for SocietySphere ElastiCache Redis"
  subnet_ids  = var.data_subnet_ids

  tags = {
    Name        = "societysphere-${var.environment}-redis-subnet-group"
    Environment = var.environment
  }
}

# Redis 7.x Parameter Group
resource "aws_elasticache_parameter_group" "main" {
  name        = "societysphere-${var.environment}-redis7-params"
  family      = "redis7"
  description = "Redis 7.x parameter group for SocietySphere caching and distributed leasing"

  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  tags = {
    Name        = "societysphere-${var.environment}-redis7-params"
    Environment = var.environment
  }
}

# ElastiCache Redis Replication Group
resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "societysphere-${var.environment}-redis"
  description          = "SocietySphere ${var.environment} Redis cluster for session cache and distributed locks"
  node_type            = var.node_type
  num_cache_clusters   = var.multi_az ? var.num_cache_clusters : 1
  port                 = 6379

  engine               = "redis"
  engine_version       = "7.1"
  parameter_group_name = aws_elasticache_parameter_group.main.name
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [var.sg_redis_id]

  automatic_failover_enabled = var.multi_az
  multi_az_enabled           = var.multi_az

  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  kms_key_id                 = var.kms_key_arn
  auth_token                 = var.auth_token

  auto_minor_version_upgrade = true
  snapshot_retention_limit   = var.environment == "production" ? 7 : 1
  snapshot_window            = "21:00-22:00"

  tags = {
    Name        = "societysphere-${var.environment}-redis"
    Environment = var.environment
  }
}
