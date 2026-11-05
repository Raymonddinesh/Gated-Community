terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote State configuration for Development
  # In local/CI validation before bucket provisioning, initialize with: tofu init -backend=false
  backend "s3" {
    bucket       = "societysphere-terraform-state-dev"
    key          = "environments/dev/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "SocietySphere"
      Environment = "dev"
      ManagedBy   = "Terraform"
      Compliance  = "ISO27001-DPDP2023"
      Phase       = "22B"
    }
  }
}
