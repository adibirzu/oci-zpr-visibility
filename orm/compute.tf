# ZPR-protected endpoints: web (app=web) and db (app=db) with static IPs that
# generate intra-VCN traffic (web->db allowed by policy; db->web denied by ZPR).

locals {
  endpoints = {
    web = { ip = cidrhost(local.endpoint_subnet_cidr, 10), peer = cidrhost(local.endpoint_subnet_cidr, 20), port = 1521, tier = "web" }
    db  = { ip = cidrhost(local.endpoint_subnet_cidr, 20), peer = cidrhost(local.endpoint_subnet_cidr, 10), port = 8080, tier = "db" }
  }
  endpoint_bootstrap_scripts = {
    for name, endpoint in local.endpoints : name => <<-EOT
      #!/bin/bash
      set -euo pipefail
      cat >/etc/systemd/system/zpr-listener.service <<'EOS'
      [Unit]
      Description=ZPR lab application listener
      After=network-online.target
      Wants=network-online.target
      [Service]
      ExecStart=/usr/bin/python3 -m http.server ${name == "db" ? 1521 : 8080} --bind 0.0.0.0
      Restart=always
      [Install]
      WantedBy=multi-user.target
      EOS
      cat >/usr/local/bin/zpr-traffic.sh <<'EOS'
      #!/bin/bash
      while true; do
        curl --silent --output /dev/null --connect-timeout 2 --max-time 3 \\
          "http://${endpoint.peer}:${endpoint.port}/" || true
        sleep 15
      done
      EOS
      chmod +x /usr/local/bin/zpr-traffic.sh
      cat >/etc/systemd/system/zpr-traffic.service <<'EOS'
      [Unit]
      Description=ZPR demo traffic
      After=network-online.target
      [Service]
      ExecStart=/usr/local/bin/zpr-traffic.sh
      Restart=always
      [Install]
      WantedBy=multi-user.target
      EOS
      systemctl daemon-reload
      systemctl enable --now zpr-traffic.service
      systemctl enable --now zpr-listener.service
    EOT
  }
}

resource "terraform_data" "endpoint_bootstrap" {
  for_each = local.enable_lab ? local.endpoints : {}
  input    = sha256(local.endpoint_bootstrap_scripts[each.key])
}

resource "oci_core_instance" "endpoint" {
  for_each            = local.enable_lab ? local.endpoints : {}
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "${local.name_prefix}-${each.key}"
  shape               = var.instance_shape
  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }
  security_attributes = {
    "oracle-zpr.app.value" = each.value.tier
    "oracle-zpr.app.mode"  = "enforce"
  }
  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid
  }
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  agent_config {
    plugins_config {
      name          = "Compute Instance Run Command"
      desired_state = "ENABLED"
    }
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.endpoints[0].id
    private_ip       = each.value.ip
    assign_public_ip = false
    hostname_label   = each.key
  }
  metadata = merge(
    { user_data = base64encode(local.endpoint_bootstrap_scripts[each.key]) },
    var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key },
  )
  freeform_tags = merge(local.common_tags, { role = each.key })
  depends_on    = [time_sleep.zpr_attr_propagation]
  lifecycle {
    replace_triggered_by = [terraform_data.endpoint_bootstrap[each.key]]
  }
}
