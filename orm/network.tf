# Network: lab-owned VCN/subnets/flow log, or read-only references to an
# existing VCN and controller subnet. Existing mode never updates the VCN.

resource "terraform_data" "existing_inputs" {
  count = local.enable_existing ? 1 : 0

  lifecycle {
    precondition {
      condition = alltrue([
        var.existing_vcn_ocid != null && var.existing_vcn_ocid != "",
        var.existing_controller_subnet_ocid != null && var.existing_controller_subnet_ocid != "",
        (var.existing_flow_log_group_ocid == null || var.existing_flow_log_group_ocid == "") == (var.existing_flow_log_ocid == null || var.existing_flow_log_ocid == ""),
      ])
      error_message = "existing mode requires VCN and controller subnet OCIDs; optional flow-log group and log OCIDs must be supplied together."
    }
  }
}

data "oci_core_vcn" "existing" {
  count      = local.enable_existing ? 1 : 0
  vcn_id     = var.existing_vcn_ocid
  depends_on = [terraform_data.existing_inputs]
}

data "oci_core_subnet" "existing" {
  count      = local.enable_existing ? 1 : 0
  subnet_id  = var.existing_controller_subnet_ocid
  depends_on = [terraform_data.existing_inputs]

  lifecycle {
    postcondition {
      condition     = self.vcn_id == var.existing_vcn_ocid
      error_message = "existing_controller_subnet_ocid must belong to existing_vcn_ocid."
    }
  }
}

resource "oci_core_vcn" "lab" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  cidr_block     = var.vcn_cidr_block
  display_name   = "${local.name_prefix}-vcn"
  dns_label      = "zprlab"
  security_attributes = {
    "oracle-zpr.app.value" = "fin-network"
    "oracle-zpr.app.mode"  = "enforce"
  }
  freeform_tags = local.common_tags
  depends_on    = [time_sleep.zpr_attr_propagation]
}

resource "oci_core_internet_gateway" "igw" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab[0].id
  display_name   = "${local.name_prefix}-igw"
}

resource "oci_core_route_table" "public" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab[0].id
  display_name   = "${local.name_prefix}-rt-public"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.igw[0].id
  }
}

# Lab endpoints are private but still need Oracle Services Network access for
# the agent and bootstrap dependencies. Existing-network mode only observes its
# supplied resources and never creates these primitives.
data "oci_core_services" "oracle_services" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

resource "oci_core_service_gateway" "endpoints" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab[0].id
  display_name   = "${local.name_prefix}-endpoints-sgw"

  services {
    service_id = data.oci_core_services.oracle_services.services[0].id
  }
}

resource "oci_core_route_table" "endpoints" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab[0].id
  display_name   = "${local.name_prefix}-rt-endpoints"
  route_rules {
    destination       = data.oci_core_services.oracle_services.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.endpoints[0].id
  }
}

resource "oci_core_security_list" "lab" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab[0].id
  display_name   = "${local.name_prefix}-sl"
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
  ingress_security_rules {
    source   = var.vcn_cidr_block
    protocol = "all"
  }
}

resource "oci_core_subnet" "endpoints" {
  count                      = local.enable_lab ? 1 : 0
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.lab[0].id
  cidr_block                 = local.endpoint_subnet_cidr
  display_name               = "${local.name_prefix}-endpoints"
  dns_label                  = "endpoints"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.lab[0].id]
  route_table_id             = oci_core_route_table.endpoints[0].id
}

resource "oci_core_subnet" "controller" {
  count             = local.enable_lab ? 1 : 0
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.lab[0].id
  cidr_block        = local.controller_subnet_cidr
  display_name      = "${local.name_prefix}-controller"
  dns_label         = "controller"
  security_list_ids = [oci_core_security_list.lab[0].id]
  route_table_id    = oci_core_route_table.public[0].id
}

resource "oci_logging_log_group" "flow" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.compartment_ocid
  display_name   = "${local.name_prefix}-flow-logs"
  freeform_tags  = local.common_tags
}

