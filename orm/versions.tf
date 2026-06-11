terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 8.17" # pinned to match .terraform.lock.hcl (8.17.0) for reproducible init
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}
