output "db_instance_id" {
  description = "The RDS DB instance identifier"
  value       = aws_db_instance.main.id
}

output "db_instance_arn" {
  description = "The ARN of the RDS instance"
  value       = aws_db_instance.main.arn
}

output "db_endpoint" {
  description = "Connection endpoint of the RDS instance"
  value       = aws_db_instance.main.endpoint
}

output "db_address" {
  description = "Hostname/address of the RDS instance"
  value       = aws_db_instance.main.address
}

output "db_port" {
  description = "Port of the database"
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "Name of the default database"
  value       = aws_db_instance.main.db_name
}

output "master_user_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret storing master credentials"
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "db_proxy_endpoint" {
  description = "Connection endpoint of the RDS Proxy (PgBouncer-compatible connection pool)"
  value       = var.enable_db_proxy ? aws_db_proxy.main[0].endpoint : aws_db_instance.main.endpoint
}

output "db_proxy_arn" {
  description = "The ARN of the RDS Proxy"
  value       = var.enable_db_proxy ? aws_db_proxy.main[0].arn : null
}

output "db_proxy_id" {
  description = "The ID of the RDS Proxy"
  value       = var.enable_db_proxy ? aws_db_proxy.main[0].id : null
}
