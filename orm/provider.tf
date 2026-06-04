# Resource Manager injects credentials at runtime (config_file_profile stays null).
# For local terraform runs, pass -var config_file_profile=<profile>.
provider "oci" {
  region              = var.region
  config_file_profile = var.config_file_profile
}
