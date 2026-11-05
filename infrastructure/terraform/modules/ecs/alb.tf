# ==============================================================================
# APPLICATION LOAD BALANCER: ROUTING, TARGET GROUPS & TLS TERMINATION
# ==============================================================================

# Application Load Balancer (Public Ingress)
# tfsec:ignore:aws-elb-alb-not-public: SocietySphere ALB is explicitly designed for public internet ingress
resource "aws_lb" "main" {
  count                      = var.enable_alb && length(var.public_subnet_ids) > 0 ? 1 : 0
  name                       = "societysphere-${var.environment}-alb"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [var.sg_alb_id]
  subnets                    = var.public_subnet_ids
  enable_deletion_protection = var.enable_deletion_protection
  drop_invalid_header_fields = true

  #checkov:skip=CKV_AWS_150: Deletion protection is environment configurable
  #checkov:skip=CKV_AWS_91: Access logging is configured in monitoring phase
  #checkov:skip=CKV2_AWS_28: WAF association is configured in security hardening phase 22G

  tags = {
    Name        = "societysphere-${var.environment}-alb"
    Environment = var.environment
  }
}

# Target Group: Frontend Web (Next.js Standalone, Port 3000)
resource "aws_lb_target_group" "web" {
  #checkov:skip=CKV_AWS_378: TLS terminates at ALB HTTPS listener; intra-VPC communication to Fargate tasks uses HTTP
  count                = var.enable_alb && var.vpc_id != "" ? 1 : 0
  name                 = "societysphere-${var.environment}-tg-web"
  port                 = 3000
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  target_type          = "ip"
  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/"
    port                = "3000"
    protocol            = "HTTP"
    matcher             = "200-399"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name        = "societysphere-${var.environment}-tg-web"
    Environment = var.environment
    Tier        = "Frontend"
  }
}

# Target Group: Backend API (FastAPI, Port 8000)
resource "aws_lb_target_group" "api" {
  #checkov:skip=CKV_AWS_378: TLS terminates at ALB HTTPS listener; intra-VPC communication to Fargate tasks uses HTTP
  count                = var.enable_alb && var.vpc_id != "" ? 1 : 0
  name                 = "societysphere-${var.environment}-tg-api"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  target_type          = "ip"
  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/health"
    port                = "8000"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name        = "societysphere-${var.environment}-tg-api"
    Environment = var.environment
    Tier        = "BackendAPI"
  }
}

# ACM Certificate Placeholder for Offline / Speculative Synthesis
resource "aws_acm_certificate" "default" {
  count             = var.enable_alb && var.certificate_arn == null ? 1 : 0
  domain_name       = "societysphere.local"
  validation_method = "DNS"

  tags = {
    Name        = "societysphere-${var.environment}-acm-cert"
    Environment = var.environment
  }
}

# HTTP Listener (Port 80): Permanent 301 Redirect to HTTPS (Port 443)
resource "aws_lb_listener" "http" {
  count             = var.enable_alb && length(var.public_subnet_ids) > 0 ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS Listener (Port 443): Secure TLS Termination
resource "aws_lb_listener" "https" {
  count             = var.enable_alb && length(var.public_subnet_ids) > 0 && var.vpc_id != "" ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn != null ? var.certificate_arn : aws_acm_certificate.default[0].arn

  # Default Action: Forward to Web Frontend (Next.js)
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web[0].arn
  }
}

# Listener Rule 0: Block OpenAPI & Documentation in Production/Staging (Priority 5)
resource "aws_lb_listener_rule" "block_openapi" {
  count        = var.enable_alb && length(var.public_subnet_ids) > 0 && var.vpc_id != "" && !var.enable_docs_routing ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 5

  action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = jsonencode({ detail = "Not Found" })
      status_code  = "404"
    }
  }

  condition {
    path_pattern {
      values = ["/openapi.json", "*/openapi.json", "/docs", "/docs/*", "/redoc", "/redoc/*"]
    }
  }
}

# Listener Rule 1: API Path Routing (/api/* -> FastAPI Backend)
resource "aws_lb_listener_rule" "api" {
  count        = var.enable_alb && length(var.public_subnet_ids) > 0 && var.vpc_id != "" ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api[0].arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# Listener Rule 2: Root Health Probes (/health* -> FastAPI Backend)
resource "aws_lb_listener_rule" "health" {
  count        = var.enable_alb && length(var.public_subnet_ids) > 0 && var.vpc_id != "" ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api[0].arn
  }

  condition {
    path_pattern {
      values = ["/health", "/health/*"]
    }
  }
}

# Listener Rule 3: Interactive Documentation (/docs, /redoc -> FastAPI Backend in Dev/QA)
resource "aws_lb_listener_rule" "docs" {
  count        = var.enable_alb && length(var.public_subnet_ids) > 0 && var.vpc_id != "" && var.enable_docs_routing ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 30

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api[0].arn
  }

  condition {
    path_pattern {
      values = ["/docs", "/redoc"]
    }
  }
}
