# Notifications + Monitoring alarms on the zpr_visibility custom metrics that
# `oci-zpr-visibility refresh` publishes (see oci_zpr_visibility/metrics.py).
# Gated by create_alarms (default false). Set alarm_notification_email to
# subscribe an inbox; confirm the OCI subscription email to receive alerts.

variable "create_alarms" {
  description = "Create the Notifications topic + Monitoring alarms on zpr_visibility metrics."
  type        = bool
  default     = false
}

variable "alarm_notification_email" {
  description = "Email to subscribe to ZPR alerts (optional)."
  type        = string
  default     = null
}

resource "oci_ons_notification_topic" "zpr" {
  count          = var.create_alarms ? 1 : 0
  compartment_id = var.compartment_ocid
  name           = "zpr-visibility-alerts"
  description    = "Alerts for ZPR visibility findings and risky flows."
  freeform_tags  = local.managed_tags
}

resource "oci_ons_subscription" "email" {
  count          = var.create_alarms && var.alarm_notification_email != null ? 1 : 0
  compartment_id = var.compartment_ocid
  topic_id       = oci_ons_notification_topic.zpr[0].id
  protocol       = "EMAIL"
  endpoint       = var.alarm_notification_email
}

locals {
  zpr_alarms = var.create_alarms ? {
    critical_high_findings = {
      query    = "findings_critical_high[5m].max() > 0"
      severity = "CRITICAL"
      body     = "ZPR: CRITICAL/HIGH findings detected in the latest run."
    }
    accepted_requires_policy_review = {
      query    = "flows_accepted_requires_policy_review[5m].max() > 0"
      severity = "WARNING"
      body     = "ZPR visibility: VCN Flow Log ACCEPT records require policy review; this is inferred evidence, not a provider enforcement verdict."
    }
    rejected_policy_expected_allow = {
      query    = "flows_rejected_policy_expected_allow[5m].max() > 0"
      severity = "WARNING"
      body     = "ZPR visibility: VCN Flow Log REJECT records overlap parsed allow intent and require review; this is inferred evidence."
    }
    missing_heartbeat = {
      query    = "heartbeat[1h].count() < 1"
      severity = "CRITICAL"
      body     = "ZPR: visibility refresh heartbeat missing for 1h (collector may be down)."
    }
    collection_errors = {
      query    = "collection_errors[5m].max() > 0"
      severity = "WARNING"
      body     = "ZPR: one or more inventory collection operations failed; review the collection-health dashboard."
    }
  } : {}
}

resource "oci_monitoring_alarm" "zpr" {
  for_each              = local.zpr_alarms
  compartment_id        = var.compartment_ocid
  metric_compartment_id = var.compartment_ocid
  namespace             = "zpr_visibility"
  display_name          = "zpr-${each.key}"
  query                 = each.value.query
  severity              = each.value.severity
  body                  = each.value.body
  destinations          = [oci_ons_notification_topic.zpr[0].id]
  is_enabled            = true
  pending_duration      = "PT5M"
  message_format        = "ONS_OPTIMIZED"
  freeform_tags         = local.managed_tags
}

output "alarm_topic_ocid" {
  description = "Notifications topic OCID for ZPR alerts (null when create_alarms=false)."
  value       = try(oci_ons_notification_topic.zpr[0].id, null)
}
