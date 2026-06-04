# Isolated ZPR enforcement demo: a VCN + subnet + two ZPR-tagged instances that
# generate intra-VCN traffic (web->db allowed by policy; db->web denied by ZPR),
# plus VCN Flow Logs. Separate state from the main stack — destroy independently.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = { source = "oracle/oci", version = ">= 6.0.0" }
  }
}

provider "oci" {
  region              = var.region
  auth                = "APIKey"
  config_file_profile = var.profile
}

variable "region" {
  type    = string
  default = "eu-frankfurt-1"
}
variable "profile" {
  type    = string
  default = "cap"
}
variable "compartment_ocid" {
  type = string
}
variable "availability_domain" {
  type    = string
  default = "YLXT:EU-FRANKFURT-1-AD-1"
}
variable "image_ocid" {
  type = string
}
variable "ssh_public_key" {
  type    = string
  default = ""
}

locals {
  zpr_tags = {
    web = { "oracle-zpr.app.value" = "web", "oracle-zpr.app.mode" = "enforce" }
    db  = { "oracle-zpr.app.value" = "db", "oracle-zpr.app.mode" = "enforce" }
    vcn = { "oracle-zpr.app.value" = "fin-network", "oracle-zpr.app.mode" = "enforce" }
  }
}

resource "oci_core_vcn" "demo" {
  compartment_id      = var.compartment_ocid
  cidr_block          = "10.20.0.0/16"
  display_name        = "zpr-visibility-demo-vcn"
  dns_label           = "zprdemo"
  security_attributes = local.zpr_tags.vcn
  freeform_tags       = { project = "oci-zpr-visibility" }
}

resource "oci_core_security_list" "demo" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.demo.id
  display_name   = "zpr-demo-sl"
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
  ingress_security_rules {
    source   = "10.20.0.0/16"
    protocol = "all"
  }
}

resource "oci_core_subnet" "demo" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.demo.id
  cidr_block                 = "10.20.1.0/24"
  display_name               = "zpr-demo-subnet"
  dns_label                  = "zprsub"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.demo.id]
  route_table_id             = oci_core_vcn.demo.default_route_table_id
}

# user_data: a systemd loop that pokes the peer over /dev/tcp (no packages/internet).
locals {
  user_data = { for k, v in { web = { peer = "10.20.1.20", port = 1521 }, db = { peer = "10.20.1.10", port = 22 } } :
    k => base64encode(<<-EOT
      #!/bin/bash
      cat >/usr/local/bin/zpr-traffic.sh <<'EOS'
      #!/bin/bash
      while true; do timeout 2 bash -c "echo > /dev/tcp/${v.peer}/${v.port}" 2>/dev/null; sleep 15; done
      EOS
      chmod +x /usr/local/bin/zpr-traffic.sh
      cat >/etc/systemd/system/zpr-traffic.service <<'EOS'
      [Unit]
      Description=ZPR demo traffic generator
      After=network-online.target
      [Service]
      ExecStart=/usr/local/bin/zpr-traffic.sh
      Restart=always
      [Install]
      WantedBy=multi-user.target
      EOS
      systemctl daemon-reload
      systemctl enable --now zpr-traffic.service
    EOT
    )
  }
}

resource "oci_core_instance" "endpoint" {
  for_each            = { web = "10.20.1.10", db = "10.20.1.20" }
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "zpr-demo-${each.key}"
  shape               = "VM.Standard.E3.Flex"
  shape_config {
    ocpus         = 1
    memory_in_gbs = 8
  }
  security_attributes = local.zpr_tags[each.key]
  source_details {
    source_type = "image"
    source_id   = var.image_ocid
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.demo.id
    private_ip       = each.value
    assign_public_ip = false
    hostname_label   = each.key
  }
  metadata = merge(
    { user_data = local.user_data[each.key] },
    var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key },
  )
  freeform_tags = { project = "oci-zpr-visibility", role = each.key }
}

resource "oci_logging_log_group" "flow" {
  compartment_id = var.compartment_ocid
  display_name   = "zpr-demo-flow-logs"
}

resource "oci_logging_log" "subnet_flow" {
  display_name = "zpr-demo-subnet-flow"
  log_group_id = oci_logging_log_group.flow.id
  log_type     = "SERVICE"
  is_enabled   = true
  configuration {
    compartment_id = var.compartment_ocid
    source {
      category    = "all"
      resource    = oci_core_subnet.demo.id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }
  retention_duration = 30
}

output "vcn_ocid" { value = oci_core_vcn.demo.id }
output "subnet_ocid" { value = oci_core_subnet.demo.id }
output "flow_log_group_ocid" { value = oci_logging_log_group.flow.id }
output "flow_log_ocid" { value = oci_logging_log.subnet_flow.id }
output "web_ip" { value = "10.20.1.10" }
output "db_ip" { value = "10.20.1.20" }