resource "oci_logging_log" "subnet_flow" {
  count        = local.enable_lab ? 1 : 0
  display_name = "${local.name_prefix}-endpoints-flow"
  log_group_id = oci_logging_log_group.flow[0].id
  log_type     = "SERVICE"
  is_enabled   = true
  configuration {
    compartment_id = var.compartment_ocid
    source {
      category    = "all"
      resource    = oci_core_subnet.endpoints[0].id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }
  retention_duration = 30
}

moved {
  from = oci_core_vcn.lab
  to   = oci_core_vcn.lab[0]
}
moved {
  from = oci_core_internet_gateway.igw
  to   = oci_core_internet_gateway.igw[0]
}
moved {
  from = oci_core_route_table.public
  to   = oci_core_route_table.public[0]
}
moved {
  from = oci_core_service_gateway.endpoints
  to   = oci_core_service_gateway.endpoints[0]
}
moved {
  from = oci_core_route_table.endpoints
  to   = oci_core_route_table.endpoints[0]
}
moved {
  from = oci_core_security_list.lab
  to   = oci_core_security_list.lab[0]
}
moved {
  from = oci_core_subnet.endpoints
  to   = oci_core_subnet.endpoints[0]
}
moved {
  from = oci_core_subnet.controller
  to   = oci_core_subnet.controller[0]
}
moved {
  from = oci_logging_log_group.flow
  to   = oci_logging_log_group.flow[0]
}
moved {
  from = oci_logging_log.subnet_flow
  to   = oci_logging_log.subnet_flow[0]
}

# Resolve the existing log's real source before presenting its traffic beside
# the selected VCN. Logging supports VCN, subnet and VNIC flow-log sources.
data "oci_logging_log" "existing_flow" {
  count        = local.validate_existing_flow ? 1 : 0
  log_group_id = local.flow_log_group_id
  log_id       = local.flow_log_id

  lifecycle {
    postcondition {
      condition     = self.is_enabled && self.log_type == "SERVICE" && try(self.configuration[0].source[0].service, "") == "flowlogs"
      error_message = "The existing log must be an enabled VCN Flow service log."
    }
    postcondition {
      condition     = self.compartment_id == local.observation_compartment_id
      error_message = "The existing flow log must belong to observation_compartment_ocid."
    }
  }
}

locals {
  existing_flow_source_id = local.validate_existing_flow ? try(data.oci_logging_log.existing_flow[0].configuration[0].source[0].resource, "") : ""
  existing_flow_is_subnet = local.validate_existing_flow && startswith(local.existing_flow_source_id, "ocid1.subnet.")
  existing_flow_is_vnic   = local.validate_existing_flow && startswith(local.existing_flow_source_id, "ocid1.vnic.")
}

data "oci_core_vnic" "flow_source" {
  count   = local.existing_flow_is_vnic ? 1 : 0
  vnic_id = local.existing_flow_source_id
}

data "oci_core_subnet" "flow_source" {
  count     = local.existing_flow_is_subnet || local.existing_flow_is_vnic ? 1 : 0
  subnet_id = local.existing_flow_is_vnic ? data.oci_core_vnic.flow_source[0].subnet_id : local.existing_flow_source_id

  lifecycle {
    postcondition {
      condition     = self.vcn_id == var.existing_vcn_ocid
      error_message = "The existing flow-log source subnet/VNIC must belong to the selected VCN."
    }
  }
}

resource "terraform_data" "existing_flow_scope" {
  count = local.validate_existing_flow ? 1 : 0
  lifecycle {
    precondition {
      condition     = local.existing_flow_source_id == var.existing_vcn_ocid || local.existing_flow_is_subnet || local.existing_flow_is_vnic
      error_message = "The flow log must observe the selected VCN or a subnet/VNIC verified within it."
    }
  }
  depends_on = [data.oci_core_subnet.flow_source]
}
