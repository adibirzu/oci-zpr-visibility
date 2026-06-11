import unittest

from oci_zpr_visibility.collector import protected_resource_record


class ProtectedResourceRecordTests(unittest.TestCase):
    def test_none_when_no_security_attributes(self):
        self.assertIsNone(protected_resource_record(
            None, resource_id="fake-vcn", resource_name="v", resource_type="Vcn",
            compartment_id="c", region="eu-frankfurt-1"))
        self.assertIsNone(protected_resource_record(
            {}, resource_id="fake-vcn", resource_name="v", resource_type="Vcn",
            compartment_id="c", region="eu-frankfurt-1"))

    def test_builds_record_with_normalized_attrs(self):
        sa = {"oracle-zpr": {"app": {"value": "fin-network", "mode": "enforce"}}}
        rec = protected_resource_record(
            sa, resource_id="fake-vcn", resource_name="demo-vcn", resource_type="Vcn",
            compartment_id="fake-compartment", region="eu-frankfurt-1", vcn_id="fake-vcn")
        self.assertEqual(rec["resource_type"], "Vcn")
        self.assertEqual(rec["normalized_security_attributes"], {"oracle-zpr.app": "fin-network"})
        self.assertEqual(rec["vcn_id"], "fake-vcn")


if __name__ == "__main__":
    unittest.main()
