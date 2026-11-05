# ==============================================================================
# APPLICATION AUTOSCALING: ECS SERVICE METRIC TARGET TRACKING
# ==============================================================================

# Web Frontend Scalable Target
resource "aws_appautoscaling_target" "web" {
  count              = var.enable_autoscaling ? 1 : 0
  max_capacity       = var.web_max_capacity
  min_capacity       = var.web_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.web.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Web CPU Target Tracking Policy (70%)
resource "aws_appautoscaling_policy" "web_cpu" {
  count              = var.enable_autoscaling ? 1 : 0
  name               = "societysphere-${var.environment}-web-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.web[0].resource_id
  scalable_dimension = aws_appautoscaling_target.web[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.web[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Web Memory Target Tracking Policy (80%)
resource "aws_appautoscaling_policy" "web_memory" {
  count              = var.enable_autoscaling ? 1 : 0
  name               = "societysphere-${var.environment}-web-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.web[0].resource_id
  scalable_dimension = aws_appautoscaling_target.web[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.web[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Backend API Scalable Target
resource "aws_appautoscaling_target" "api" {
  count              = var.enable_autoscaling ? 1 : 0
  max_capacity       = var.api_max_capacity
  min_capacity       = var.api_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# API CPU Target Tracking Policy (70%)
resource "aws_appautoscaling_policy" "api_cpu" {
  count              = var.enable_autoscaling ? 1 : 0
  name               = "societysphere-${var.environment}-api-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.api[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# API Memory Target Tracking Policy (80%)
resource "aws_appautoscaling_policy" "api_memory" {
  count              = var.enable_autoscaling ? 1 : 0
  name               = "societysphere-${var.environment}-api-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.api[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Background Workers Scalable Target
resource "aws_appautoscaling_target" "workers" {
  count              = var.enable_autoscaling ? 1 : 0
  max_capacity       = var.workers_max_capacity
  min_capacity       = var.workers_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.workers.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Workers CPU Target Tracking Policy (75%)
resource "aws_appautoscaling_policy" "workers_cpu" {
  count              = var.enable_autoscaling ? 1 : 0
  name               = "societysphere-${var.environment}-workers-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.workers[0].resource_id
  scalable_dimension = aws_appautoscaling_target.workers[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.workers[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 75.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Workers Memory Target Tracking Policy (80%)
resource "aws_appautoscaling_policy" "workers_memory" {
  count              = var.enable_autoscaling ? 1 : 0
  name               = "societysphere-${var.environment}-workers-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.workers[0].resource_id
  scalable_dimension = aws_appautoscaling_target.workers[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.workers[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
