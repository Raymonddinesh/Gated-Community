output "bucket_id" {
  description = "The ID/name of the documents S3 bucket"
  value       = aws_s3_bucket.documents.id
}

output "bucket_arn" {
  description = "The ARN of the documents S3 bucket"
  value       = aws_s3_bucket.documents.arn
}

output "bucket_domain_name" {
  description = "The bucket domain name"
  value       = aws_s3_bucket.documents.bucket_domain_name
}
