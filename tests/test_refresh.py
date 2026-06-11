import unittest
from unittest import mock

from oci_zpr_visibility import refresh


class RefreshFlowLogTests(unittest.TestCase):
    def test_live_flow_fetch_uses_explicit_flow_compartment(self):
        session = mock.Mock()
        session.tenancy_id = "tenancy"
        collector = mock.Mock()
        collector.collect.return_value = {"resources": [], "ip_resource_map": []}
        collector.records_for_snapshot.return_value = []

        with (
            mock.patch("oci_zpr_visibility.refresh.build_session", return_value=session),
            mock.patch("oci_zpr_visibility.refresh.ZprCollector", return_value=collector),
            mock.patch("oci_zpr_visibility.refresh.generate_findings", return_value=[]),
            mock.patch("oci_zpr_visibility.refresh.load_previous_records", return_value=[]),
            mock.patch("oci_zpr_visibility.refresh.compute_drift", return_value=[]),
            mock.patch("oci_zpr_visibility.refresh.save_records"),
            mock.patch("oci_zpr_visibility.refresh.write_jsonl"),
            mock.patch("oci_zpr_visibility.refresh.provision_la.main", return_value=0),
            mock.patch("oci_zpr_visibility.metrics.publish_metrics", return_value=0),
            mock.patch("oci_zpr_visibility.flow_logs.fetch_flow_logs", return_value=[]) as fetch_flow_logs,
        ):
            rc = refresh.main([
                "--state-bucket", "state",
                "--flow-log-compartment-id", "flow-compartment",
                "--flow-log-group-id", "flow-log-group",
                "--flow-log-id", "flow-log",
            ])

        self.assertEqual(rc, 0)
        self.assertEqual(fetch_flow_logs.call_args.args[1], "flow-compartment")


if __name__ == "__main__":
    unittest.main()
