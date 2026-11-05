# Amazon VPC Definition
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "societysphere-${var.environment}-vpc"
    Environment = var.environment
  }
}

# Public Subnets (ALB & NAT Gateways)
resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name        = "societysphere-${var.environment}-public-${var.availability_zones[count.index]}"
    Environment = var.environment
    Tier        = "Public"
  }
}

# Private Application Subnets (ECS Fargate & PgBouncer)
resource "aws_subnet" "app" {
  count                   = length(var.app_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.app_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name        = "societysphere-${var.environment}-app-${var.availability_zones[count.index]}"
    Environment = var.environment
    Tier        = "Application"
  }
}

# Isolated Data Subnets (RDS, ElastiCache, Amazon MQ)
resource "aws_subnet" "data" {
  count                   = length(var.data_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.data_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name        = "societysphere-${var.environment}-data-${var.availability_zones[count.index]}"
    Environment = var.environment
    Tier        = "Database"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-igw"
    Environment = var.environment
  }
}

# Elastic IPs for NAT Gateways
resource "aws_eip" "nat" {
  count  = var.single_nat_gateway ? 1 : length(var.availability_zones)
  domain = "vpc"

  tags = {
    Name        = "societysphere-${var.environment}-nat-eip-${count.index + 1}"
    Environment = var.environment
  }
}

# NAT Gateways
resource "aws_nat_gateway" "nat" {
  count         = var.single_nat_gateway ? 1 : length(var.availability_zones)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name        = "societysphere-${var.environment}-nat-${count.index + 1}"
    Environment = var.environment
  }

  depends_on = [aws_internet_gateway.igw]
}

# Public Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name        = "societysphere-${var.environment}-public-rt"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private Application Route Tables
resource "aws_route_table" "app" {
  count  = length(var.availability_zones)
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.nat[0].id : aws_nat_gateway.nat[count.index].id
  }

  tags = {
    Name        = "societysphere-${var.environment}-app-rt-${var.availability_zones[count.index]}"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "app" {
  count          = length(aws_subnet.app)
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.app[count.index].id
}

# Isolated Data Route Table (No Internet or NAT egress)
resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-data-rt"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "data" {
  count          = length(aws_subnet.data)
  subnet_id      = aws_subnet.data[count.index].id
  route_table_id = aws_route_table.data.id
}

# Amazon S3 Gateway Endpoint (High-throughput, free internal routing)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([aws_route_table.public.id, aws_route_table.data.id], aws_route_table.app[*].id)

  tags = {
    Name        = "societysphere-${var.environment}-s3-endpoint"
    Environment = var.environment
  }
}

# AWS PrivateLink Interface Endpoints (ECR, CloudWatch Logs, Secrets Manager)
resource "aws_vpc_endpoint" "interface" {
  for_each = var.enable_interface_endpoints ? toset(var.interface_endpoints_services) : []

  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.app[*].id
  security_group_ids  = [aws_security_group.endpoints[0].id]
  private_dns_enabled = true

  tags = {
    Name        = "societysphere-${var.environment}-vpce-${replace(each.value, ".", "-")}"
    Environment = var.environment
  }
}

data "aws_region" "current" {}

# ==============================================================================
# DEFAULT SECURITY GROUP RESTRICTION (CIS AWS Foundations Benchmark)
# ==============================================================================

# Sealing the default security group prevents unauthorized default network usage
resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id

  # Zero ingress and zero egress rules

  tags = {
    Name        = "societysphere-${var.environment}-default-sg-restricted"
    Environment = var.environment
    Compliance  = "CIS-Benchmark-5.4"
  }
}

# ==============================================================================
# SECURITY GROUPS
# ==============================================================================

# VPC Interface Endpoints Security Group
resource "aws_security_group" "endpoints" {
  count       = var.enable_interface_endpoints ? 1 : 0
  name        = "societysphere-${var.environment}-sg-endpoints"
  description = "Security group for AWS PrivateLink VPC Interface Endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS inbound from application subnets to VPC endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.app_subnet_cidrs
  }

  tags = {
    Name        = "societysphere-${var.environment}-sg-endpoints"
    Environment = var.environment
  }
}

# ALB Security Group
resource "aws_security_group" "alb" {
  name        = "societysphere-${var.environment}-sg-alb"
  description = "Security group for SocietySphere Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP ingress redirection to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tfsec:ignore:aws-vpc-no-public-ingress-sgr
  }

  ingress {
    description = "HTTPS ingress from public internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tfsec:ignore:aws-vpc-no-public-ingress-sgr
  }

  tags = {
    Name        = "societysphere-${var.environment}-sg-alb"
    Environment = var.environment
  }
}

