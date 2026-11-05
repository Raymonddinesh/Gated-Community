output "kms_key_arn" {
  description = "ARN of the Customer Managed Key"
  value       = aws_kms_key.primary.arn
}

output "kms_key_alias" {
  description = "Alias of the Customer Managed Key"
  value       = aws_kms_alias.primary.name
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution IAM role"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the generic ECS application task IAM role"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_task_web_role_arn" {
  description = "ARN of the frontend Web ECS task IAM role"
  value       = aws_iam_role.ecs_task_web.arn
}

output "ecs_task_api_role_arn" {
  description = "ARN of the backend API ECS task IAM role"
  value       = aws_iam_role.ecs_task_api.arn
}

output "ecs_task_workers_role_arn" {
  description = "ARN of the background Workers ECS task IAM role"
  value       = aws_iam_role.ecs_task_workers.arn
}

output "db_secret_arn" {
  description = "ARN of the database secret container in Secrets Manager"
  value       = aws_secretsmanager_secret.database.arn
}

output "app_secret_arn" {
  description = "ARN of the application secret container in Secrets Manager"
  value       = aws_secretsmanager_secret.app.arn
}
