output "vpc_id" {
  description = "Staging VPC ID"
  value       = module.networking.vpc_id
}

output "documents_bucket" {
  description = "Staging S3 documents bucket"
  value       = module.storage.bucket_id
}

output "db_endpoint" {
  description = "Staging PostgreSQL endpoint"
  value       = module.rds.db_endpoint
}

output "redis_endpoint" {
  description = "Staging Redis endpoint"
  value       = module.redis.primary_endpoint_address
}

output "rabbitmq_endpoints" {
  description = "Staging RabbitMQ endpoint"
  value       = module.rabbitmq.amqp_ssl_endpoints
}

output "interface_endpoint_ids" {
  description = "Staging VPC Interface Endpoint IDs"
  value       = module.networking.interface_endpoint_ids
}

output "vpc_flow_logs_id" {
  description = "Staging VPC Flow Log ID"
  value       = module.networking.vpc_flow_logs_id
}

output "alb_dns_name" {
  description = "Staging Application Load Balancer DNS name"
  value       = module.ecs.alb_dns_name
}

output "ecr_web_repository_url" {
  description = "Staging Frontend Web ECR Repository URL"
  value       = module.ecs.ecr_web_repository_url
}

output "ecr_api_repository_url" {
  description = "Staging Backend API ECR Repository URL"
  value       = module.ecs.ecr_api_repository_url
}

output "db_proxy_endpoint" {
  description = "Staging RDS Proxy endpoint for connection pooling"
  value       = module.rds.db_proxy_endpoint
}