# Web Frontend Security Group (Next.js 14)
resource "aws_security_group" "web" {
  name        = "societysphere-${var.environment}-sg-web"
  description = "Security group for Next.js 14 Web Frontend ECS tasks"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS egress to VPC endpoints and external services"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tfsec:ignore:aws-vpc-no-public-egress-sgr
  }

  tags = {
    Name        = "societysphere-${var.environment}-sg-web"
    Environment = var.environment
  }
}

# Backend API Security Group (FastAPI)
resource "aws_security_group" "api" {
  name        = "societysphere-${var.environment}-sg-api"
  description = "Security group for FastAPI Backend API ECS tasks"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS egress to AWS services and payment webhooks"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tfsec:ignore:aws-vpc-no-public-egress-sgr
  }

  tags = {
    Name        = "societysphere-${var.environment}-sg-api"
    Environment = var.environment
  }
}

# Background Workers Security Group
resource "aws_security_group" "workers" {
  name        = "societysphere-${var.environment}-sg-workers"
  description = "Security group for Background Worker ECS tasks"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS egress to external notification and payment APIs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tfsec:ignore:aws-vpc-no-public-egress-sgr
  }

  tags = {
    Name        = "societysphere-${var.environment}-sg-workers"
    Environment = var.environment
  }
}

# PgBouncer Connection Pooler Security Group
resource "aws_security_group" "pgbouncer" {
  name        = "societysphere-${var.environment}-sg-pgbouncer"
  description = "Security group for PgBouncer connection pooler"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-sg-pgbouncer"
    Environment = var.environment
  }
}

# RDS PostgreSQL Security Group
resource "aws_security_group" "rds" {
  name        = "societysphere-${var.environment}-sg-rds"
  description = "Security group for RDS PostgreSQL database"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-sg-rds"
    Environment = var.environment
  }
}

# ElastiCache Redis Security Group
resource "aws_security_group" "redis" {
  name        = "societysphere-${var.environment}-sg-redis"
  description = "Security group for ElastiCache Redis cluster"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-sg-redis"
    Environment = var.environment
  }
}

# Amazon MQ RabbitMQ Security Group
resource "aws_security_group" "rabbitmq" {
  name        = "societysphere-${var.environment}-sg-rabbitmq"
  description = "Security group for Amazon MQ RabbitMQ broker"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-sg-rabbitmq"
    Environment = var.environment
  }
}

# ==============================================================================
# INTER-SERVICE SECURITY GROUP RULES (Acyclic graph)
# ==============================================================================

# ALB to Web / API
resource "aws_security_group_rule" "alb_egress_to_web" {
  type                     = "egress"
  description              = "Forward HTTP to Next.js Web Frontend"
  from_port                = 3000
  to_port                  = 3000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.alb.id
  source_security_group_id = aws_security_group.web.id
}

