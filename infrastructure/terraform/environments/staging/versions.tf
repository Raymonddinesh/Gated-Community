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

  backend "s3" {
    bucket       = "societysphere-terraform-state-staging"
    key          = "environments/staging/terraform.tfstate"
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
      Environment = "staging"
      ManagedBy   = "Terraform"
      Compliance  = "ISO27001-DPDP2023"
      Phase       = "22B"
    }
  }
}
