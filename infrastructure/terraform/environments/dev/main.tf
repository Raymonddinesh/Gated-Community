# ==============================================================================
# ENVIRONMENT: DEVELOPMENT (Cost-Optimized / Option A Reference)
# ==============================================================================

module "security" {
  source = "../../modules/security"

  environment          = var.environment
  documents_bucket_arn = module.storage.bucket_arn
  ses_sender_email     = "dev-noreply@societysphere.com"
}

module "storage" {
  source = "../../modules/storage"

  environment        = var.environment
  kms_key_arn        = module.security.kms_key_arn
  enable_object_lock = false
}

module "monitoring" {
  source = "../../modules/monitoring"

  environment        = var.environment
  kms_key_arn        = module.security.kms_key_arn
  log_retention_days = 7
}

module "networking" {
  source = "../../modules/networking"

  environment              = var.environment
  vpc_cidr                 = var.vpc_cidr
  availability_zones       = var.availability_zones
  public_subnet_cidrs      = var.public_subnet_cidrs
  app_subnet_cidrs         = var.app_subnet_cidrs
  data_subnet_cidrs        = var.data_subnet_cidrs
  single_nat_gateway       = true
  enable_vpc_flow_logs     = true
  kms_key_arn              = module.security.kms_key_arn
  flow_logs_retention_days = 7
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

  web_desired_count     = 1
  api_desired_count     = 1
  workers_desired_count = 1
  web_min_capacity      = 1
  web_max_capacity      = 3
  api_min_capacity      = 1
  api_max_capacity      = 5
  workers_min_capacity  = 1
  workers_max_capacity  = 3

  enable_docs_routing = true
}

module "rds" {
  source = "../../modules/rds"

  environment             = var.environment
  data_subnet_ids         = module.networking.data_subnet_ids
  sg_rds_id               = module.networking.sg_rds_id
  kms_key_arn             = module.security.kms_key_arn
  instance_class          = var.rds_instance_class
  allocated_storage       = 30
  max_allocated_storage   = 100
  multi_az                = false
  backup_retention_period = 7
  deletion_protection     = true
}

module "redis" {
  source = "../../modules/redis"

  environment        = var.environment
  data_subnet_ids    = module.networking.data_subnet_ids
  sg_redis_id        = module.networking.sg_redis_id
  kms_key_arn        = module.security.kms_key_arn
  node_type          = var.redis_node_type
  multi_az           = false
  num_cache_clusters = 1
}

module "rabbitmq" {
  source = "../../modules/rabbitmq"

  environment        = var.environment
  data_subnet_ids    = module.networking.data_subnet_ids
  sg_rabbitmq_id     = module.networking.sg_rabbitmq_id
  kms_key_arn        = module.security.kms_key_arn
  host_instance_type = var.mq_instance_type
  deployment_mode    = "SINGLE_INSTANCE"
}
