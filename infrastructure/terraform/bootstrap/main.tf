data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = var.aws_region
  bucket_name = "${var.bucket_prefix}-${local.account_id}-${local.region}"
}

# KMS Customer Managed Key for Remote State Encryption
resource "aws_kms_key" "state_key" {
  description             = "KMS Key for SocietySphere Terraform Remote State"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootPermissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      }
    ]
  })

  tags = {
    Name        = "societysphere-state-key"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "state_key_alias" {
  name          = var.kms_key_alias
  target_key_id = aws_kms_key.state_key.key_id
}

# S3 Bucket for Remote State
# tfsec:ignore:aws-s3-enable-bucket-logging: Access logs are forwarded to the centralized S3 audit bucket in the Security Account
resource "aws_s3_bucket" "state_bucket" {
  bucket        = local.bucket_name
  force_destroy = false

  tags = {
    Name        = local.bucket_name
    Environment = var.environment
    Purpose     = "TerraformRemoteState"
  }
}

resource "aws_s3_bucket_versioning" "state_versioning" {
  bucket = aws_s3_bucket.state_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state_encryption" {
  bucket = aws_s3_bucket.state_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.state_key.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state_pab" {
  bucket = aws_s3_bucket.state_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "state_policy" {
  bucket = aws_s3_bucket.state_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.state_bucket.arn,
          "${aws_s3_bucket.state_bucket.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "state_lifecycle" {
  bucket = aws_s3_bucket.state_bucket.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# Optional DynamoDB Table for Legacy Locking (if S3 native lockfile is not used)
resource "aws_dynamodb_table" "state_locks" {
  count        = var.enable_dynamodb_lock ? 1 : 0
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.state_key.arn
  }

  tags = {
    Name        = var.dynamodb_table_name
    Environment = var.environment
  }
}
