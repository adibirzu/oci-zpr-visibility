# Object Storage: drift-state bucket + a bucket holding the collector package
# tarball the controller installs.
data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.tenancy_ocid
}

resource "oci_objectstorage_bucket" "state" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${local.name_prefix}-state"
  freeform_tags  = merge(local.common_tags, { "zpr-installation" = var.installation_id })
}

resource "oci_objectstorage_bucket" "pkg" {
  count          = local.enable_controller ? 1 : 0
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${local.name_prefix}-pkg"
  freeform_tags  = local.common_tags
}

resource "terraform_data" "collector_revision" {
  count = local.enable_controller ? 1 : 0
  triggers_replace = {
    package   = filesha256(var.package_tarball_path)
    bootstrap = filesha256("${path.module}/cloudinit/controller.sh.tftpl")
  }
}

resource "oci_objectstorage_object" "pkg" {
  count        = local.enable_controller ? 1 : 0
  namespace    = data.oci_objectstorage_namespace.ns.namespace
  bucket       = oci_objectstorage_bucket.pkg[0].name
  object       = "oci_zpr_visibility_pkg.tgz"
  source       = var.package_tarball_path
  content_type = "application/gzip"
  lifecycle {
    # Stable archive mtime avoids provider timestamp churn; hashes still
    # force a real upload/rebootstrap whenever content changes.
    replace_triggered_by = [terraform_data.collector_revision[0]]
  }
}
