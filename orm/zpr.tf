# ZPR: add the 'app' security attribute to the default oracle-zpr namespace and
# a policy (web->db allowed; db->web denied by absence). ZPR tenancy config is
# assumed already enabled (it is tenancy-wide and singleton).

data "oci_security_attribute_security_attribute_namespaces" "oracle_zpr" {
  compartment_id = var.tenancy_ocid
  name           = "oracle-zpr"
  state          = "ACTIVE"
}

locals {
  oracle_zpr_ns_id = data.oci_security_attribute_security_attribute_namespaces.oracle_zpr.security_attribute_namespaces[0].id
}

resource "oci_security_attribute_security_attribute" "app" {
  security_attribute_namespace_id = local.oracle_zpr_ns_id
  name                            = "app"
  description                     = "ZPR visibility demo application tier"
  validator {
    validator_type = "ENUM"
    values         = ["web", "db", "ops", "fin-network", "payroll"]
  }
}

resource "oci_zpr_zpr_policy" "demo" {
  compartment_id = var.tenancy_ocid
  name           = "zpr-visibility-demo"
  description    = "ZPR visibility demo: web->db allowed; broad-CIDR exception."
  statements = [
    "in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints",
    "in app:fin-network VCN allow app:ops endpoints to connect to '10.0.0.0/8'",
  ]
  depends_on = [oci_security_attribute_security_attribute.app]
}
