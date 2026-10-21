# Serverless deployment mode (deployment_mode = "function").
#
# The same `refresh` unit the controller VM runs on a cron also runs as an OCI
# Function under a **resource principal** (no instance, no API keys). Terraform
# cannot build/push the Docker image — that is `fn deploy` from functions/ — so:
#   * the Functions application + resource-principal IAM are always created in
#     function mode; principal grants exist only for the exact Terraform function, and
#   * the function resource itself is created only once var.function_image points
#     at the pushed OCIR image.
#
# There is no native cron-for-Functions in core OCI; invoke it from Events,
# Connector Hub, API Gateway, or a scheduler you operate. See docs/deployment-modes.md.

resource "oci_functions_application" "refresh" {
  depends_on     = [terraform_data.existing_flow_scope]
  count          = local.enable_function ? 1 : 0
  compartment_id = var.compartment_ocid
  display_name   = "${local.name_prefix}-fn-app"
  subnet_ids     = [local.controller_subnet_id]
  config = {
    STATE_BUCKET               = oci_objectstorage_bucket.state.name
    REGION                     = var.region
    LOG_GROUP_NAME             = "${local.name_prefix}-la"
    LOG_GROUP_COMPARTMENT_ID   = var.compartment_ocid
    FLOW_LOG_COMPARTMENT_ID    = local.observation_compartment_id
    FLOW_LOG_GROUP_ID          = local.flow_log_group_id
    FLOW_LOG_ID                = local.flow_log_id
    FLOW_VCN_ID                = local.observed_vcn_id
    COLLECTION_COMPARTMENT_IDS = jsonencode(local.observation_compartment_ids)
  }
  freeform_tags = local.common_tags
}

resource "oci_functions_function" "refresh" {
  count              = local.enable_function && var.function_image != "" ? 1 : 0
  application_id     = oci_functions_application.refresh[0].id
  display_name       = "${local.name_prefix}-refresh"
  image              = var.function_image
  memory_in_mbs      = 1024
  timeout_in_seconds = 300
  freeform_tags      = local.common_tags
}

resource "oci_identity_dynamic_group" "function" {
  count          = local.enable_function && var.function_image != "" ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-fn-dg"
  description    = "ZPR visibility refresh function (resource principal)"
  matching_rule  = "ALL {resource.type = 'fnfunc', resource.id = '${oci_functions_function.refresh[0].id}'}"
}

resource "oci_identity_policy" "function" {
  count          = local.enable_function && var.function_image != "" ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-fn-policy"
  description    = "Least-privilege grants for the ZPR visibility refresh function (resource principal)."
  statements = [
    for g in local.refresh_grants :
    "Allow dynamic-group ${oci_identity_dynamic_group.function[0].name} to ${g.perm} in ${g.scope}"
  ]
}
