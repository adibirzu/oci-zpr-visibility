variable "tenancy_ocid" { type = string }
variable "compartment_ocid" {
  type        = string
  description = "Compartment for the lab resources (root tenancy is fine)."
}
variable "region" { type = string }
variable "installation_id" {
  type        = string
  default     = "zpr-visibility"
  description = "Stable installation identifier retained for upgrade compatibility."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,39}$", var.installation_id))
    error_message = "Use 3-40 lowercase letters, digits and hyphens."
  }
}

variable "name_prefix" {
  type        = string
  default     = "zpr-visibility"
  description = "Display-name alias for installation_id. The default preserves upgrades with a customized installation_id."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,39}$", var.name_prefix))
    error_message = "name_prefix must be 3-40 lower-case letters, digits or hyphens and begin with a letter."
  }
}

variable "vcn_cidr_block" {
  type        = string
  default     = "10.20.0.0/16"
  description = "Non-overlapping IPv4 CIDR reserved for the isolated ZPR lab VCN. Ignored in existing-network mode."
  validation {
    condition     = can(cidrnetmask(var.vcn_cidr_block)) && can(regex("/(16|17|18|19|20|21|22)$", var.vcn_cidr_block)) && can(cidrsubnet(var.vcn_cidr_block, 24 - tonumber(split("/", var.vcn_cidr_block)[1]), 2))
    error_message = "vcn_cidr_block must be a valid IPv4 network between /16 and /22, with room for the derived /24 subnets."
  }
}

variable "network_mode" {
  type        = string
  default     = "lab"
  description = "Network ownership mode. lab creates the demo VCN and endpoints; existing observes a supplied VCN/subnet and flow log without managing them."
  validation {
    condition     = contains(["lab", "existing"], var.network_mode)
    error_message = "network_mode must be either 'lab' or 'existing'."
  }
}

variable "existing_vcn_ocid" {
  type        = string
  default     = null
  description = "Existing VCN OCID used when network_mode = existing."
}
variable "existing_controller_subnet_ocid" {
  type        = string
  default     = null
  description = "Existing subnet OCID for the observer controller or function when network_mode = existing."
}
variable "existing_flow_log_group_ocid" {
  type        = string
  default     = null
  description = "Existing OCI Logging log group OCID containing the selected flow log."
}
variable "existing_flow_log_ocid" {
  type        = string
  default     = null
  description = "Existing OCI Logging service log OCID to observe."
}
variable "observation_compartment_ocid" {
  type        = string
  default     = null
  description = "Compartment containing the existing flow-log group/log. Defaults to the deployment compartment."
}
variable "collection_compartment_ocids" {
  type        = list(string)
  default     = null
  description = "Exact non-empty compartment OCIDs the observer may collect. Omit the value for mode defaults."
  validation {
    condition     = var.collection_compartment_ocids == null ? true : (length(var.collection_compartment_ocids) > 0 && alltrue([for compartment_id in var.collection_compartment_ocids : try(trimspace(compartment_id) != "", false)]))
    error_message = "collection_compartment_ocids must be omitted for defaults or contain at least one non-blank compartment OCID."
  }
}
variable "controller_assign_public_ip" {
  type        = bool
  default     = null
  description = "Assign a public IP to the controller. Defaults to true for lab mode and false for existing mode."
}

variable "config_file_profile" {
  type    = string
  default = null
}

variable "availability_domain" {
  type        = string
  description = "AD for the lab instances."
}
variable "instance_shape" {
  type        = string
  default     = "VM.Standard.E3.Flex"
  description = "OCI Flex shape for lab endpoints and the observer controller."
  validation {
    condition     = can(regex("^[A-Za-z0-9.]+\\.Flex$", var.instance_shape))
    error_message = "instance_shape must be an OCI Flex shape."
  }
}
variable "instance_ocpus" {
  type        = number
  default     = 1
  description = "OCPUs for each lab endpoint and the observer controller."
  validation {
    condition     = var.instance_ocpus >= 1
    error_message = "instance_ocpus must be at least 1."
  }
}
variable "instance_memory_gbs" {
  type        = number
  default     = 8
  description = "Memory in GB for each lab endpoint and the observer controller."
  validation {
    condition     = var.instance_memory_gbs >= 1
    error_message = "instance_memory_gbs must be at least 1 GB."
  }
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
  description = "OCIR image for the refresh function (e.g. <region>.ocir.io/<namespace>/zpr-visibility-refresh:0.0.1), built and pushed with 'fn deploy'. Terraform cannot build Docker images; the function resource is created only once this is supplied. The Functions application is created in function mode; IAM grants match only the Terraform-managed Function and are created once its image is supplied."
}

