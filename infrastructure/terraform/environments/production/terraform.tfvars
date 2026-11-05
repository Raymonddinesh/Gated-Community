# ==============================================================================
# ENVIRONMENT: PRODUCTION VARIABLES
# ==============================================================================
# SAFETY GATE: By default, production applies are LOCKED.
# Set production_apply_authorized = true ONLY during authorized maintenance windows.
# ==============================================================================

aws_region                  = "ap-south-1"
environment                 = "production"
production_apply_authorized = false

# Network Topology (Phase 22A Architecture: 10.0.0.0/16)
vpc_cidr            = "10.0.0.0/16"
availability_zones  = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
app_subnet_cidrs    = ["10.0.10.0/22", "10.0.14.0/22", "10.0.18.0/22"]
data_subnet_cidrs   = ["10.0.30.0/24", "10.0.31.0/24", "10.0.32.0/24"]

# Sizing Baselines (Phase 22A Architecture Assessment: Option B)
rds_instance_class = "db.m6g.xlarge"
redis_node_type    = "cache.m6g.large"
mq_instance_type   = "mq.m5.large"
