# Controller VM: bootstraps Log Analytics content + dashboard via instance
# principal, then keeps a 15-min refresh cron. Scoped IAM via a dynamic group
# matching exactly this instance.

resource "oci_core_instance" "controller" {
  count               = var.enable_controller ? 1 : 0
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
  create_vnic_details {
    subnet_id        = oci_core_subnet.controller.id
    assign_public_ip = true
  }
  metadata = merge(
    {
      user_data = base64encode(templatefile("${path.module}/cloudinit/controller.sh.tftpl", {
        region         = var.region
        log_group_name = "${local.name_prefix}-la"
        state_bucket   = oci_objectstorage_bucket.state.name
        pkg_bucket     = oci_objectstorage_bucket.pkg[0].name
        pkg_object     = oci_objectstorage_object.pkg[0].object
      }))
    },
    var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key },
  )
  freeform_tags = merge(local.common_tags, { role = "controller" })
}

resource "oci_identity_dynamic_group" "controller" {
  count          = var.enable_controller ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-controller-dg"
  description    = "ZPR visibility controller instance"
  matching_rule  = "ALL {instance.id = '${oci_core_instance.controller[0].id}'}"
}

resource "oci_identity_policy" "controller" {
  count          = var.enable_controller ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-controller-policy"
  description    = "Grants the ZPR visibility controller the access it needs"
  # Lab grant: broad but valid. For production, scope to:
  #   manage loganalytics-features-family, manage management-dashboard-family,
  #   read zpr-policy, read security-attribute-namespaces, read virtual-network-family,
  #   read instance-family, read compartments, manage objects (state/pkg buckets), use metrics.
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.controller[0].name} to manage all-resources in tenancy",
  ]
}
