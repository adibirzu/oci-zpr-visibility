import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
ORM = ROOT / "orm"


class OrmExistingNetworkContractTests(unittest.TestCase):
    def read(self, name):
        return (ORM / name).read_text()

    def test_existing_mode_is_opt_in_and_requires_existing_references(self):
        variables = self.read("variables.tf")
        schema = self.read("schema.yaml")
        for text in (variables, schema):
            self.assertIn("network_mode", text)
            self.assertIn("existing_vcn_ocid", text)
            self.assertIn("existing_controller_subnet_ocid", text)
            self.assertIn("existing_flow_log_group_ocid", text)
            self.assertIn("existing_flow_log_ocid", text)
        self.assertIn('default     = "lab"', variables)

    def test_existing_mode_does_not_manage_network_endpoints_or_zpr(self):
        network = self.read("network.tf")
        compute = self.read("compute.tf")
        zpr = self.read("zpr.tf")
        for text in (network, compute, zpr):
            self.assertIn("local.enable_lab", text)
        self.assertIn("existing_controller_subnet_ocid", network)
        self.assertIn("vcn_id", network)

    def test_existing_mode_uses_references_for_observer_placement(self):
        network = self.read("network.tf")
        variables = self.read("variables.tf")
        self.assertIn('data "oci_core_vcn" "existing"', network)
        self.assertIn('data "oci_core_subnet" "existing"', network)
        self.assertIn("postcondition", network)
        self.assertIn("self.vcn_id == var.existing_vcn_ocid", network)
        self.assertIn("controller_subnet_id", variables)

    def test_flow_logs_are_optional_but_must_be_supplied_as_a_pair(self):
        network = self.read("network.tf")
        self.assertIn("existing_flow_log_group_ocid == null", network)
        self.assertIn("existing_flow_log_ocid == null", network)

    def test_existing_mode_passes_supplied_flow_log_ids_to_observer(self):
        controller = self.read("controller.tf")
        functions = self.read("functions.tf")
        self.assertIn("existing_flow_log_group_ocid", self.read("variables.tf"))
        self.assertIn("existing_flow_log_ocid", self.read("variables.tf"))
        self.assertIn("observation_compartment_ocid", self.read("variables.tf"))
        for text in (controller, functions):
            self.assertIn("flow_log_group_id", text)
            self.assertIn("flow_log_id", text)

    def test_packaging_excludes_state_caches_and_writes_to_requested_output(self):
        script = (ROOT / "scripts/build_orm_zip.sh").read_text()
        self.assertIn("${1:-orm-stack.zip}", script)
        self.assertIn(".terraform/*", script)
        self.assertIn("*.tfstate*", script)
        self.assertIn("*.tfstate.*", script)
        self.assertIn("__pycache__/*", script)


if __name__ == "__main__":
    unittest.main()
