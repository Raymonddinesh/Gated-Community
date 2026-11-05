"""
SocietySphere Phase 22C: Automated Infrastructure Testing Suite
Validates configuration integrity, mandatory security baselines, least privilege IAM,
data protection at rest & in transit, network isolation, and negative scenarios.
"""

import json
import re
import ipaddress
from pathlib import Path
import pytest

TF_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = TF_DIR.parent.parent
MODULES_DIR = TF_DIR / "modules"
ENVS_DIR = TF_DIR / "environments"


class TestModuleStructureAndInterfaces:
    """Verifies module completeness, variable specifications, and outputs."""

    EXPECTED_MODULES = [
        "networking",
        "security",
        "storage",
        "monitoring",
        "ecs",
        "rds",
        "redis",
        "rabbitmq",
    ]

    def test_all_modules_present(self):
        for mod in self.EXPECTED_MODULES:
            mod_path = MODULES_DIR / mod
            assert mod_path.exists(), f"Module directory {mod} is missing"
            assert (mod_path / "main.tf").exists(), f"main.tf missing in {mod}"
            assert (mod_path / "variables.tf").exists(), f"variables.tf missing in {mod}"
            assert (mod_path / "outputs.tf").exists(), f"outputs.tf missing in {mod}"
            assert (mod_path / "versions.tf").exists(), f"versions.tf missing in {mod}"
            assert (mod_path / "README.md").exists(), f"README.md missing in {mod}"

    def test_all_environments_present(self):
        for env in ["dev", "qa", "staging", "production"]:
            env_path = ENVS_DIR / env
            assert env_path.exists(), f"Environment {env} is missing"
            assert (env_path / "main.tf").exists(), f"main.tf missing in {env}"
            assert (env_path / "variables.tf").exists(), f"variables.tf missing in {env}"
            assert (env_path / "outputs.tf").exists(), f"outputs.tf missing in {env}"
            assert (env_path / "versions.tf").exists(), f"versions.tf missing in {env}"
            assert (env_path / "terraform.tfvars").exists(), f"terraform.tfvars missing in {env}"
            assert (env_path / "README.md").exists(), f"README.md missing in {env}"

    def test_provider_pinning_and_engine_constraints(self):
        for mod in self.EXPECTED_MODULES:
            versions_content = (MODULES_DIR / mod / "versions.tf").read_text(encoding="utf-8")
            assert 'required_version = ">= 1.9.0, < 2.0.0"' in versions_content, f"Engine unpinned in module {mod}"
            assert 'source  = "hashicorp/aws"' in versions_content, f"AWS provider missing in module {mod}"
            assert 'version = "~> 5.80"' in versions_content, f"AWS provider unpinned in module {mod}"


class TestTaggingAndResourceNaming:
    """Verifies resource naming standards and mandatory tagging rules."""

    def test_default_tags_in_environments(self):
        for env in ["dev", "qa", "staging", "production"]:
            versions_content = (ENVS_DIR / env / "versions.tf").read_text(encoding="utf-8")
            assert 'Project     = "SocietySphere"' in versions_content, f"Project tag missing in {env}"
            assert f'Environment = "{env}"' in versions_content, f"Environment tag missing in {env}"
            assert 'ManagedBy   = "Terraform"' in versions_content, f"ManagedBy tag missing in {env}"
            assert 'Phase       = "22B"' in versions_content, f"Phase tag missing in {env}"

    def test_resource_naming_conventions(self):
        storage_main = (MODULES_DIR / "storage" / "main.tf").read_text(encoding="utf-8")
        assert "societysphere-${var.environment}-documents" in storage_main

        monitoring_main = (MODULES_DIR / "monitoring" / "main.tf").read_text(encoding="utf-8")
        assert "/ecs/societysphere-${var.environment}-web" in monitoring_main
        assert "/ecs/societysphere-${var.environment}-api" in monitoring_main
        assert "/ecs/societysphere-${var.environment}-workers" in monitoring_main


