# Controller VM: bootstraps Log Analytics content + dashboard via instance
# principal, then keeps a 15-min refresh cron. Scoped IAM via a dynamic group
# matching exactly this instance.

resource "oci_core_instance" "controller" {
  count               = local.enable_controller ? 1 : 0
  depends_on          = [terraform_data.existing_flow_scope]
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "${local.name_prefix}-controller"
  shape               = var.instance_shape
  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }
  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid
  }
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  agent_config {
    plugins_config {
      name          = "Compute Instance Run Command"
      desired_state = "ENABLED"
    }
    plugins_config {
      name          = "Management Agent"
      desired_state = "ENABLED"
    }
  }
  create_vnic_details {
    subnet_id        = local.controller_subnet_id
    assign_public_ip = local.controller_assign_public_ip
  }
  metadata = merge(
    {
      user_data = base64encode(templatefile("${path.module}/cloudinit/controller.sh.tftpl", {
        region                   = var.region
        log_group_name           = "${local.name_prefix}-la"
        log_group_compartment_id = var.compartment_ocid
        dashboard_compartment_id = var.compartment_ocid
        state_bucket             = oci_objectstorage_bucket.state.name
        pkg_bucket               = oci_objectstorage_bucket.pkg[0].name
        pkg_object               = oci_objectstorage_object.pkg[0].object
        pkg_sha256               = filesha256(var.package_tarball_path)
        bootstrap_requirements   = file("${path.module}/bootstrap-requirements.txt")
        flow_compartment_id      = local.observation_compartment_id
        flow_log_group_id        = local.flow_log_group_id
        flow_log_id              = local.flow_log_id
        flow_vcn_id              = local.observed_vcn_id
        refresh_config_b64 = base64encode(jsonencode({
          region                   = var.region
          state_bucket             = oci_objectstorage_bucket.state.name
          log_group_name           = "${local.name_prefix}-la"
          compartment_ids          = local.observation_compartment_ids
          flow_compartment_id      = local.observation_compartment_id
          log_group_compartment_id = var.compartment_ocid
          flow_log_group_id        = local.flow_log_group_id
          flow_log_id              = local.flow_log_id
          flow_vcn_id              = local.observed_vcn_id
        }))
      }))
    },
    var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key },
  )
  freeform_tags = merge(local.common_tags, { role = "controller" })
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
  description    = "Least-privilege grants for the ZPR visibility controller (instance principal)."
  statements = [
    for g in local.refresh_grants :
    "Allow dynamic-group ${oci_identity_dynamic_group.controller[0].name} to ${g.perm} in ${g.scope}"
  ]
}
