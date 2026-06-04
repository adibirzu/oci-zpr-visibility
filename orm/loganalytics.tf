# Log Analytics ingestion target. Fields/parser/source + dashboard are created by
# the controller (or the documented post-apply command), not Terraform.
resource "oci_log_analytics_log_analytics_log_group" "la" {
  count          = 0 # placeholder: provision-la creates the LA log group idempotently
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  compartment_id = var.compartment_ocid
  display_name   = "${local.name_prefix}-la"
}
