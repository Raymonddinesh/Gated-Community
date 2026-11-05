output "state_bucket_name" {
  description = "Name of the provisioned S3 bucket for Terraform remote state"
  value       = aws_s3_bucket.state_bucket.id
}

output "state_bucket_arn" {
  description = "ARN of the provisioned S3 bucket for Terraform remote state"
  value       = aws_s3_bucket.state_bucket.arn
}

output "kms_key_arn" {
  description = "ARN of the KMS key used for remote state encryption"
  value       = aws_kms_key.state_key.arn
}

output "kms_key_alias" {
  description = "Alias of the KMS key used for remote state encryption"
  value       = aws_kms_alias.state_key_alias.name
}

output "dynamodb_lock_table_name" {
  description = "Name of the DynamoDB lock table (if enabled)"
  value       = var.enable_dynamodb_lock ? aws_dynamodb_table.state_locks[0].name : "N/A (S3 native lockfile configured)"
}