resource "aws_security_group_rule" "web_ingress_from_alb" {
  type                     = "ingress"
  description              = "Allow port 3000 from ALB"
  from_port                = 3000
  to_port                  = 3000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.web.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "alb_egress_to_api" {
  type                     = "egress"
  description              = "Forward HTTP to FastAPI Backend"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.alb.id
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "api_ingress_from_alb" {
  type                     = "ingress"
  description              = "HTTP ingress from ALB"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "web_egress_to_api" {
  type                     = "egress"
  description              = "Internal API calls to Backend API"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.web.id
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "api_ingress_from_web" {
  type                     = "ingress"
  description              = "HTTP ingress from Web Frontend for SSR"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.web.id
}

# API / Workers to PgBouncer
resource "aws_security_group_rule" "api_egress_to_pgbouncer" {
  type                     = "egress"
  description              = "PostgreSQL traffic to PgBouncer connection pooler"
  from_port                = 6432
  to_port                  = 6432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.pgbouncer.id
}

resource "aws_security_group_rule" "workers_egress_to_pgbouncer" {
  type                     = "egress"
  description              = "PostgreSQL traffic to PgBouncer connection pooler"
  from_port                = 6432
  to_port                  = 6432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.workers.id
  source_security_group_id = aws_security_group.pgbouncer.id
}

resource "aws_security_group_rule" "pgbouncer_ingress_from_api" {
  type                     = "ingress"
  description              = "PostgreSQL pooling ingress from FastAPI"
  from_port                = 6432
  to_port                  = 6432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.pgbouncer.id
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "pgbouncer_ingress_from_workers" {
  type                     = "ingress"
  description              = "PostgreSQL pooling ingress from Workers"
  from_port                = 6432
  to_port                  = 6432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.pgbouncer.id
  source_security_group_id = aws_security_group.workers.id
}

# PgBouncer to RDS
resource "aws_security_group_rule" "pgbouncer_egress_to_rds" {
  type                     = "egress"
  description              = "Direct PostgreSQL egress to RDS primary"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.pgbouncer.id
  source_security_group_id = aws_security_group.rds.id
}

resource "aws_security_group_rule" "rds_ingress_from_pgbouncer" {
  type                     = "ingress"
  description              = "PostgreSQL ingress from PgBouncer pooler"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.pgbouncer.id
}

# API / Workers to Redis
resource "aws_security_group_rule" "api_egress_to_redis" {
  type                     = "egress"
  description              = "Redis caching traffic"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.redis.id
}

resource "aws_security_group_rule" "workers_egress_to_redis" {
  type                     = "egress"
  description              = "Redis distributed lease traffic"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.workers.id
  source_security_group_id = aws_security_group.redis.id
}

resource "aws_security_group_rule" "redis_ingress_from_api" {
  type                     = "ingress"
  description              = "Redis ingress from FastAPI"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.redis.id
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "redis_ingress_from_workers" {
  type                     = "ingress"
  description              = "Redis ingress from Workers"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.redis.id
  source_security_group_id = aws_security_group.workers.id
}

# API / Workers to RabbitMQ
resource "aws_security_group_rule" "api_egress_to_rabbitmq" {
  type                     = "egress"
  description              = "AMQPS messaging traffic to RabbitMQ"
  from_port                = 5671
  to_port                  = 5671
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.rabbitmq.id
}

resource "aws_security_group_rule" "workers_egress_to_rabbitmq" {
  type                     = "egress"
  description              = "AMQPS messaging traffic to RabbitMQ"
  from_port                = 5671
  to_port                  = 5671
  protocol                 = "tcp"
  security_group_id        = aws_security_group.workers.id
  source_security_group_id = aws_security_group.rabbitmq.id
}

resource "aws_security_group_rule" "rabbitmq_ingress_from_api" {
  type                     = "ingress"
  description              = "AMQPS ingress from FastAPI"
  from_port                = 5671
  to_port                  = 5671
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rabbitmq.id
  source_security_group_id = aws_security_group.api.id
}

resource "aws_security_group_rule" "rabbitmq_ingress_from_workers" {
  type                     = "ingress"
  description              = "AMQPS ingress from Workers"
  from_port                = 5671
  to_port                  = 5671
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rabbitmq.id
  source_security_group_id = aws_security_group.workers.id
}

# ==============================================================================
# VPC FLOW LOGS (ISO 27001 / DPDP 2023 Network Auditing)
# ==============================================================================

resource "aws_flow_log" "main" {
  count           = var.enable_vpc_flow_logs ? 1 : 0
  iam_role_arn    = aws_iam_role.flow_log[0].arn
  log_destination = aws_cloudwatch_log_group.flow_log[0].arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.main.id

  tags = {
    Name        = "societysphere-${var.environment}-vpc-flow-logs"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "flow_log" {
  #checkov:skip=CKV_AWS_338: Flow log retention is environment configurable (dev=7d, qa=14d, staging=30d, prod=365d)
  count             = var.enable_vpc_flow_logs ? 1 : 0
  name              = "/aws/vpc/societysphere-${var.environment}-flow-logs"
  retention_in_days = var.flow_logs_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name        = "societysphere-${var.environment}-flow-logs"
    Environment = var.environment
  }
}

resource "aws_iam_role" "flow_log" {
  count = var.enable_vpc_flow_logs ? 1 : 0
  name  = "societysphere-${var.environment}-vpc-flow-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VpcFlowLogAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "societysphere-${var.environment}-vpc-flow-logs-role"
    Environment = var.environment
  }
}

# tfsec:ignore:aws-iam-no-policy-wildcards: VPC flow log service requires wildcard stream access within the scoped flow log group
resource "aws_iam_role_policy" "flow_log" {
  count = var.enable_vpc_flow_logs ? 1 : 0
  name  = "societysphere-${var.environment}-vpc-flow-logs-policy"
  role  = aws_iam_role.flow_log[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VpcFlowLogDelivery"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.flow_log[0].arn}:*"
      }
    ]
  })
}
