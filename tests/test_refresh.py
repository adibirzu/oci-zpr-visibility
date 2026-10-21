import unittest
from unittest import mock

from oci_zpr_visibility import refresh


class RefreshFlowLogTests(unittest.TestCase):
    def test_refresh_passes_log_group_compartment_to_provision(self):
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
            mock.patch("oci_zpr_visibility.refresh.provision_la.main", return_value=0) as provision,
            mock.patch("oci_zpr_visibility.metrics.publish_metrics", return_value=0) as metrics,
        ):
            self.assertEqual(refresh.main([
                "--state-bucket", "state",
                "--log-group-compartment-id", "observation-compartment",
            ]), 0)

        self.assertEqual(metrics.call_args.kwargs["compartment_id"], "observation-compartment")
        argv = provision.call_args.args[0]
        self.assertEqual(argv[argv.index("--log-group-compartment-id") + 1], "observation-compartment")

    def test_partial_flow_flags_are_rejected_before_session(self):
        with mock.patch("oci_zpr_visibility.refresh.build_session") as build_session:
            with self.assertRaises(SystemExit):
                refresh.main(["--state-bucket", "state", "--flow-log-group-id", "group"])
        build_session.assert_not_called()

    def test_nonpositive_lookback_is_rejected_before_session(self):
        with mock.patch("oci_zpr_visibility.refresh.build_session") as build_session:
            with self.assertRaises(SystemExit):
                refresh.main(["--state-bucket", "state", "--flow-lookback-minutes", "0"])
        build_session.assert_not_called()

    def test_failed_provision_reports_zero_uploaded(self):
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
            mock.patch("oci_zpr_visibility.refresh.provision_la.main", return_value=7),
            mock.patch("oci_zpr_visibility.metrics.publish_metrics", return_value=0),
            mock.patch("oci_zpr_visibility.refresh.emit") as emit,
        ):
            self.assertEqual(refresh.main(["--state-bucket", "state"]), 7)
        self.assertEqual(emit.call_args.args[0]["uploaded"], 0)
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
            mock.patch("oci_zpr_visibility.refresh.write_jsonl") as write_jsonl,
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
        self.assertFalse(write_jsonl.call_args.args[0].exists())


if __name__ == "__main__":
    unittest.main()