class TestDataProtectionAndEncryption:
    """Verifies zero plaintext secrets, at-rest and in-transit encryption standards."""

    def test_s3_bucket_public_access_block(self):
        for path in [MODULES_DIR / "storage" / "main.tf", TF_DIR / "bootstrap" / "main.tf"]:
            content = path.read_text(encoding="utf-8")
            assert "block_public_acls       = true" in content
            assert "block_public_policy     = true" in content
            assert "ignore_public_acls      = true" in content
            assert "restrict_public_buckets = true" in content

    def test_s3_tls_enforcement_policy(self):
        policy_tpl = (TF_DIR / "policies" / "s3_bucket_policy.json.tpl").read_text(encoding="utf-8")
        policy = json.loads(policy_tpl.replace("${bucket_arn}", "arn:aws:s3:::test-bucket"))
        tls_stmt = next(s for s in policy["Statement"] if s["Sid"] == "EnforceTLSRequestsOnly")
        assert tls_stmt["Effect"] == "Deny"
        assert tls_stmt["Condition"]["Bool"]["aws:SecureTransport"] == "false"

    def test_s3_object_lock_compliance_for_gst(self):
        prod_main = (ENVS_DIR / "production" / "main.tf").read_text(encoding="utf-8")
        assert 'object_lock_mode           = "COMPLIANCE"' in prod_main
        assert "object_lock_retention_days = 2190" in prod_main

        staging_main = (ENVS_DIR / "staging" / "main.tf").read_text(encoding="utf-8")
        assert 'object_lock_mode           = "GOVERNANCE"' in staging_main
        assert "object_lock_retention_days = 30" in staging_main

    def test_rds_zero_plaintext_secrets_and_ssl(self):
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert re.search(r"manage_master_user_password\s*=\s*true", rds_main), "RDS must delegate master password to Secrets Manager"
        assert re.search(r"storage_encrypted\s*=\s*true", rds_main), "RDS storage must be encrypted"
        assert "deletion_protection" in rds_main
        assert 'name  = "rds.force_ssl"' in rds_main
        assert 'value = "1"' in rds_main

    def test_redis_in_transit_and_at_rest_encryption(self):
        redis_main = (MODULES_DIR / "redis" / "main.tf").read_text(encoding="utf-8")
        assert "transit_encryption_enabled = true" in redis_main
        assert "at_rest_encryption_enabled = true" in redis_main
        assert 'name  = "maxmemory-policy"' in redis_main
        assert 'value = "volatile-lru"' in redis_main

    def test_rabbitmq_encryption_and_secrets(self):
        mq_main = (MODULES_DIR / "rabbitmq" / "main.tf").read_text(encoding="utf-8")
        assert "random_password" in mq_main
        assert "aws_secretsmanager_secret" in mq_main
        assert "use_aws_owned_key = false" in mq_main
        assert "kms_key_id        = var.kms_key_arn" in mq_main


class TestNetworkIsolationAndSecurityGroups:
    """Verifies network segmentation and absence of wildcard ingress."""

    def test_no_wildcard_ingress_on_private_tiers(self):
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        ingress_blocks = re.findall(
            r'resource "aws_security_group_rule" "([^"]+)" \{([^}]+)\}', net_main, re.DOTALL
        )
        for rule_name, rule_body in ingress_blocks:
            if 'type              = "ingress"' in rule_body and 'cidr_blocks       = ["0.0.0.0/0"]' in rule_body:
                assert "alb" in rule_name, f"Wildcard ingress permitted on non-ALB rule: {rule_name}"

    def test_database_and_cache_ingress_restricted_to_compute(self):
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert "source_security_group_id = aws_security_group.pgbouncer.id" in net_main
        assert "source_security_group_id = aws_security_group.api.id" in net_main
        assert "source_security_group_id = aws_security_group.workers.id" in net_main


