import unittest
from unittest import mock

from oci_zpr_visibility import discover


SNAPSHOT = {
    "snapshot_time": "2026-06-17T00:00:00Z",
    "zpr_configuration": {"zpr_status": "ENABLED"},
    "zpr_policies": [
        {"name": "demo", "lifecycle_state": "ACTIVE", "statements": ["s1", "s2"]},
    ],
    "security_attributes": [
        {"name": "app", "namespace_name": "oracle-zpr"},
        {"name": "team", "namespace_name": "other-ns"},
    ],
    "resources": [
        {"resource_type": "instance", "normalized_security_attributes": {"oracle-zpr.app": "web"}},
        {"resource_type": "Vcn", "normalized_security_attributes": {"oracle-zpr.app": "fin-network"}},
        {"resource_type": "instance", "normalized_security_attributes": {}},  # unprotected
    ],
}


class FakeSession:
    tenancy_id = "ocid1.tenancy.oc1..fake"
    region = "eu-frankfurt-1"


class DiscoverTests(unittest.TestCase):
    def _run(self):
        fake_collector = mock.Mock()
        fake_collector.collect.return_value = SNAPSHOT
        with mock.patch.object(discover, "ZprCollector", return_value=fake_collector), \
             mock.patch.object(discover, "_compartment_ids", return_value=["c1"]), \
             mock.patch.object(discover, "_discover_flow_logs", return_value=[
                 {"flow_log_compartment_id": "c1", "flow_log_group_id": "g1",
                  "flow_log_id": "l1", "flow_log_name": "vcn-flow"}]):
            return discover.discover(FakeSession(), compartment_id="c1")

    def test_summarizes_zpr_state(self):
        report = self._run()
        self.assertTrue(report["zpr_enabled"])
        self.assertEqual(report["zpr_status"], "ENABLED")
        self.assertEqual(report["policy_count"], 1)
        self.assertEqual(report["policies"][0]["statements"], 2)

    def test_only_oracle_zpr_attributes_listed(self):
        report = self._run()
        self.assertEqual(report["oracle_zpr_attributes"], ["app"])

    def test_counts_only_protected_resources(self):
        report = self._run()
        self.assertEqual(report["protected_resource_count"], 2)
        self.assertEqual(report["protected_by_type"], {"instance": 1, "Vcn": 1})

    def test_flow_logs_passthrough(self):
        report = self._run()
        self.assertEqual(report["flow_logs"][0]["flow_log_group_id"], "g1")

    def test_disabled_when_configuration_errors(self):
        snap = dict(SNAPSHOT, zpr_configuration={"error": "NotAuthorizedOrNotFound"})
        fake_collector = mock.Mock()
        fake_collector.collect.return_value = snap
        with mock.patch.object(discover, "ZprCollector", return_value=fake_collector), \
             mock.patch.object(discover, "_compartment_ids", return_value=["c1"]), \
             mock.patch.object(discover, "_discover_flow_logs", return_value=[]):
            report = discover.discover(FakeSession(), compartment_id="c1")
        self.assertFalse(report["zpr_enabled"])


if __name__ == "__main__":
    unittest.main()
