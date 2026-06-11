variable "tenancy_ocid" { type = string }
variable "compartment_ocid" {
  type        = string
  description = "Compartment for the lab resources (root tenancy is fine)."
}
variable "region" { type = string }

variable "config_file_profile" {
  type    = string
  default = null
}

variable "availability_domain" {
  type        = string
  description = "AD for the lab instances."
}
variable "instance_image_ocid" {
  type        = string
  description = "Oracle Linux 9 image OCID for VM.Standard.E3.Flex in this region."
}
variable "ssh_public_key" {
  type        = string
  default     = ""
  description = "Optional SSH public key for the lab instances."
}
variable "package_tarball_path" {
  type        = string
  default     = "oci_zpr_visibility_pkg.tgz"
  description = "Path (in the stack zip) to the collector package tarball uploaded for the controller."
}
variable "deployment_mode" {
  type        = string
  default     = "controller_vm"
  description = "Autonomy mode for the refresh unit: 'controller_vm' (small VM + built-in 15-min cron, instance principal) or 'function' (serverless OCI Function, resource principal)."
  validation {
    condition     = contains(["controller_vm", "function"], var.deployment_mode)
    error_message = "deployment_mode must be either 'controller_vm' or 'function'."
  }
}

variable "function_image" {
  type        = string
  default     = ""
  description = "OCIR image for the refresh function (e.g. <region>.ocir.io/<namespace>/zpr-visibility-refresh:0.0.1), built and pushed with 'fn deploy'. Terraform cannot build Docker images; the function resource is created only once this is supplied. The Functions application + IAM are created regardless when deployment_mode = function."
}

locals {
  name_prefix = "zpr-visibility"
  common_tags = { project = "oci-zpr-visibility", lab = "zpr-demo" }

  enable_controller = var.deployment_mode == "controller_vm"
  enable_function   = var.deployment_mode == "function"

  # Least-privilege grants shared by both the controller VM dynamic group and the
  # function dynamic group. Replaces the old "manage all-resources" lab grant.
  # Verb+target are scoped per the OCI service the collector actually calls; object
  # access is narrowed to the lab compartment.
  # Minimal statement count (policy-statement budget is tenancy-hierarchy-wide and
  # can be scarce). The single "read all-resources" covers the collector's reads
  # (zpr-policy, security-attribute-namespaces, virtual-network-family,
  # instance-family, compartments, buckets); manage verbs are kept narrow.
  refresh_grants = [
    { perm = "manage loganalytics-features-family", scope = "tenancy" },
    { perm = "manage management-dashboard-family", scope = "tenancy" },
    { perm = "read all-resources", scope = "tenancy" },
    { perm = "use metrics", scope = "tenancy" },
    { perm = "manage objects", scope = "compartment id ${var.compartment_ocid}" },
  ]
}
