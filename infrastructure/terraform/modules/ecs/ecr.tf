# ==============================================================================
# AMAZON ECR: REPOSITORIES, LIFECYCLE & SECURITY POLICIES
# ==============================================================================

# Web Frontend ECR Repository
# tfsec:ignore:aws-ecr-enforce-immutable-repository: Tag mutability is environment-configurable (mutable in dev/qa, immutable in production)
# tfsec:ignore:aws-ecr-repository-customer-key: KMS CMK encryption is environment-configurable via var.kms_key_arn
resource "aws_ecr_repository" "web" {
  name                 = "societysphere-${var.environment}-web"
  image_tag_mutability = var.environment == "production" ? "IMMUTABLE" : "MUTABLE"

  #checkov:skip=CKV_AWS_51: Tag mutability is environment configurable (immutable in prod, mutable in dev/qa)

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }

  tags = {
    Name        = "societysphere-${var.environment}-web"
    Environment = var.environment
    Tier        = "Frontend"
  }
}

# Backend API & Workers ECR Repository
# tfsec:ignore:aws-ecr-enforce-immutable-repository: Tag mutability is environment-configurable (mutable in dev/qa, immutable in production)
# tfsec:ignore:aws-ecr-repository-customer-key: KMS CMK encryption is environment-configurable via var.kms_key_arn
resource "aws_ecr_repository" "api" {
  name                 = "societysphere-${var.environment}-api"
  image_tag_mutability = var.environment == "production" ? "IMMUTABLE" : "MUTABLE"

  #checkov:skip=CKV_AWS_51: Tag mutability is environment configurable (immutable in prod, mutable in dev/qa)

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }

  tags = {
    Name        = "societysphere-${var.environment}-api"
    Environment = var.environment
    Tier        = "Backend"
  }
}

# ECR Lifecycle Policy (Web)
resource "aws_ecr_lifecycle_policy" "web" {
  repository = aws_ecr_repository.web.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Retain active release images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "release", "prod", "sha-"]
          countType     = "imageCountMoreThan"
          countNumber   = var.environment == "production" ? 30 : 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ECR Lifecycle Policy (API & Workers)
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Retain active release images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "release", "prod", "sha-"]
          countType     = "imageCountMoreThan"
          countNumber   = var.environment == "production" ? 30 : 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
