output "vcn_ocid" { value = oci_core_vcn.lab.id }
output "endpoints_subnet_ocid" { value = oci_core_subnet.endpoints.id }
output "flow_log_group_ocid" { value = oci_logging_log_group.flow.id }
output "flow_log_ocid" { value = oci_logging_log.subnet_flow.id }
output "state_bucket" { value = oci_objectstorage_bucket.state.name }
output "zpr_policy_ocid" { value = oci_zpr_zpr_policy.demo.id }
output "controller_public_ip" {
  value = var.enable_controller ? oci_core_instance.controller[0].public_ip : null
}
output "web_ip" { value = "10.20.1.10" }
output "db_ip" { value = "10.20.1.20" }
