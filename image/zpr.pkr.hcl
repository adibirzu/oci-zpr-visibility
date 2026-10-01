packer {
  required_plugins {
    oracle = {
      version = "= 1.1.2"
      source  = "github.com/hashicorp/oracle"
    }
  }
}

variable "profile" { type = string }
variable "availability_domain" { type = string }
variable "compartment_ocid" { type = string }
variable "base_image_ocid" { type = string }
variable "subnet_ocid" { type = string }
variable "image_name" { type = string }
variable "bundle_path" { type = string }

source "oracle-oci" "zpr" {
  access_cfg_file_account = var.profile
  availability_domain    = var.availability_domain
  compartment_ocid       = var.compartment_ocid
  base_image_ocid        = var.base_image_ocid
  subnet_ocid            = var.subnet_ocid
  image_name             = var.image_name
  image_compartment_ocid = var.compartment_ocid
  shape                  = "VM.Standard.E3.Flex"
  shape_config {
    ocpus         = 1
    memory_in_gbs = 8
  }
  ssh_username = "opc"
  use_private_ip = true
  instance_options_are_legacy_imds_endpoints_disabled = true
  create_vnic_details {
    assign_public_ip = false
  }
}

build {
  sources = ["source.oracle-oci.zpr"]
  provisioner "file" {
    source      = var.bundle_path
    destination = "/tmp/zpr-bundle"
  }
  provisioner "shell" {
    script          = "${path.root}/install.sh"
    execute_command = "sudo -n bash '{{ .Path }}'"
  }
  post-processor "manifest" {
    output     = "image-manifest.json"
    strip_path = true
  }
}
