output "logging_log_group_ocid" {
  description = "Central OCI Logging log group OCID."
  value       = oci_logging_log_group.zpr_visibility.id
}

output "flow_log_ocids" {
  description = "OCI Logging service log OCIDs for VCN Flow Logs."
  value       = { for key, log in oci_logging_log.flow_logs : key => log.id }
}

output "zpr_inventory_custom_log_ocid" {
  description = "OCI custom log OCID used by the Python collector to emit ZPR inventory and findings records."
  value       = oci_logging_log.zpr_inventory.id
}

output "flow_logs_service_connector_ocid" {
  description = "Service Connector Hub connector OCID for flow logs to Log Analytics."
  value       = try(oci_sch_service_connector.flow_logs_to_log_analytics[0].id, null)
}

output "zpr_inventory_service_connector_ocid" {
  description = "Service Connector Hub connector OCID for custom ZPR inventory logs to Log Analytics."
  value       = try(oci_sch_service_connector.zpr_inventory_to_log_analytics[0].id, null)
}
