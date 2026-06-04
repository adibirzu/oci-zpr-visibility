import unittest

from oci_zpr_visibility.collector import protected_resource_record


class ProtectedResourceRecordTests(unittest.TestCase):
    def test_none_when_no_security_attributes(self):
        self.assertIsNone(protected_resource_record(
            None, resource_id="ocid1.vcn..x", resource_name="v", resource_type="Vcn",
            compartment_id="c", region="eu-frankfurt-1"))
        self.assertIsNone(protected_resource_record(
            {}, resource_id="ocid1.vcn..x", resource_name="v", resource_type="Vcn",
            compartment_id="c", region="eu-frankfurt-1"))

    def test_builds_record_with_normalized_attrs(self):
        sa = {"oracle-zpr": {"app": {"value": "fin-network", "mode": "enforce"}}}
        rec = protected_resource_record(
            sa, resource_id="ocid1.vcn..x", resource_name="demo-vcn", resource_type="Vcn",
            compartment_id="ocid1.tenancy..c", region="eu-frankfurt-1", vcn_id="ocid1.vcn..x")
        self.assertEqual(rec["resource_type"], "Vcn")
        self.assertEqual(rec["normalized_security_attributes"], {"oracle-zpr.app": "fin-network"})
        self.assertEqual(rec["vcn_id"], "ocid1.vcn..x")


if __name__ == "__main__":
    unittest.main()
