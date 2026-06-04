# Network: VCN (ZPR-tagged) + a public subnet (controller egress) + a private
# subnet (web/db endpoints) + subnet VCN Flow Logs.

resource "oci_core_vcn" "lab" {
  compartment_id = var.compartment_ocid
  cidr_block     = "10.20.0.0/16"
  display_name   = "${local.name_prefix}-vcn"
  dns_label      = "zprlab"
  security_attributes = {
    "oracle-zpr.app.value" = "fin-network"
    "oracle-zpr.app.mode"  = "enforce"
  }
  freeform_tags = local.common_tags
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab.id
  display_name   = "${local.name_prefix}-igw"
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab.id
  display_name   = "${local.name_prefix}-rt-public"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.igw.id
  }
}

resource "oci_core_security_list" "lab" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lab.id
  display_name   = "${local.name_prefix}-sl"
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
  ingress_security_rules {
    source   = "10.20.0.0/16"
    protocol = "all"
  }
}

resource "oci_core_subnet" "endpoints" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.lab.id
  cidr_block                 = "10.20.1.0/24"
  display_name               = "${local.name_prefix}-endpoints"
  dns_label                  = "endpoints"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.lab.id]
  route_table_id             = oci_core_vcn.lab.default_route_table_id
}

resource "oci_core_subnet" "controller" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.lab.id
  cidr_block        = "10.20.2.0/24"
  display_name      = "${local.name_prefix}-controller"
  dns_label         = "controller"
  security_list_ids = [oci_core_security_list.lab.id]
  route_table_id    = oci_core_route_table.public.id
}

resource "oci_logging_log_group" "flow" {
  compartment_id = var.compartment_ocid
  display_name   = "${local.name_prefix}-flow-logs"
  freeform_tags  = local.common_tags
}

resource "oci_logging_log" "subnet_flow" {
  display_name = "${local.name_prefix}-endpoints-flow"
  log_group_id = oci_logging_log_group.flow.id
  log_type     = "SERVICE"
  is_enabled   = true
  configuration {
    compartment_id = var.compartment_ocid
    source {
      category    = "all"
      resource    = oci_core_subnet.endpoints.id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }
  retention_duration = 30
}
