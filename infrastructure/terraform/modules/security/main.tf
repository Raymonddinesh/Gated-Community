data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# ==============================================================================
# AWS KMS CUSTOMER MANAGED KEY (CMK)
# ==============================================================================

resource "aws_kms_key" "primary" {
  description             = "SocietySphere ${var.environment} Customer Managed Key"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogsEncryption"
        Effect = "Allow"
        Principal = {
          Service = [
            "logs.${local.region}.amazonaws.com",
            "delivery.logs.amazonaws.com"
          ]
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-cmk"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "primary" {
  name          = "alias/societysphere-${var.environment}-cmk"
  target_key_id = aws_kms_key.primary.key_id
}

# ==============================================================================
# AWS SECRETS MANAGER (Containers - No hardcoded secrets)
# ==============================================================================

resource "aws_secretsmanager_secret" "database" {
  name                    = "societysphere/${var.environment}/database"
  description             = "Database credentials for SocietySphere ${var.environment}"
  kms_key_id              = aws_kms_key.primary.arn
  recovery_window_in_days = 0

  tags = {
    Name        = "societysphere-${var.environment}-db-secret"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "societysphere/${var.environment}/app"
  description             = "Application secrets (JWT, Razorpay) for SocietySphere ${var.environment}"
  kms_key_id              = aws_kms_key.primary.arn
  recovery_window_in_days = 0

  tags = {
    Name        = "societysphere-${var.environment}-app-secret"
    Environment = var.environment
  }
}

# ==============================================================================
# IAM ROLES: ECS TASK EXECUTION ROLE (Container Startup & Pull)
# ==============================================================================

resource "aws_iam_role" "ecs_execution" {
  name = "societysphere-${var.environment}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcsTaskExecutionAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-ecs-execution-role"
    Environment = var.environment
  }
}

# tfsec:ignore:aws-iam-no-policy-wildcards: ECR authorization token retrieval is an AWS-mandated wildcard action
resource "aws_iam_role_policy" "ecs_execution" {
  name = "societysphere-${var.environment}-ecs-execution-policy"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcrAuthAndPull"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/ecs/societysphere-${var.environment}-*:*"
      },
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.database.arn,
          aws_secretsmanager_secret.app.arn
        ]
      },
      {
        Sid    = "KmsDecryptForSecrets"
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.primary.arn
      }
    ]
  })
}

# ==============================================================================
# IAM ROLES: ECS TASK RUNTIME ROLE (Application Operations)
# ==============================================================================
# IAM ROLES: ECS TASK RUNTIME ROLES (Least-Privilege Application Operations)
# ==============================================================================

# Generic Application Task Role (Backwards Compatibility)
resource "aws_iam_role" "ecs_task" {
  name = "societysphere-${var.environment}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcsTaskAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-ecs-task-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "societysphere-${var.environment}-ecs-task-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3DocumentsAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = var.documents_bucket_arn != "" ? [
          var.documents_bucket_arn,
          "${var.documents_bucket_arn}/*"
        ] : ["arn:aws:s3:::societysphere-${var.environment}-documents-*"]
      },
      {
        Sid    = "KmsEnvelopeCrypto"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.primary.arn
      },
      {
        Sid    = "SesEmailDispatch"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "arn:aws:ses:${local.region}:${local.account_id}:identity/${var.ses_sender_email}"
      }
    ]
  })
}

# 1. Frontend Web Task Role (Minimal Least-Privilege: No direct DB, S3, or secrets access)
resource "aws_iam_role" "ecs_task_web" {
  name = "societysphere-${var.environment}-ecs-task-web-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcsTaskWebAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-ecs-task-web-role"
    Environment = var.environment
    Tier        = "Frontend"
  }
}

# 2. Backend API Task Role (S3 documents, KMS crypto, SES email dispatch)
resource "aws_iam_role" "ecs_task_api" {
  name = "societysphere-${var.environment}-ecs-task-api-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcsTaskApiAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-ecs-task-api-role"
    Environment = var.environment
    Tier        = "BackendAPI"
  }
}

resource "aws_iam_role_policy" "ecs_task_api" {
  name = "societysphere-${var.environment}-ecs-task-api-policy"
  role = aws_iam_role.ecs_task_api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3DocumentsAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = var.documents_bucket_arn != "" ? [
          var.documents_bucket_arn,
          "${var.documents_bucket_arn}/*"
        ] : ["arn:aws:s3:::societysphere-${var.environment}-documents-*"]
      },
      {
        Sid    = "KmsEnvelopeCrypto"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.primary.arn
      },
      {
        Sid    = "SesEmailDispatch"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "arn:aws:ses:${local.region}:${local.account_id}:identity/${var.ses_sender_email}"
      }
    ]
  })
}

# 3. Background Workers Task Role (S3 documents for invoice PDFs/tax snapshots, KMS, SES)
resource "aws_iam_role" "ecs_task_workers" {
  name = "societysphere-${var.environment}-ecs-task-workers-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcsTaskWorkersAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-ecs-task-workers-role"
    Environment = var.environment
    Tier        = "Workers"
  }
}

resource "aws_iam_role_policy" "ecs_task_workers" {
  name = "societysphere-${var.environment}-ecs-task-workers-policy"
  role = aws_iam_role.ecs_task_workers.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3DocumentsAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = var.documents_bucket_arn != "" ? [
          var.documents_bucket_arn,
          "${var.documents_bucket_arn}/*"
        ] : ["arn:aws:s3:::societysphere-${var.environment}-documents-*"]
      },
      {
        Sid    = "KmsEnvelopeCrypto"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.primary.arn
      },
      {
        Sid    = "SesEmailDispatch"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "arn:aws:ses:${local.region}:${local.account_id}:identity/${var.ses_sender_email}"
      }
    ]
  })
}
