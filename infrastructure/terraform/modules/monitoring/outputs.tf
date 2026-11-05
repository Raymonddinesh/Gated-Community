output "web_log_group_name" {
  description = "Name of the Web Frontend CloudWatch log group"
  value       = aws_cloudwatch_log_group.ecs_web.name
}

output "api_log_group_name" {
  description = "Name of the Backend API CloudWatch log group"
  value       = aws_cloudwatch_log_group.ecs_api.name
}

output "workers_log_group_name" {
  description = "Name of the Background Workers CloudWatch log group"
  value       = aws_cloudwatch_log_group.ecs_workers.name
}

output "api_cpu_alarm_arn" {
  description = "ARN of the API CPU utilization alarm"
  value       = aws_cloudwatch_metric_alarm.api_cpu_high.arn
}

output "rds_cpu_alarm_arn" {
  description = "ARN of the RDS CPU utilization alarm"
  value       = aws_cloudwatch_metric_alarm.rds_cpu_high.arn
}
