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
variable "enable_controller" {
  type        = bool
  default     = true
  description = "Create the controller VM that auto-provisions LA content + dashboard."
}

locals {
  name_prefix = "zpr-visibility"
  common_tags = { project = "oci-zpr-visibility", lab = "zpr-demo" }
}
