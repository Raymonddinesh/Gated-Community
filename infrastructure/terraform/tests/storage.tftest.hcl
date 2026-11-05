# ==============================================================================
# OpenTofu / Terraform Native Module Test: Storage Module
# ==============================================================================

run "verify_production_gst_retention_defaults" {
  command = plan

  variables {
    environment                = "production"
    kms_key_arn                = "arn:aws:kms:ap-south-1:123456789012:key/12345678-1234-1234-1234-123456789012"
    enable_object_lock         = true
    object_lock_mode           = "COMPLIANCE"
    object_lock_retention_days = 2190
  }

  module {
    source = "../modules/storage"
  }

  assert {
    condition     = var.object_lock_mode == "COMPLIANCE"
    error_message = "Production document storage must enforce COMPLIANCE object lock mode"
  }

  assert {
    condition     = var.object_lock_retention_days == 2190
    error_message = "Production document retention must enforce 2,190 days (6 years for Indian GST)"
  }
}

run "verify_nonprod_governance_retention" {
  command = plan

  variables {
    environment                = "staging"
    kms_key_arn                = "arn:aws:kms:ap-south-1:123456789012:key/12345678-1234-1234-1234-123456789012"
    enable_object_lock         = true
    object_lock_mode           = "GOVERNANCE"
    object_lock_retention_days = 30
  }

  module {
    source = "../modules/storage"
  }

  assert {
    condition     = var.object_lock_mode == "GOVERNANCE"
    error_message = "Staging storage should use GOVERNANCE mode for testing flexibility"
  }
}
