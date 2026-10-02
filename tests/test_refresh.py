import unittest
from unittest import mock
import pytest

from oci_zpr_visibility import refresh


class RefreshFlowLogTests(unittest.TestCase):
    def test_asymmetric_flow_configuration_is_rejected_before_oci(self):
        with mock.patch("oci_zpr_visibility.refresh.build_session") as build:
            with pytest.raises(SystemExit):
                refresh.main(["--state-bucket", "state", "--strict", "--flow-log-group-id", "group"])
        build.assert_not_called()

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
            mock.patch("oci_zpr_visibility.refresh.save_records") as save_records,
            mock.patch("oci_zpr_visibility.refresh.write_jsonl") as write_jsonl,
            mock.patch("oci_zpr_visibility.refresh.provision_la.main", return_value=0) as provision_main,
            mock.patch("oci_zpr_visibility.metrics.publish_metrics", return_value=0),
            mock.patch("oci_zpr_visibility.flow_logs.fetch_flow_logs", return_value=[]) as fetch_flow_logs,
        ):
            rc = refresh.main([
                "--state-bucket", "state",
                "--log-analytics-compartment-id", "la-compartment",
                "--flow-log-compartment-id", "flow-compartment",
                "--flow-log-group-id", "flow-log-group",
                "--flow-log-id", "flow-log",
            ])

        self.assertEqual(rc, 0)
        self.assertEqual(fetch_flow_logs.call_args.args[1], "flow-compartment")
        self.assertIn("--compartment-id", provision_main.call_args.args[0])
        self.assertIn("la-compartment", provision_main.call_args.args[0])
        self.assertFalse(write_jsonl.call_args.args[0].exists())
        save_records.assert_called_once()

    def test_strict_flow_failure_does_not_advance_drift_baseline(self):
        session = mock.Mock(tenancy_id="tenancy")
        collector = mock.Mock()
        collector.collect.return_value = {"resources": [], "ip_resource_map": [], "collection_error_count": 0}
        collector.records_for_snapshot.return_value = []
        with (
            mock.patch("oci_zpr_visibility.refresh.build_session", return_value=session),
            mock.patch("oci_zpr_visibility.refresh.ZprCollector", return_value=collector),
            mock.patch("oci_zpr_visibility.refresh.generate_findings", return_value=[]),
            mock.patch("oci_zpr_visibility.refresh.load_previous_records", return_value=[]),
            mock.patch("oci_zpr_visibility.refresh.compute_drift", return_value=[]),
            mock.patch("oci_zpr_visibility.refresh.save_records") as save_records,
            mock.patch("oci_zpr_visibility.refresh.write_jsonl"),
            mock.patch("oci_zpr_visibility.refresh.provision_la.main", return_value=0),
            mock.patch("oci_zpr_visibility.metrics.publish_metrics", return_value=0),
            mock.patch("oci_zpr_visibility.flow_logs.fetch_flow_logs", side_effect=RuntimeError("unavailable")),
        ):
            rc = refresh.main(["--state-bucket", "state", "--strict",
                "--flow-log-group-id", "group", "--flow-log-id", "flow"])
        self.assertEqual(rc, 1)
        save_records.assert_not_called()


if __name__ == "__main__":
    unittest.main()
