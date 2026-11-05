output "vpc_id" {
  description = "QA VPC ID"
  value       = module.networking.vpc_id
}

output "documents_bucket" {
  description = "QA S3 documents bucket"
  value       = module.storage.bucket_id
}

output "db_endpoint" {
  description = "QA PostgreSQL endpoint"
  value       = module.rds.db_endpoint
}

output "redis_endpoint" {
  description = "QA Redis endpoint"
  value       = module.redis.primary_endpoint_address
}

output "rabbitmq_endpoints" {
  description = "QA RabbitMQ endpoint"
  value       = module.rabbitmq.amqp_ssl_endpoints
}

output "vpc_flow_logs_id" {
  description = "QA VPC Flow Log ID"
  value       = module.networking.vpc_flow_logs_id
}

output "alb_dns_name" {
  description = "QA Application Load Balancer DNS name"
  value       = module.ecs.alb_dns_name
}

output "ecr_web_repository_url" {
  description = "QA Frontend Web ECR Repository URL"
  value       = module.ecs.ecr_web_repository_url
}

output "ecr_api_repository_url" {
  description = "QA Backend API ECR Repository URL"
  value       = module.ecs.ecr_api_repository_url
}

output "db_proxy_endpoint" {
  description = "QA RDS Proxy endpoint for connection pooling"
  value       = module.rds.db_proxy_endpoint
}

