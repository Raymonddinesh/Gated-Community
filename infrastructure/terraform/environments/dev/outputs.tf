output "vpc_id" {
  description = "Development VPC ID"
  value       = module.networking.vpc_id
}

output "documents_bucket" {
  description = "Development S3 documents bucket"
  value       = module.storage.bucket_id
}

output "db_endpoint" {
  description = "Development PostgreSQL endpoint"
  value       = module.rds.db_endpoint
}

output "redis_endpoint" {
  description = "Development Redis endpoint"
  value       = module.redis.primary_endpoint_address
}

output "rabbitmq_endpoints" {
  description = "Development RabbitMQ endpoint"
  value       = module.rabbitmq.amqp_ssl_endpoints
}

output "vpc_flow_logs_id" {
  description = "Development VPC Flow Log ID"
  value       = module.networking.vpc_flow_logs_id
}

output "alb_dns_name" {
  description = "Development Application Load Balancer DNS name"
  value       = module.ecs.alb_dns_name
}

output "ecr_web_repository_url" {
  description = "Development Frontend Web ECR Repository URL"
  value       = module.ecs.ecr_web_repository_url
}

output "ecr_api_repository_url" {
  description = "Development Backend API ECR Repository URL"
  value       = module.ecs.ecr_api_repository_url
}

output "db_proxy_endpoint" {
  description = "Development RDS Proxy endpoint for connection pooling"
  value       = module.rds.db_proxy_endpoint
}

