locals {
  managed_tags = merge(
    {
      managed_by = "oci-zpr-visibility"
      purpose    = "zpr-observability"
    },
    var.freeform_tags
  )
  create_flow_log_connector      = var.create_log_analytics_connector && length(var.flow_log_targets) > 0
  create_zpr_inventory_connector = var.create_log_analytics_connector
}

resource "oci_zpr_configuration" "this" {
  count          = var.enable_zpr ? 1 : 0
  compartment_id = var.tenancy_ocid
  zpr_status     = "ENABLED"
  freeform_tags  = local.managed_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "oci_logging_log_group" "zpr_visibility" {
  compartment_id = var.compartment_ocid
  display_name   = "zpr-visibility"
  description    = "Central OCI Logging group for ZPR visibility flow logs and custom inventory records."
  freeform_tags  = local.managed_tags
}

resource "oci_logging_log" "flow_logs" {
  for_each     = var.flow_log_targets
  display_name = coalesce(each.value.display_name, "zpr-flow-${each.key}")
  log_group_id = oci_logging_log_group.zpr_visibility.id
  log_type     = "SERVICE"
  is_enabled   = true

  configuration {
    compartment_id = var.compartment_ocid

    source {
      category    = each.value.category
      resource    = each.value.resource_id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }

  retention_duration = var.logging_retention_days
  freeform_tags      = local.managed_tags
}

resource "oci_logging_log" "zpr_inventory" {
  display_name = "zpr-inventory"
  log_group_id = oci_logging_log_group.zpr_visibility.id
  log_type     = "CUSTOM"
  is_enabled   = true

  retention_duration = var.logging_retention_days
  freeform_tags      = local.managed_tags
}

resource "oci_sch_service_connector" "flow_logs_to_log_analytics" {
  count          = local.create_flow_log_connector ? 1 : 0
  compartment_id = var.compartment_ocid
  display_name   = "zpr-flow-logs-to-log-analytics"
  description    = "Routes OCI VCN Flow Logs from Logging to OCI Log Analytics for ZPR visibility dashboards."
  freeform_tags  = local.managed_tags

  source {
    kind = "logging"

    dynamic "log_sources" {
      for_each = oci_logging_log.flow_logs
      content {
        compartment_id = var.compartment_ocid
        log_group_id   = oci_logging_log_group.zpr_visibility.id
        log_id         = log_sources.value.id
      }
    }
  }

  target {
    kind                  = "loggingAnalytics"
    namespace             = var.log_analytics_namespace
    log_group_id          = var.log_analytics_log_group_ocid
    log_source_identifier = var.flow_log_analytics_source_identifier
  }

  lifecycle {
    precondition {
      condition     = !local.create_flow_log_connector || (var.log_analytics_namespace != null && var.log_analytics_log_group_ocid != null)
      error_message = "log_analytics_namespace and log_analytics_log_group_ocid are required when create_log_analytics_connector is true."
    }
  }
}

resource "oci_sch_service_connector" "zpr_inventory_to_log_analytics" {
  count          = local.create_zpr_inventory_connector ? 1 : 0
  compartment_id = var.compartment_ocid
  display_name   = "zpr-inventory-to-log-analytics"
  description    = "Routes custom ZPR inventory, relationship, and finding records from OCI Logging to OCI Log Analytics."
  freeform_tags  = local.managed_tags

  source {
    kind = "logging"

    log_sources {
      compartment_id = var.compartment_ocid
      log_group_id   = oci_logging_log_group.zpr_visibility.id
      log_id         = oci_logging_log.zpr_inventory.id
    }
  }

  target {
    kind                  = "loggingAnalytics"
    namespace             = var.log_analytics_namespace
    log_group_id          = var.log_analytics_log_group_ocid
    log_source_identifier = var.zpr_inventory_log_analytics_source_identifier
  }

  lifecycle {
    precondition {
      condition     = !local.create_zpr_inventory_connector || (var.log_analytics_namespace != null && var.log_analytics_log_group_ocid != null)
      error_message = "log_analytics_namespace and log_analytics_log_group_ocid are required when create_log_analytics_connector is true."
    }
  }
}
