# Controller VM: bootstraps Log Analytics content + dashboard via instance
# principal, then keeps a supervised 15-min refresh timer. Scoped IAM via a dynamic group
# matching exactly this instance.

resource "oci_core_instance" "controller" {
  count               = local.enable_controller ? 1 : 0
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "${local.name_prefix}-controller"
  shape               = "VM.Standard.E3.Flex"
  shape_config {
    ocpus         = 1
    memory_in_gbs = 8
  }
  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid
  }
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.controller.id
    assign_public_ip = false
  }
  metadata = merge(
    {
      user_data = base64encode(templatefile("${path.module}/cloudinit/controller.sh.tftpl", {
        region              = var.region
        log_group_name      = "${local.name_prefix}-owned-la"
        state_bucket        = oci_objectstorage_bucket.state.name
        pkg_bucket          = oci_objectstorage_bucket.pkg[0].name
        pkg_object          = oci_objectstorage_object.pkg[0].object
        flow_compartment_id = var.compartment_ocid
        flow_log_group_id   = oci_logging_log_group.flow.id
        flow_log_id         = oci_logging_log.subnet_flow.id
        package_sha256      = filesha256(var.package_tarball_path)
        runtime_lock        = base64encode(file("${path.module}/requirements-runtime.lock"))
        runtime_config = base64encode(jsonencode({
          region          = var.region, compartment_id = var.compartment_ocid,
          installation_id = var.installation_id, state_bucket = oci_objectstorage_bucket.state.name,
          log_group_name  = "${local.name_prefix}-owned-la", flow_log_group_id = oci_logging_log_group.flow.id,
          flow_log_id     = oci_logging_log.subnet_flow.id
        }))
      }))
    },
    var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key },
  )
  freeform_tags = merge(local.common_tags, { role = "controller", "zpr-installation" = var.installation_id })
  agent_config {
    plugins_config {
      name          = "Compute Instance Run Command"
      desired_state = "ENABLED"
    }
  }
  # User-data runs only on first boot. Changed collector bytes must replace
  # this stateless controller, not silently update metadata on a failed VM.
  # The deterministic archive avoids replacements for identical source.
  lifecycle {
    replace_triggered_by = [oci_objectstorage_object.pkg[0]]
  }
}

resource "oci_identity_dynamic_group" "controller" {
  count          = local.enable_controller ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-controller-dg"
  description    = "ZPR visibility controller instance"
  matching_rule  = "ALL {instance.id = '${oci_core_instance.controller[0].id}'}"
}

resource "oci_identity_policy" "controller" {
  count          = local.enable_controller ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-controller-policy"
  description    = "Scoped collection plus LA content bootstrap/cleanup grants for the controller."
  statements = concat([
    for g in local.refresh_grants :
    "Allow dynamic-group ${oci_identity_dynamic_group.controller[0].name} to ${g.perm} in ${g.scope}"
    ], [
    "Allow dynamic-group ${oci_identity_dynamic_group.controller[0].name} to use instance-agent-command-execution-family in compartment id ${var.compartment_ocid} where request.instance.id=target.instance.id"
  ])
}
