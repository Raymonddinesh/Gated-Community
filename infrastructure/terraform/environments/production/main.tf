# ==============================================================================
# ENVIRONMENT: PRODUCTION (Option B High-Availability Baseline)
# ==============================================================================
# Strict Production Safety Gate:
# Deployment to production is disabled by default.
# Executing 'tofu apply' or 'terraform apply' without explicitly setting
# var.production_apply_authorized = true will fail at the plan/apply stage.
# ==============================================================================

resource "terraform_data" "production_safety_gate" {
  lifecycle {
    precondition {
      condition     = var.production_apply_authorized == true
      error_message = "CRITICAL SAFETY GATE: Production deployment is locked by default. You must explicitly set 'production_apply_authorized = true' (via -var or production.tfvars) after formal Phase 22B architect sign-off."
    }
  }
}

module "security" {
  source = "../../modules/security"

  environment          = var.environment
  documents_bucket_arn = module.storage.bucket_arn
  ses_sender_email     = "notifications@societysphere.com"
}

module "storage" {
  source = "../../modules/storage"

  environment                = var.environment
  kms_key_arn                = module.security.kms_key_arn
  enable_object_lock         = true
  object_lock_mode           = "COMPLIANCE"
  object_lock_retention_days = 2190 # 6 years for Indian GST invoice compliance
}

module "monitoring" {
  source = "../../modules/monitoring"

  environment        = var.environment
  kms_key_arn        = module.security.kms_key_arn
  log_retention_days = 365 # 1 year for ISO27001/DPDP compliance
}

module "networking" {
  source = "../../modules/networking"

  environment                = var.environment
  vpc_cidr                   = var.vpc_cidr
  availability_zones         = var.availability_zones
  public_subnet_cidrs        = var.public_subnet_cidrs
  app_subnet_cidrs           = var.app_subnet_cidrs
  data_subnet_cidrs          = var.data_subnet_cidrs
  single_nat_gateway         = false # 3 Multi-AZ NAT Gateways for HA
  enable_vpc_flow_logs       = true
  kms_key_arn                = module.security.kms_key_arn
  flow_logs_retention_days   = 365
  enable_interface_endpoints = true
}

module "ecs" {
  source = "../../modules/ecs"

  environment           = var.environment
  vpc_id                = module.networking.vpc_id
  public_subnet_ids     = module.networking.public_subnet_ids
  app_subnet_ids        = module.networking.app_subnet_ids
  sg_alb_id             = module.networking.sg_alb_id
  sg_web_id             = module.networking.sg_web_id
  sg_api_id             = module.networking.sg_api_id
  sg_workers_id         = module.networking.sg_workers_id
  execution_role_arn    = module.security.ecs_execution_role_arn
  task_role_arn         = module.security.ecs_task_role_arn
  task_role_web_arn     = module.security.ecs_task_web_role_arn
  task_role_api_arn     = module.security.ecs_task_api_role_arn
  task_role_workers_arn = module.security.ecs_task_workers_role_arn
  db_secret_arn         = module.security.db_secret_arn
  app_secret_arn        = module.security.app_secret_arn
  kms_key_arn           = module.security.kms_key_arn

  web_desired_count     = 3
  api_desired_count     = 3
  workers_desired_count = 3
  web_min_capacity      = 2
  web_max_capacity      = 10
  api_min_capacity      = 2
  api_max_capacity      = 20
  workers_min_capacity  = 2
  workers_max_capacity  = 10

  enable_deletion_protection = true
  enable_docs_routing        = false
}

module "rds" {
  source = "../../modules/rds"

  environment             = var.environment
  data_subnet_ids         = module.networking.data_subnet_ids
  sg_rds_id               = module.networking.sg_rds_id
  kms_key_arn             = module.security.kms_key_arn
  instance_class          = var.rds_instance_class
  allocated_storage       = 100
  max_allocated_storage   = 500
  multi_az                = true
  backup_retention_period = 35
  deletion_protection     = true
}

module "redis" {
  source = "../../modules/redis"

  environment        = var.environment
  data_subnet_ids    = module.networking.data_subnet_ids
  sg_redis_id        = module.networking.sg_redis_id
  kms_key_arn        = module.security.kms_key_arn
  node_type          = var.redis_node_type
  multi_az           = true
  num_cache_clusters = 2
}

module "rabbitmq" {
  source = "../../modules/rabbitmq"

  environment        = var.environment
  data_subnet_ids    = module.networking.data_subnet_ids
  sg_rabbitmq_id     = module.networking.sg_rabbitmq_id
  kms_key_arn        = module.security.kms_key_arn
  host_instance_type = var.mq_instance_type
  deployment_mode    = "CLUSTER_MULTI_AZ"
}
