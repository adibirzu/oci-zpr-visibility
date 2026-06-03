variable "region" {
  description = "OCI region where Logging and Connector Hub resources are created."
  type        = string
}

variable "auth" {
  description = "OCI Terraform provider auth mode: APIKey, InstancePrincipal, ResourcePrincipal, SecurityToken, or OkeWorkloadIdentity."
  type        = string
  default     = "APIKey"
}

variable "config_file_profile" {
  description = "OCI CLI config profile used when auth is APIKey or SecurityToken."
  type        = string
  default     = "DEFAULT"
}

variable "tenancy_ocid" {
  description = "Root tenancy OCID. Used to enable ZPR in the root compartment."
  type        = string
  sensitive   = true
}

variable "compartment_ocid" {
  description = "Compartment OCID for the central Logging and Connector Hub resources."
  type        = string
  sensitive   = true
}

variable "enable_zpr" {
  description = "Create the tenancy-level ZPR configuration in ENABLED state."
  type        = bool
  default     = true
}

variable "flow_log_targets" {
  description = "VCN Flow Log enablement targets. category must be vcn, subnet, vnic, or all."
  type = map(object({
    resource_id  = string
    category     = string
    display_name = optional(string)
  }))
  default = {}

  validation {
    condition = alltrue([
      for target in values(var.flow_log_targets) : contains(["vcn", "subnet", "vnic", "all"], target.category)
    ])
    error_message = "Each flow_log_targets entry must use category vcn, subnet, vnic, or all."
  }
}

variable "logging_retention_days" {
  description = "OCI Logging retention in days. OCI supports 30-day increments."
  type        = number
  default     = 90
}

variable "create_log_analytics_connector" {
  description = "Create a Service Connector from OCI Logging to OCI Log Analytics."
  type        = bool
  default     = true
}

variable "log_analytics_namespace" {
  description = "OCI Log Analytics namespace."
  type        = string
  default     = null
}

variable "log_analytics_log_group_ocid" {
  description = "Target OCI Log Analytics log group OCID."
  type        = string
  default     = null
  sensitive   = true
}

variable "flow_log_analytics_source_identifier" {
  description = "Log Analytics source identifier for OCI VCN Flow Logs."
  type        = string
  default     = "OCI VCN Flow Unified Schema Logs"
}

variable "zpr_inventory_log_analytics_source_identifier" {
  description = "Log Analytics source identifier for custom ZPR inventory JSON records."
  type        = string
  default     = "OCI ZPR Visibility JSON"
}

variable "freeform_tags" {
  description = "Freeform tags applied to managed resources."
  type        = map(string)
  default     = {}
}
