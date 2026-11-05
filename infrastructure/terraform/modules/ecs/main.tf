data "aws_region" "current" {}

# ==============================================================================
# ECS CLUSTER & CAPACITY PROVIDERS
# ==============================================================================

resource "aws_ecs_cluster" "main" {
  name = "societysphere-${var.environment}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "societysphere-${var.environment}-cluster"
    Environment = var.environment
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ==============================================================================
# TASK DEFINITIONS
# ==============================================================================

# Web Frontend Task Definition (Next.js 14 Standalone)
resource "aws_ecs_task_definition" "web" {
  family                   = "societysphere-${var.environment}-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_web_arn != null ? var.task_role_web_arn : var.task_role_arn

  container_definitions = jsonencode([
    {
      name        = "web"
      image       = var.web_image
      essential   = true
      user        = "1001:1001"
      stopTimeout = 30

      portMappings = [
        {
          containerPort = 3000
          hostPort      = 3000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "NODE_ENV"
          value = "production"
        },
        {
          name  = "PORT"
          value = "3000"
        },
        {
          name  = "NEXT_TELEMETRY_DISABLED"
          value = "1"
        }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "wget -q --spider http://127.0.0.1:3000/ || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/societysphere-${var.environment}-web"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "web"
        }
      }
    }
  ])

  tags = {
    Name        = "societysphere-${var.environment}-web-task"
    Environment = var.environment
    Tier        = "Frontend"
  }
}

# Backend API Task Definition (FastAPI)
resource "aws_ecs_task_definition" "api" {
  family                   = "societysphere-${var.environment}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_api_arn != null ? var.task_role_api_arn : var.task_role_arn

  container_definitions = jsonencode([
    {
      name        = "api"
      image       = var.api_image
      essential   = true
      user        = "1001:1001"
      stopTimeout = 30
      command     = ["uvicorn", "apps.api.src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "APP_NAME"
          value = "SocietySphere"
        },
        {
          name  = "APP_ENV"
          value = var.environment
        },
        {
          name  = "PORT"
          value = "8000"
        },
        {
          name  = "API_PREFIX"
          value = "/api/v1"
        },
        {
          name  = "PYTHONUNBUFFERED"
          value = "1"
        }
      ]

      secrets = var.db_secret_arn != null && var.app_secret_arn != null ? [
        {
          name      = "DATABASE_CREDENTIALS"
          valueFrom = var.db_secret_arn
        },
        {
          name      = "APP_SECRETS"
          valueFrom = var.app_secret_arn
        }
      ] : []

      healthCheck = {
        command     = ["CMD", "curl", "-f", "http://127.0.0.1:8000/health/live"]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/societysphere-${var.environment}-api"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])

  tags = {
    Name        = "societysphere-${var.environment}-api-task"
    Environment = var.environment
    Tier        = "BackendAPI"
  }
}

# Background Workers Task Definition (Unified asyncio TaskGroup Supervisor)
resource "aws_ecs_task_definition" "workers" {
  family                   = "societysphere-${var.environment}-workers"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.workers_cpu
  memory                   = var.workers_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_workers_arn != null ? var.task_role_workers_arn : var.task_role_arn

  container_definitions = jsonencode([
    {
      name        = "workers"
      image       = var.api_image
      essential   = true
      user        = "1001:1001"
      stopTimeout = 30
      command     = ["python", "-m", "apps.api.src.workers.runner"]

      environment = [
        {
          name  = "APP_NAME"
          value = "SocietySphere"
        },
        {
          name  = "APP_ENV"
          value = var.environment
        },
        {
          name  = "PYTHONUNBUFFERED"
          value = "1"
        }
      ]

      secrets = var.db_secret_arn != null && var.app_secret_arn != null ? [
        {
          name      = "DATABASE_CREDENTIALS"
          valueFrom = var.db_secret_arn
        },
        {
          name      = "APP_SECRETS"
          valueFrom = var.app_secret_arn
        }
      ] : []

      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import sys; sys.exit(0)\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/societysphere-${var.environment}-workers"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "workers"
        }
      }
    }
  ])

  tags = {
    Name        = "societysphere-${var.environment}-workers-task"
    Environment = var.environment
    Tier        = "Workers"
  }
}

# ==============================================================================
# ECS SERVICES: ROLLING DEPLOYMENT & CIRCUIT BREAKER PROTECTION
# ==============================================================================

# Web Frontend Service
resource "aws_ecs_service" "web" {
  name            = "societysphere-${var.environment}-web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  health_check_grace_period_seconds = (var.enable_alb && var.vpc_id != "") || var.alb_target_group_web_arn != "" ? var.health_check_grace_period_seconds : null

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_web_id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.enable_alb && var.vpc_id != "" ? [aws_lb_target_group.web[0].arn] : (var.alb_target_group_web_arn != "" ? [var.alb_target_group_web_arn] : [])
    content {
      target_group_arn = load_balancer.value
      container_name   = "web"
      container_port   = 3000
    }
  }

  tags = {
    Name        = "societysphere-${var.environment}-web-service"
    Environment = var.environment
    Tier        = "Frontend"
  }
}

# Backend API Service
resource "aws_ecs_service" "api" {
  name            = "societysphere-${var.environment}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  health_check_grace_period_seconds = (var.enable_alb && var.vpc_id != "") || var.alb_target_group_api_arn != "" ? var.health_check_grace_period_seconds : null

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_api_id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.enable_alb && var.vpc_id != "" ? [aws_lb_target_group.api[0].arn] : (var.alb_target_group_api_arn != "" ? [var.alb_target_group_api_arn] : [])
    content {
      target_group_arn = load_balancer.value
      container_name   = "api"
      container_port   = 8000
    }
  }

  tags = {
    Name        = "societysphere-${var.environment}-api-service"
    Environment = var.environment
    Tier        = "BackendAPI"
  }
}

# Background Workers Service (Strictly Isolated: No ALB load_balancer block)
resource "aws_ecs_service" "workers" {
  name            = "societysphere-${var.environment}-workers"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.workers.arn
  desired_count   = var.workers_desired_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_workers_id]
    assign_public_ip = false
  }

  tags = {
    Name        = "societysphere-${var.environment}-workers-service"
    Environment = var.environment
    Tier        = "Workers"
  }
}
