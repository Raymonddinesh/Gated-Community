output "cluster_id" {
  description = "The ID of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "cluster_name" {
  description = "The name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "The ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "web_service_name" {
  description = "Name of the Web Frontend ECS service"
  value       = aws_ecs_service.web.name
}

output "api_service_name" {
  description = "Name of the Backend API ECS service"
  value       = aws_ecs_service.api.name
}

output "workers_service_name" {
  description = "Name of the Background Workers ECS service"
  value       = aws_ecs_service.workers.name
}

output "web_task_definition_arn" {
  description = "ARN of the Web Frontend task definition"
  value       = aws_ecs_task_definition.web.arn
}

output "api_task_definition_arn" {
  description = "ARN of the Backend API task definition"
  value       = aws_ecs_task_definition.api.arn
}

output "workers_task_definition_arn" {
  description = "ARN of the Background Workers task definition"
  value       = aws_ecs_task_definition.workers.arn
}

output "ecr_web_repository_url" {
  description = "URL of the Frontend Web ECR repository"
  value       = aws_ecr_repository.web.repository_url
}

output "ecr_api_repository_url" {
  description = "URL of the Backend API ECR repository"
  value       = aws_ecr_repository.api.repository_url
}

output "alb_id" {
  description = "ID of the Application Load Balancer"
  value       = length(aws_lb.main) > 0 ? aws_lb.main[0].id : null
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = length(aws_lb.main) > 0 ? aws_lb.main[0].arn : null
}

output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = length(aws_lb.main) > 0 ? aws_lb.main[0].dns_name : null
}

output "tg_web_arn" {
  description = "ARN of the Web Frontend Target Group"
  value       = length(aws_lb_target_group.web) > 0 ? aws_lb_target_group.web[0].arn : null
}

output "tg_api_arn" {
  description = "ARN of the Backend API Target Group"
  value       = length(aws_lb_target_group.api) > 0 ? aws_lb_target_group.api[0].arn : null
}
