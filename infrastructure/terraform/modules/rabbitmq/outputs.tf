output "broker_id" {
  description = "The unique ID of the Amazon MQ broker"
  value       = aws_mq_broker.main.id
}

output "broker_arn" {
  description = "The Amazon Resource Name (ARN) of the broker"
  value       = aws_mq_broker.main.arn
}

output "amqp_ssl_endpoints" {
  description = "List of AMQP SSL endpoints for client connections (port 5671)"
  value       = aws_mq_broker.main.instances[*].endpoints[0]
}

output "credentials_secret_arn" {
  description = "ARN of the Secrets Manager secret storing broker credentials"
  value       = aws_secretsmanager_secret.mq_credentials.arn
}