locals {
  # Both inputs retain the historic default. A legacy stack with only a
  # customized installation_id keeps that identity when name_prefix is new.
  name_prefix = var.name_prefix == "zpr-visibility" && var.installation_id != "zpr-visibility" ? var.installation_id : var.name_prefix
  common_tags = { project = "oci-zpr-visibility", lab = "zpr-demo" }

  endpoint_subnet_cidr   = cidrsubnet(var.vcn_cidr_block, 24 - tonumber(split("/", var.vcn_cidr_block)[1]), 1)
  controller_subnet_cidr = cidrsubnet(var.vcn_cidr_block, 24 - tonumber(split("/", var.vcn_cidr_block)[1]), 2)

  enable_controller           = var.deployment_mode == "controller_vm"
  enable_function             = var.deployment_mode == "function"
  enable_lab                  = var.network_mode == "lab"
  enable_existing             = var.network_mode == "existing"
  observation_compartment_id  = coalesce(var.observation_compartment_ocid, var.compartment_ocid)
  observation_compartment_ids = var.collection_compartment_ocids != null ? distinct(var.collection_compartment_ocids) : distinct(local.enable_existing ? [var.compartment_ocid, local.observation_compartment_id] : [var.compartment_ocid])
  controller_assign_public_ip = var.controller_assign_public_ip != null ? var.controller_assign_public_ip : local.enable_lab

  controller_subnet_id = local.enable_existing ? data.oci_core_subnet.existing[0].id : oci_core_subnet.controller[0].id
  observed_vcn_id      = local.enable_existing ? data.oci_core_vcn.existing[0].id : oci_core_vcn.lab[0].id
  flow_log_group_id    = local.enable_existing ? (var.existing_flow_log_group_ocid == null ? "" : var.existing_flow_log_group_ocid) : oci_logging_log_group.flow[0].id
  flow_log_id          = local.enable_existing ? (var.existing_flow_log_ocid == null ? "" : var.existing_flow_log_ocid) : oci_logging_log.subnet_flow[0].id

  validate_existing_flow = local.enable_existing && local.flow_log_id != "" && local.flow_log_group_id != ""

  # Least-privilege grants shared by both the controller VM dynamic group and the
  # function dynamic group. Replaces the old "manage all-resources" lab grant.
  # Verb+target are scoped per the OCI service the collector actually calls; object
  # access is narrowed to the lab compartment.
  # Minimal statement count (policy-statement budget is tenancy-hierarchy-wide and
  # can be scarce). The single "read all-resources" covers the collector's reads
  # (zpr-policy, security-attribute-namespaces, virtual-network-family,
  # instance-family, compartments, buckets); manage verbs are kept narrow.
  refresh_grants = concat(
    [
      { perm = "manage loganalytics-features-family", scope = "tenancy" },
      { perm = "manage management-dashboard-family", scope = "compartment id ${var.compartment_ocid}" },
      { perm = "read zpr-family", scope = "tenancy" },
      { perm = "read security-attribute-namespaces", scope = "tenancy" },
      { perm = "use metrics", scope = "compartment id ${var.compartment_ocid}" },
      { perm = "manage objects", scope = "compartment id ${var.compartment_ocid} where any {target.bucket.name='${local.name_prefix}-state',target.bucket.name='${local.name_prefix}-pkg'}" },
    ],
    [
      for compartment_id in local.observation_compartment_ids : {
        perm  = "read all-resources"
        scope = "compartment id ${compartment_id}"
      }
    ],
    local.enable_lab || local.validate_existing_flow ? [
      { perm = "read log-groups", scope = "compartment id ${local.observation_compartment_id}" },
      { perm = "read log-content", scope = "compartment id ${local.observation_compartment_id}" },
    ] : [],
  )
}
