import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
ORM = ROOT / "orm"


class OrmUpgradeSafetyTests(unittest.TestCase):
    def read(self, name):
        return (ORM / name).read_text()

    def test_lab_network_keeps_endpoint_service_gateway_and_route(self):
        network = self.read("network.tf")
        self.assertIn('resource "oci_core_service_gateway" "endpoints"', network)
        self.assertIn('resource "oci_core_route_table" "endpoints"', network)
        self.assertIn('route_table_id             = oci_core_route_table.endpoints[0].id', network)
        self.assertIn('to   = oci_core_service_gateway.endpoints[0]', network)
        self.assertIn('to   = oci_core_route_table.endpoints[0]', network)

    def test_endpoint_bootstrap_is_listener_based_and_replace_safe(self):
        compute = self.read("compute.tf")
        self.assertIn('resource "terraform_data" "endpoint_bootstrap"', compute)
        self.assertIn('for_each = local.enable_lab ? local.endpoints : {}', compute)
        self.assertIn('zpr-listener.service', compute)
        self.assertIn('python3 -m http.server', compute)
        self.assertIn('replace_triggered_by = [terraform_data.endpoint_bootstrap[each.key]]', compute)

    def test_guest_hardening_and_flexible_instance_settings_are_retained(self):
        compute = self.read("compute.tf")
        variables = self.read("variables.tf")
        for text in (compute,):
            self.assertIn('are_legacy_imds_endpoints_disabled = true', text)
            self.assertIn('name          = "Compute Instance Run Command"', text)
            self.assertIn('desired_state = "ENABLED"', text)
            self.assertIn('shape               = var.instance_shape', text)
        for variable in ('vcn_cidr_block', 'instance_shape', 'instance_ocpus', 'instance_memory_gbs'):
            self.assertIn(f'variable "{variable}"', variables)

    def test_upgrade_name_compatibility_and_least_privilege_scopes(self):
        variables = self.read("variables.tf")
        schema = self.read("schema.yaml")
        self.assertIn('variable "installation_id"', variables)
        self.assertIn('variable "name_prefix"', variables)
        self.assertIn('var.name_prefix == "zpr-visibility" && var.installation_id != "zpr-visibility"', variables)
        self.assertIn('scope = "compartment id ${var.compartment_ocid}"', variables)
        self.assertIn('for compartment_id in local.observation_compartment_ids', variables)
        self.assertIn('scope = "compartment id ${compartment_id}"', variables)
        self.assertIn('read security-attribute-namespaces', variables)
        self.assertIn("target.bucket.name='${local.name_prefix}-state'", variables)
        self.assertIn("target.bucket.name='${local.name_prefix}-pkg'", variables)
        self.assertIn('installation_id:', schema)

    def test_explicit_collection_scope_rejects_empty_or_blank_ids(self):
        variables = self.read("variables.tf")
        self.assertIn('variable "collection_compartment_ocids"', variables)
        self.assertIn("var.collection_compartment_ocids == null ? true : (", variables)
        self.assertIn("length(var.collection_compartment_ocids) > 0", variables)
        self.assertIn("trimspace(compartment_id) != \"\"", variables)

    def test_flow_log_reads_are_independent_of_inventory_scope(self):
        variables = self.read("variables.tf")
        self.assertIn("local.enable_lab || local.validate_existing_flow", variables)
        self.assertIn('{ perm = "read log-groups", scope = "compartment id ${local.observation_compartment_id}" }', variables)
        self.assertIn('{ perm = "read log-content", scope = "compartment id ${local.observation_compartment_id}" }', variables)

    def test_lab_primitives_are_disabled_in_existing_network_mode(self):
        network = self.read("network.tf")
        compute = self.read("compute.tf")
        for resource in (
            'resource "oci_core_vcn" "lab"',
            'resource "oci_core_internet_gateway" "igw"',
            'resource "oci_core_service_gateway" "endpoints"',
            'resource "oci_core_route_table" "endpoints"',
            'resource "oci_core_subnet" "endpoints"',
            'resource "oci_logging_log" "subnet_flow"',
        ):
            start = network.index(resource)
            block = network[start : network.find("\n}\n", start) + 3]
            self.assertIn("local.enable_lab ? 1 : 0", block)
        self.assertIn("for_each            = local.enable_lab ? local.endpoints : {}", compute)


if __name__ == "__main__":
    unittest.main()


def test_scope_validation_executes_in_terraform_for_defaults_and_invalid_inputs(tmp_path):
    import shutil
    import subprocess
    import pytest
    if not shutil.which('terraform'):
        pytest.skip('Terraform is required for scope validation')
    source = (ORM/'variables.tf').read_text()
    start = source.index('variable "collection_compartment_ocids"')
    end = source.index('\nvariable ', start + 1)
    (tmp_path/'scope.tf').write_text(source[start:end])
    for value, accepted in [(None, True), ('[]', False), ('[""]', False), ('["  "]', False), ('[null]', False), ('["valid"]', True)]:
        args = ['terraform', f'-chdir={tmp_path}', 'plan', '-input=false', '-no-color', '-lock=false']
        if value is not None:
            args += ['-var', f'collection_compartment_ocids={value}']
        result = subprocess.run(args, text=True, capture_output=True, timeout=30)
        assert (result.returncode == 0) == accepted, result.stderr
