output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "The CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "app_subnet_ids" {
  description = "List of private application subnet IDs"
  value       = aws_subnet.app[*].id
}

output "data_subnet_ids" {
  description = "List of isolated data subnet IDs"
  value       = aws_subnet.data[*].id
}

output "sg_alb_id" {
  description = "Security group ID for Application Load Balancer"
  value       = aws_security_group.alb.id
}

output "sg_web_id" {
  description = "Security group ID for Web Frontend ECS tasks"
  value       = aws_security_group.web.id
}

output "sg_api_id" {
  description = "Security group ID for Backend API ECS tasks"
  value       = aws_security_group.api.id
}

output "sg_workers_id" {
  description = "Security group ID for Background Worker ECS tasks"
  value       = aws_security_group.workers.id
}

output "sg_pgbouncer_id" {
  description = "Security group ID for PgBouncer connection pooler"
  value       = aws_security_group.pgbouncer.id
}

output "sg_rds_id" {
  description = "Security group ID for RDS PostgreSQL"
  value       = aws_security_group.rds.id
}

output "sg_redis_id" {
  description = "Security group ID for ElastiCache Redis"
  value       = aws_security_group.redis.id
}

output "sg_rabbitmq_id" {
  description = "Security group ID for Amazon MQ RabbitMQ"
  value       = aws_security_group.rabbitmq.id
}

output "sg_endpoints_id" {
  description = "Security group ID for VPC Interface Endpoints"
  value       = var.enable_interface_endpoints ? aws_security_group.endpoints[0].id : null
}

output "interface_endpoint_ids" {
  description = "Map of VPC Interface Endpoint IDs"
  value       = { for k, v in aws_vpc_endpoint.interface : k => v.id }
}

output "vpc_flow_logs_id" {
  description = "ID of the VPC Flow Log"
  value       = var.enable_vpc_flow_logs ? aws_flow_log.main[0].id : null
}

output "vpc_flow_logs_log_group_arn" {
  description = "ARN of CloudWatch Log Group for VPC Flow Logs"
  value       = var.enable_vpc_flow_logs ? aws_cloudwatch_log_group.flow_log[0].arn : null
}
