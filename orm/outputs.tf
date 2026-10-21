output "vcn_ocid" { value = local.observed_vcn_id }
output "endpoints_subnet_ocid" { value = local.enable_lab ? oci_core_subnet.endpoints[0].id : null }
output "flow_log_group_ocid" { value = local.flow_log_group_id }
output "flow_log_ocid" { value = local.flow_log_id }
output "state_bucket" { value = oci_objectstorage_bucket.state.name }
output "zpr_policy_ocid" { value = local.enable_lab ? oci_zpr_zpr_policy.demo[0].id : null }
output "controller_public_ip" {
  value = local.enable_controller ? oci_core_instance.controller[0].public_ip : null
}
output "function_app_ocid" {
  value = local.enable_function ? oci_functions_application.refresh[0].id : null
}
output "function_ocid" {
  value = local.enable_function && var.function_image != "" ? oci_functions_function.refresh[0].id : null
}
output "deployment_mode" { value = var.deployment_mode }
output "web_ip" { value = local.enable_lab ? "10.20.1.10" : null }
output "db_ip" { value = local.enable_lab ? "10.20.1.20" : null }
