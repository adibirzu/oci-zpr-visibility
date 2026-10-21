# ZPR: add the 'app' security attribute to the default oracle-zpr namespace and
# a policy (web->db allowed; db->web denied by absence). ZPR tenancy config is
# assumed already enabled (it is tenancy-wide and singleton).

data "oci_security_attribute_security_attribute_namespaces" "oracle_zpr" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "oracle-zpr"
  state          = "ACTIVE"
}

locals {
  oracle_zpr_ns_id = local.enable_lab ? data.oci_security_attribute_security_attribute_namespaces.oracle_zpr[0].security_attribute_namespaces[0].id : null
}

resource "oci_security_attribute_security_attribute" "app" {
  count                           = local.enable_lab ? 1 : 0
  security_attribute_namespace_id = local.oracle_zpr_ns_id
  name                            = "app"
  description                     = "ZPR visibility demo application tier"
  validator {
    validator_type = "ENUM"
    values         = ["web", "db", "ops", "fin-network", "payroll"]
  }
}

# A newly created ZPR security attribute is not instantly referencable from a
# resource's security_attributes map (it must propagate). The VCN and endpoint
# instances reference "oracle-zpr.app.*" as literal strings, so Terraform has no
# implicit dependency on the attribute above — without this gate they create in
# parallel and fail with "400-InvalidParameter, Invalid tags". Gate them on this.
resource "time_sleep" "zpr_attr_propagation" {
  count           = local.enable_lab ? 1 : 0
  depends_on      = [oci_security_attribute_security_attribute.app]
  create_duration = "90s"
}

resource "oci_zpr_zpr_policy" "demo" {
  count          = local.enable_lab ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "zpr-visibility-demo"
  description    = "ZPR visibility demo: web->db allowed; broad-CIDR exception."
  statements = [
    "in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints",
    "in app:fin-network VCN allow app:ops endpoints to connect to '10.0.0.0/8'",
  ]
  depends_on = [oci_security_attribute_security_attribute.app]
}

moved {
  from = oci_security_attribute_security_attribute.app
  to   = oci_security_attribute_security_attribute.app[0]
}
moved {
  from = time_sleep.zpr_attr_propagation
  to   = time_sleep.zpr_attr_propagation[0]
}
moved {
  from = oci_zpr_zpr_policy.demo
  to   = oci_zpr_zpr_policy.demo[0]
}