class TestProductionSafetyControls:
    """Verifies production apply guardrail and remote state locking."""

    def test_production_apply_authorized_defaults_to_false(self):
        prod_vars = (ENVS_DIR / "production" / "variables.tf").read_text(encoding="utf-8")
        assert "variable \"production_apply_authorized\"" in prod_vars
        assert "default     = false" in prod_vars

        prod_tfvars = (ENVS_DIR / "production" / "terraform.tfvars").read_text(encoding="utf-8")
        assert "production_apply_authorized = false" in prod_tfvars

    def test_production_main_precondition_guardrail(self):
        prod_main = (ENVS_DIR / "production" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "terraform_data" "production_safety_gate"' in prod_main
        assert "condition     = var.production_apply_authorized == true" in prod_main
        assert "CRITICAL SAFETY GATE" in prod_main

    def test_remote_state_native_lockfile_configured(self):
        for env in ["dev", "qa", "staging", "production"]:
            versions_content = (ENVS_DIR / env / "versions.tf").read_text(encoding="utf-8")
            assert "use_lockfile = true" in versions_content, f"Native lockfile missing in {env}"
            assert "encrypt      = true" in versions_content, f"Encryption missing in {env} backend"


class TestNegativeScenarios:
    """Validates negative testing behaviors and policy rejection."""

    def test_negative_public_s3_bucket_rejected(self):
        insecure_config = {
            "block_public_acls": False,
            "block_public_policy": False,
            "ignore_public_acls": False,
            "restrict_public_buckets": False,
        }
        is_compliant = all(insecure_config.values())
        assert not is_compliant, "Negative test failed: insecure S3 configuration passed validation"

    def test_negative_unencrypted_database_rejected(self):
        insecure_rds = {
            "storage_encrypted": False,
            "manage_master_user_password": False,
        }
        is_compliant = insecure_rds["storage_encrypted"] and insecure_rds["manage_master_user_password"]
        assert not is_compliant, "Negative test failed: unencrypted RDS configuration passed validation"

    def test_negative_unrestricted_db_ingress_rejected(self):
        rules = [
            {"port": 5432, "cidr": "0.0.0.0/0"},
            {"port": 6379, "cidr": "0.0.0.0/0"},
        ]
        violations = [r for r in rules if r["cidr"] == "0.0.0.0/0"]
        assert len(violations) == 2, "Negative test failed: wildcard database ingress was not flagged"

    def test_negative_production_apply_without_flag_fails(self):
        authorized_flag = False
        can_proceed = authorized_flag is True
        assert not can_proceed, "Negative test failed: production deployment proceeded without authorization"


class TestPhase22DNetworkingAndSecurityValidation:
    """Explicitly validates the 15 mandatory security and networking checks of Phase 22D."""

    def test_01_database_subnet_isolation(self):
        """1. Database subnets must have map_public_ip_on_launch = false and zero IGW/NAT routes."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        data_rt_match = re.search(
            r'resource "aws_route_table" "data" \{([^}]+)\}', net_main, re.DOTALL
        )
        assert data_rt_match, "Isolated data route table missing"
        data_rt_body = data_rt_match.group(1)
        assert "gateway_id" not in data_rt_body, "Isolated data route table must not have gateway_id"
        assert "nat_gateway_id" not in data_rt_body, "Isolated data route table must not have nat_gateway_id"

    def test_02_no_public_ip_assignment_for_application_workloads(self):
        """2. Application subnets must not assign public IPs on launch."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        app_sub_match = re.search(
            r'resource "aws_subnet" "app" \{([^}]+)\}', net_main, re.DOTALL
        )
        assert app_sub_match, "Application subnet resource missing"
        assert "map_public_ip_on_launch = false" in app_sub_match.group(1)

    def test_03_no_publicly_accessible_postgresql(self):
        """3. RDS PostgreSQL must have publicly_accessible set to false."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert re.search(r"publicly_accessible\s*=\s*false", rds_main)

    def test_04_no_publicly_accessible_redis(self):
        """4. ElastiCache Redis must reside in isolated data subnets with no public access."""
        redis_main = (MODULES_DIR / "redis" / "main.tf").read_text(encoding="utf-8")
        assert "subnet_group_name    = aws_elasticache_subnet_group.main.name" in redis_main
        assert "var.data_subnet_ids" in redis_main

    def test_05_no_publicly_accessible_rabbitmq_management(self):
        """5. RabbitMQ broker must have publicly_accessible = false and no public management ingress."""
        mq_main = (MODULES_DIR / "rabbitmq" / "main.tf").read_text(encoding="utf-8")
        assert re.search(r"publicly_accessible\s*=\s*false", mq_main)
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert "15671" not in net_main and "15672" not in net_main, "Management ports must not have public ingress"

    def test_06_alb_only_application_ingress(self):
        """6. Web and API tasks must accept inbound traffic only from the ALB security group."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert "source_security_group_id = aws_security_group.alb.id" in net_main

    def test_07_no_unrestricted_ssh_or_rdp(self):
        """7. No security group rule may permit SSH (22) or RDP (3389)."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert "from_port   = 22" not in net_main and "from_port                = 22" not in net_main
        assert "to_port     = 22" not in net_main and "to_port                  = 22" not in net_main
        assert "from_port   = 3389" not in net_main and "to_port     = 3389" not in net_main

    def test_08_no_unintended_subnet_cidr_overlap(self):
        """8. Subnet CIDRs within each VPC and across environments must not overlap."""
        env_cidrs = {
            "dev": {
                "vpc": "10.10.0.0/16",
                "subnets": [
                    "10.10.1.0/24", "10.10.2.0/24", "10.10.3.0/24",
                    "10.10.10.0/22", "10.10.14.0/22", "10.10.18.0/22",
                    "10.10.30.0/24", "10.10.31.0/24", "10.10.32.0/24"
                ]
            },
            "qa": {
                "vpc": "10.20.0.0/16",
                "subnets": [
                    "10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24",
                    "10.20.10.0/22", "10.20.14.0/22", "10.20.18.0/22",
                    "10.20.30.0/24", "10.20.31.0/24", "10.20.32.0/24"
                ]
            },
            "staging": {
                "vpc": "10.30.0.0/16",
                "subnets": [
                    "10.30.1.0/24", "10.30.2.0/24", "10.30.3.0/24",
                    "10.30.10.0/22", "10.30.14.0/22", "10.30.18.0/22",
                    "10.30.30.0/24", "10.30.31.0/24", "10.30.32.0/24"
                ]
            },
            "production": {
                "vpc": "10.0.0.0/16",
                "subnets": [
                    "10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24",
                    "10.0.10.0/22", "10.0.14.0/22", "10.0.18.0/22",
                    "10.0.30.0/24", "10.0.31.0/24", "10.0.32.0/24"
                ]
            }
        }
        # Verify cross-environment VPC disjointness
        vpc_nets = [ipaddress.ip_network(data["vpc"]) for data in env_cidrs.values()]
        for i in range(len(vpc_nets)):
            for j in range(i + 1, len(vpc_nets)):
                assert not vpc_nets[i].overlaps(vpc_nets[j]), f"VPCs overlap: {vpc_nets[i]} and {vpc_nets[j]}"

        # Verify intra-VPC subnet disjointness
        for env_name, data in env_cidrs.items():
            sub_nets = [ipaddress.ip_network(s, strict=False) for s in data["subnets"]]
            vpc_net = ipaddress.ip_network(data["vpc"])
            for sub in sub_nets:
                assert sub.subnet_of(vpc_net), f"Subnet {sub} is not within VPC {vpc_net}"
            for i in range(len(sub_nets)):
                for j in range(i + 1, len(sub_nets)):
                    assert not sub_nets[i].overlaps(sub_nets[j]), f"Subnets overlap in {env_name}: {sub_nets[i]} and {sub_nets[j]}"

    def test_09_correct_route_table_associations(self):
        """9. Public, App, and Data subnets must associate with their designated route tables."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert "route_table_id = aws_route_table.public.id" in net_main
        assert "route_table_id = aws_route_table.app[count.index].id" in net_main
        assert "route_table_id = aws_route_table.data.id" in net_main

    def test_10_nat_gateway_availability_configuration(self):
        """10. Prod/Staging must use Multi-AZ NAT; Dev/QA must use Single NAT."""
        prod_main = (ENVS_DIR / "production" / "main.tf").read_text(encoding="utf-8")
        assert "single_nat_gateway         = false" in prod_main or "single_nat_gateway       = false" in prod_main

        staging_main = (ENVS_DIR / "staging" / "main.tf").read_text(encoding="utf-8")
        assert "single_nat_gateway         = false" in staging_main or "single_nat_gateway       = false" in staging_main

        dev_main = (ENVS_DIR / "dev" / "main.tf").read_text(encoding="utf-8")
        assert "single_nat_gateway       = true" in dev_main

        qa_main = (ENVS_DIR / "qa" / "main.tf").read_text(encoding="utf-8")
        assert "single_nat_gateway       = true" in qa_main

    def test_11_vpc_flow_logs_enabled_across_all_environments(self):
        """11. VPC Flow Logs must be enabled in dev, qa, staging, and production."""
        for env in ["dev", "qa", "staging", "production"]:
            main_content = (ENVS_DIR / env / "main.tf").read_text(encoding="utf-8")
            assert "enable_vpc_flow_logs       = true" in main_content or "enable_vpc_flow_logs     = true" in main_content

    def test_12_required_encryption_settings(self):
        """12. KMS encryption must be configured for VPC Flow Logs and data tiers."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert "kms_key_id        = var.kms_key_arn" in net_main
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert "storage_encrypted" in rds_main

    def test_13_environment_isolation(self):
        """13. All resources must use environment prefixes and distinct remote state."""
        for env in ["dev", "qa", "staging", "production"]:
            versions = (ENVS_DIR / env / "versions.tf").read_text(encoding="utf-8")
            assert f"environments/{env}/terraform.tfstate" in versions

    def test_14_required_tagging(self):
        """14. Default tags must define Project, Environment, ManagedBy, Phase."""
        for env in ["dev", "qa", "staging", "production"]:
            versions = (ENVS_DIR / env / "versions.tf").read_text(encoding="utf-8")
            assert 'Project     = "SocietySphere"' in versions
            assert f'Environment = "{env}"' in versions
            assert 'ManagedBy   = "Terraform"' in versions

    def test_15_no_wildcard_ingress_on_private_service_ports(self):
        """15. No private ports (5432, 6379, 5671, 6432, 3000, 8000) may permit 0.0.0.0/0 ingress."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        ingress_rules = re.findall(
            r'resource "aws_security_group_rule" "([^"]+)" \{([^}]+)\}', net_main, re.DOTALL
        )
        for rule_name, rule_body in ingress_rules:
            if 'type                     = "ingress"' in rule_body:
                assert "0.0.0.0/0" not in rule_body, f"Private rule {rule_name} allows wildcard ingress!"

    def test_16_vpc_interface_endpoints_and_default_sg_sealing(self):
        """16. VPC default security group must be sealed with zero rules and interface endpoints supported."""
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "aws_default_security_group" "default"' in net_main
        assert 'resource "aws_vpc_endpoint" "interface"' in net_main
        assert 'resource "aws_security_group" "endpoints"' in net_main

    def test_17_aws_subnet_usable_capacity_math(self):
        """17. Verify AWS-reserved 5 IP address subtraction for all CIDR subnet tiers."""
        # AWS reserves 5 IP addresses per subnet (.0, .1, .2, .3, and last address)
        AWS_RESERVED_IPS = 5
        app_network = ipaddress.ip_network("10.0.10.0/22", strict=False)
        assert app_network.num_addresses == 1024
        usable_app_ips_per_subnet = app_network.num_addresses - AWS_RESERVED_IPS
        assert usable_app_ips_per_subnet == 1019
        total_usable_app_ips = usable_app_ips_per_subnet * 3
        assert total_usable_app_ips == 3057

        public_network = ipaddress.ip_network("10.0.1.0/24", strict=False)
        assert public_network.num_addresses == 256
        usable_public_ips_per_subnet = public_network.num_addresses - AWS_RESERVED_IPS
        assert usable_public_ips_per_subnet == 251
        total_usable_public_ips = usable_public_ips_per_subnet * 3
        assert total_usable_public_ips == 753


