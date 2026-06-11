# ZPR-protected endpoints: web (app=web) and db (app=db) with static IPs that
# generate intra-VCN traffic (web->db allowed by policy; db->web denied by ZPR).

locals {
  endpoints = {
    web = { ip = "10.20.1.10", peer = "10.20.1.20", port = 1521, tier = "web" }
    db  = { ip = "10.20.1.20", peer = "10.20.1.10", port = 22, tier = "db" }
  }
}

resource "oci_core_instance" "endpoint" {
  for_each            = local.endpoints
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "${local.name_prefix}-${each.key}"
  shape               = "VM.Standard.E3.Flex"
  shape_config {
    ocpus         = 1
    memory_in_gbs = 8
  }
  security_attributes = {
    "oracle-zpr.app.value" = each.value.tier
    "oracle-zpr.app.mode"  = "enforce"
  }
  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.endpoints.id
    private_ip       = each.value.ip
    assign_public_ip = false
    hostname_label   = each.key
  }
  metadata = merge(
    { user_data = base64encode(<<-EOT
      #!/bin/bash
      cat >/usr/local/bin/zpr-traffic.sh <<'EOS'
      #!/bin/bash
      while true; do timeout 2 bash -c "echo > /dev/tcp/${each.value.peer}/${each.value.port}" 2>/dev/null; sleep 15; done
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
      systemctl daemon-reload && systemctl enable --now zpr-traffic.service
    EOT
    ) },
    var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key },
  )
  freeform_tags = merge(local.common_tags, { role = each.key })
  depends_on    = [time_sleep.zpr_attr_propagation]
}