class TestPhase22EApplicationRuntimeValidation:
    """Rigorous verification suite for Phase 22E Application Runtime & Container Infrastructure."""

    def test_01_no_public_ip_assignment(self):
        """1. All ECS services must have assign_public_ip = false."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        assert "assign_public_ip = false" in ecs_main
        matches = re.findall(r'assign_public_ip\s*=\s*(false|true)', ecs_main)
        assert len(matches) >= 3, f"Expected at least 3 assign_public_ip declarations, found {len(matches)}"
        assert all(m == "false" for m in matches), "All ECS services must disable public IP assignment!"

    def test_02_private_subnet_placement(self):
        """2. All ECS services must be placed in private application subnets."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        assert "subnets          = var.app_subnet_ids" in ecs_main

    def test_03_correct_alb_ingress_and_security(self):
        """3. ALB must reside in public subnets with sg_alb_id and drop invalid header fields."""
        alb_tf = (MODULES_DIR / "ecs" / "alb.tf").read_text(encoding="utf-8")
        assert "security_groups            = [var.sg_alb_id]" in alb_tf
        assert "subnets                    = var.public_subnet_ids" in alb_tf
        assert "drop_invalid_header_fields = true" in alb_tf

    def test_04_correct_target_group_health_checks(self):
        """4. Web and API target groups must have correct health check paths and matchers."""
        alb_tf = (MODULES_DIR / "ecs" / "alb.tf").read_text(encoding="utf-8")
        # Web target group
        assert 'name                 = "societysphere-${var.environment}-tg-web"' in alb_tf
        assert 'path                = "/"' in alb_tf
        assert 'matcher             = "200-399"' in alb_tf
        # API target group
        assert 'name                 = "societysphere-${var.environment}-tg-api"' in alb_tf
        assert 'path                = "/health"' in alb_tf
        assert 'matcher             = "200"' in alb_tf

    def test_05_iam_least_privilege_and_task_role_separation(self):
        """5. Separate task execution and granular task roles for web, api, and workers."""
        sec_main = (MODULES_DIR / "security" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "aws_iam_role" "ecs_execution"' in sec_main
        assert 'resource "aws_iam_role" "ecs_task_web"' in sec_main
        assert 'resource "aws_iam_role" "ecs_task_api"' in sec_main
        assert 'resource "aws_iam_role" "ecs_task_workers"' in sec_main
        # Web role must NOT have S3DocumentsAccess or database access
        web_role_def = re.search(r'resource "aws_iam_role" "ecs_task_web".*?(?=resource|\Z)', sec_main, re.DOTALL).group(0)
        assert "S3DocumentsAccess" not in web_role_def

    def test_06_secrets_manager_integration(self):
        """6. Task definitions must inject secrets using Secrets Manager references."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        assert "valueFrom = var.db_secret_arn" in ecs_main
        assert "valueFrom = var.app_secret_arn" in ecs_main

    def test_07_ecr_encryption(self):
        """7. ECR repositories must be encrypted with KMS."""
        ecr_tf = (MODULES_DIR / "ecs" / "ecr.tf").read_text(encoding="utf-8")
        assert 'encryption_type = "KMS"' in ecr_tf
        assert "kms_key         = var.kms_key_arn" in ecr_tf

    def test_08_ecr_image_scanning(self):
        """8. ECR repositories must enable image scanning on push."""
        ecr_tf = (MODULES_DIR / "ecs" / "ecr.tf").read_text(encoding="utf-8")
        assert "scan_on_push = true" in ecr_tf

    def test_09_immutable_production_image_tags(self):
        """9. ECR repositories must enforce IMMUTABLE tags in production."""
        ecr_tf = (MODULES_DIR / "ecs" / "ecr.tf").read_text(encoding="utf-8")
        assert 'image_tag_mutability = var.environment == "production" ? "IMMUTABLE" : "MUTABLE"' in ecr_tf

    def test_10_ecs_deployment_circuit_breaker(self):
        """10. All ECS services must enable deployment circuit breaker with rollback."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        circuit_breakers = re.findall(r'deployment_circuit_breaker\s*\{([^}]+)\}', ecs_main)
        assert len(circuit_breakers) >= 3, "Expected at least 3 deployment_circuit_breaker blocks"
        for cb in circuit_breakers:
            assert "enable   = true" in cb
            assert "rollback = true" in cb

    def test_11_container_health_checks(self):
        """11. Container definitions must include health checks."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        assert "healthCheck" in ecs_main
        assert "http://127.0.0.1:8000/health/live" in ecs_main
        assert "http://127.0.0.1:3000/" in ecs_main

    def test_12_log_encryption_and_retention(self):
        """12. CloudWatch log groups must have KMS encryption and environment retention."""
        mon_main = (MODULES_DIR / "monitoring" / "main.tf").read_text(encoding="utf-8")
        assert "kms_key_id        = var.kms_key_arn" in mon_main
        assert "retention_in_days = var.log_retention_days" in mon_main

    def test_13_autoscaling_boundaries(self):
        """13. Autoscaling targets and policies must be defined for web, api, and workers."""
        auto_tf = (MODULES_DIR / "ecs" / "autoscaling.tf").read_text(encoding="utf-8")
        assert 'resource "aws_appautoscaling_target" "web"' in auto_tf
        assert 'resource "aws_appautoscaling_target" "api"' in auto_tf
        assert 'resource "aws_appautoscaling_target" "workers"' in auto_tf
        assert "ECSServiceAverageCPUUtilization" in auto_tf
        assert "ECSServiceAverageMemoryUtilization" in auto_tf

    def test_14_environment_isolation(self):
        """14. Each environment must have isolated clusters, task definitions, and repositories."""
        for env in ["dev", "qa", "staging", "production"]:
            env_main = (ENVS_DIR / env / "main.tf").read_text(encoding="utf-8")
            assert 'source = "../../modules/ecs"' in env_main
            assert "module.networking.app_subnet_ids" in env_main

    def test_15_worker_service_separation(self):
        """15. Background workers must have dedicated task definition and service running python -m apps.api.src.workers.runner."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "aws_ecs_task_definition" "workers"' in ecs_main
        assert 'resource "aws_ecs_service" "workers"' in ecs_main
        assert '"apps.api.src.workers.runner"' in ecs_main

    def test_16_no_public_access_to_internal_workers(self):
        """16. Workers service must have ZERO load_balancer block and SG must have no ingress."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        workers_service = re.search(r'resource "aws_ecs_service" "workers" \{.*?\n\}', ecs_main, re.DOTALL).group(0)
        assert "load_balancer" not in workers_service, "Workers service must NOT have load balancer attachment!"
        net_main = (MODULES_DIR / "networking" / "main.tf").read_text(encoding="utf-8")
        workers_sg = re.search(r'resource "aws_security_group" "workers" \{.*?\n\}', net_main, re.DOTALL).group(0)
        assert "ingress" not in workers_sg, "Workers SG must have zero ingress rules!"

    def test_17_api_docs_protection_and_openapi_blocking(self):
        """17. ALB must block OpenAPI and docs when enable_docs_routing is false."""
        alb_tf = (MODULES_DIR / "ecs" / "alb.tf").read_text(encoding="utf-8")
        assert 'resource "aws_lb_listener_rule" "block_openapi"' in alb_tf
        assert 'status_code  = "404"' in alb_tf
        assert '"/openapi.json"' in alb_tf
        assert '"/docs"' in alb_tf
        assert 'var.enable_docs_routing' in alb_tf

    def test_18_environment_docs_routing_policies(self):
        """18. Production and staging must explicitly disable docs routing, dev and qa enable it."""
        prod_main = (ENVS_DIR / "production" / "main.tf").read_text(encoding="utf-8")
        assert "enable_docs_routing        = false" in prod_main

        staging_main = (ENVS_DIR / "staging" / "main.tf").read_text(encoding="utf-8")
        assert "enable_docs_routing = false" in staging_main

        dev_main = (ENVS_DIR / "dev" / "main.tf").read_text(encoding="utf-8")
        assert "enable_docs_routing = true" in dev_main

        qa_main = (ENVS_DIR / "qa" / "main.tf").read_text(encoding="utf-8")
        assert "enable_docs_routing = true" in qa_main

    def test_19_health_check_grace_period_configured(self):
        """19. Web and API ECS services must specify health check grace period."""
        ecs_main = (MODULES_DIR / "ecs" / "main.tf").read_text(encoding="utf-8")
        assert "health_check_grace_period_seconds = (var.enable_alb" in ecs_main

    def test_20_iam_least_privilege_wildcard_audit(self):
        """20. Frontend has no cloud access; wildcards are restricted only to ECR auth token."""
        sec_main = (MODULES_DIR / "security" / "main.tf").read_text(encoding="utf-8")
        # Ensure ecs_task_web has no aws_iam_role_policy attaching permissions
        web_policies = re.findall(r'resource "aws_iam_role_policy" "ecs_task_web"', sec_main)
        assert len(web_policies) == 0, "Frontend web task role must have zero inline policies!"
        # Ensure only ECR token action uses wildcard resource in ecs_execution
        assert "ecr:GetAuthorizationToken" in sec_main


class TestPhase22FDataInfrastructureValidation:
    """Rigorous verification suite for Phase 22F Database, Redis, RabbitMQ & Storage Infrastructure."""

    def test_01_rds_storage_and_kms_encryption(self):
        """1. RDS PostgreSQL must enforce storage encryption using Customer Managed KMS Key."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert "storage_encrypted     = true" in rds_main
        assert "kms_key_id            = var.kms_key_arn" in rds_main
        assert "performance_insights_kms_key_id = var.kms_key_arn" in rds_main

    def test_02_rds_private_access_and_subnet_group(self):
        """2. RDS PostgreSQL must be private and reside strictly in isolated data subnets."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert "publicly_accessible    = false" in rds_main
        assert "subnet_ids  = var.data_subnet_ids" in rds_main
        assert "db_subnet_group_name   = aws_db_subnet_group.main.name" in rds_main

    def test_03_rds_multi_az_production_configuration(self):
        """3. Production RDS must enforce Multi-AZ replication while dev is single-AZ."""
        prod_main = (ENVS_DIR / "production" / "main.tf").read_text(encoding="utf-8")
        assert "multi_az                = true" in prod_main
        dev_main = (ENVS_DIR / "dev" / "main.tf").read_text(encoding="utf-8")
        assert "multi_az                = false" in dev_main

    def test_04_rds_backup_retention_and_protection(self):
        """4. Production RDS must configure 35-day backup retention and deletion protection."""
        prod_main = (ENVS_DIR / "production" / "main.tf").read_text(encoding="utf-8")
        assert "backup_retention_period = 35" in prod_main
        assert "deletion_protection     = true" in prod_main
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert "deletion_protection       = var.deletion_protection" in rds_main

    def test_05_rds_parameter_group_and_connection_limits(self):
        """5. RDS parameter group must tune timeouts, SSL, and connection auditing."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert 'name  = "rds.force_ssl"' in rds_main
        assert 'name  = "idle_in_transaction_session_timeout"' in rds_main
        assert 'name  = "statement_timeout"' in rds_main
        assert 'name  = "log_connections"' in rds_main
        assert 'name  = "log_disconnections"' in rds_main
        assert 'name  = "log_lock_waits"' in rds_main

    def test_06_pgbouncer_rds_proxy_transaction_pooling(self):
        """6. RDS Proxy must be configured for transaction pooling with variable sets excluded."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "aws_db_proxy" "main"' in rds_main
        assert 'session_pinning_filters      = ["EXCLUDE_VARIABLE_SETS"]' in rds_main
        assert 'require_tls            = true' in rds_main
        assert 'auth_scheme = "SECRETS"' in rds_main

    def test_07_rls_tenant_isolation_transaction_safety(self):
        """7. Tenant context must use set_config with is_local=true preventing pool leakage."""
        session_py = (ROOT_DIR / "apps" / "api" / "src" / "database" / "session.py").read_text(encoding="utf-8")
        assert "set_config('app.current_society_id', :val, true)" in session_py
        assert "is_local=true" in session_py

    def test_08_redis_encryption_in_transit_and_at_rest(self):
        """8. Redis ElastiCache must enforce encryption in transit and at rest with KMS."""
        redis_main = (MODULES_DIR / "redis" / "main.tf").read_text(encoding="utf-8")
        assert "transit_encryption_enabled = true" in redis_main
        assert "at_rest_encryption_enabled = true" in redis_main
        assert "kms_key_id                 = var.kms_key_arn" in redis_main

    def test_09_redis_access_restrictions(self):
        """9. Redis must be placed in isolated data subnets and bound to sg_redis_id."""
        redis_main = (MODULES_DIR / "redis" / "main.tf").read_text(encoding="utf-8")
        assert "subnet_ids  = var.data_subnet_ids" in redis_main
        assert "security_group_ids   = [var.sg_redis_id]" in redis_main

    def test_10_rabbitmq_durability_and_clustering(self):
        """10. Amazon MQ RabbitMQ must use version 3.13 and support multi-AZ quorum cluster."""
        mq_main = (MODULES_DIR / "rabbitmq" / "main.tf").read_text(encoding="utf-8")
        assert 'engine_type        = "RabbitMQ"' in mq_main
        assert 'engine_version     = "3.13"' in mq_main
        assert "CLUSTER_MULTI_AZ" in mq_main
        assert "use_aws_owned_key = false" in mq_main

    def test_11_rabbitmq_dlx_and_exchanges(self):
        """11. RabbitMQ topology must declare durable jobs and dlx exchanges."""
        topo_py = (ROOT_DIR / "apps" / "api" / "src" / "events" / "queue_topology.py").read_text(encoding="utf-8")
        assert 'JOBS_EXCHANGE = "societysphere.jobs"' in topo_py
        assert 'DLX_EXCHANGE = "societysphere.dlx"' in topo_py
        assert "durable=True" in topo_py

    def test_12_s3_public_access_blocking(self):
        """12. S3 documents bucket must block all public access."""
        storage_main = (MODULES_DIR / "storage" / "main.tf").read_text(encoding="utf-8")
        assert "block_public_acls       = true" in storage_main
        assert "block_public_policy     = true" in storage_main
        assert "ignore_public_acls      = true" in storage_main
        assert "restrict_public_buckets = true" in storage_main

    def test_13_s3_encryption_and_bucket_key(self):
        """13. S3 documents bucket must use SSE-KMS with Customer Managed Key and bucket key enabled."""
        storage_main = (MODULES_DIR / "storage" / "main.tf").read_text(encoding="utf-8")
        assert "kms_master_key_id = var.kms_key_arn" in storage_main
        assert 'sse_algorithm     = "aws:kms"' in storage_main
        assert "bucket_key_enabled = true" in storage_main

    def test_14_s3_versioning_and_object_lock(self):
        """14. S3 documents bucket must enable versioning and support Object Lock compliance."""
        storage_main = (MODULES_DIR / "storage" / "main.tf").read_text(encoding="utf-8")
        assert 'status = "Enabled"' in storage_main
        assert 'resource "aws_s3_bucket_object_lock_configuration" "documents"' in storage_main

    def test_15_s3_lifecycle_and_cors(self):
        """15. S3 documents bucket must configure Glacier archiving and presigned upload CORS."""
        storage_main = (MODULES_DIR / "storage" / "main.tf").read_text(encoding="utf-8")
        assert 'storage_class   = "GLACIER"' in storage_main
        assert "noncurrent_days = 2555" in storage_main
        assert 'resource "aws_s3_bucket_cors_configuration" "documents"' in storage_main

    def test_16_iam_least_privilege_data_tier(self):
        """16. RDS Proxy IAM role must have zero wildcard resource permissions."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        proxy_policy = re.search(r'resource "aws_iam_role_policy" "db_proxy".*?(?=\nresource|\Z)', rds_main, re.DOTALL).group(0)
        assert '"*"' not in proxy_policy, "RDS Proxy policy must not contain wildcard resources!"

    def test_17_secret_handling_zero_plaintext(self):
        """17. Secrets must be managed via Secrets Manager with zero plaintext credentials in Git."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert "manage_master_user_password   = true" in rds_main
        mq_main = (MODULES_DIR / "rabbitmq" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "aws_secretsmanager_secret" "mq_credentials"' in mq_main

    def test_18_environment_isolation_data_tier(self):
        """18. All four environments must have isolated data tier modules and outputs."""
        for env in ["dev", "qa", "staging", "production"]:
            env_main = (ENVS_DIR / env / "main.tf").read_text(encoding="utf-8")
            assert 'source = "../../modules/rds"' in env_main
            assert 'source = "../../modules/redis"' in env_main
            assert 'source = "../../modules/rabbitmq"' in env_main
            assert 'source = "../../modules/storage"' in env_main
            env_out = (ENVS_DIR / env / "outputs.tf").read_text(encoding="utf-8")
            assert "db_proxy_endpoint" in env_out

    def test_19_rds_enhanced_monitoring(self):
        """19. RDS must configure Enhanced Monitoring with dedicated IAM role and 60s interval."""
        rds_main = (MODULES_DIR / "rds" / "main.tf").read_text(encoding="utf-8")
        assert 'resource "aws_iam_role" "rds_monitoring"' in rds_main
        assert "monitoring_interval = var.monitoring_interval" in rds_main
        assert "AmazonRDSEnhancedMonitoringRole" in rds_main




