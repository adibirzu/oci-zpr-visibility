import unittest

from oci_zpr_visibility.correlate import correlate_flow_records
from oci_zpr_visibility.policy_parser import policy_statement_records


class CorrelateTests(unittest.TestCase):
    def test_correlates_expected_and_rejected_flows(self):
        snapshot = {
            "snapshot_time": "2026-06-03T10:00:00Z",
            "zpr_policies": [
                {
                    "id": "policy-1",
                    "name": "web-db",
                    "statements": ["in networks:prod allow apps:web endpoints to connect to apps:db endpoints"],
                }
            ],
            "ip_resource_map": [
                {
                    "private_ip": "10.0.1.10",
                    "resource_id": "web-1",
                    "resource_name": "web",
                    "normalized_security_attributes": {"apps.role": "web"},
                },
                {
                    "private_ip": "10.0.2.20",
                    "resource_id": "db-1",
                    "resource_name": "db",
                    "normalized_security_attributes": {"apps.role": "db"},
                },
                {
                    "private_ip": "10.0.2.30",
                    "resource_id": "payroll-db",
                    "resource_name": "payroll-db",
                    "normalized_security_attributes": {"apps.role": "payroll-db"},
                },
            ],
        }
        policies = policy_statement_records(snapshot["zpr_policies"][0], snapshot["snapshot_time"])
        flows = [
            {"data": {"action": "ACCEPT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.20"}},
            {"data": {"action": "REJECT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.30"}},
        ]

        enriched = correlate_flow_records(flows, snapshot, policies)

        self.assertEqual(enriched[0]["classification"], "expected_accepted")
        self.assertEqual(enriched[0]["review_classification"], "policy_consistent_accept")
        self.assertEqual(enriched[0]["zpr_attribution"], "INFERRED_NOT_PROVIDER_VERDICT")
        self.assertEqual(enriched[0]["correlation_confidence"], "MEDIUM")
        self.assertEqual(enriched[1]["classification"], "expected_blocked")

    def test_preserves_flow_evidence_and_event_time(self):
        snapshot = {
            "snapshot_time": "2026-06-03T09:59:00Z",
            "ip_resource_map": [{
                "private_ip": "10.0.2.20",
                "resource_id": "db-1",
                "normalized_security_attributes": {"app": "db"},
            }],
        }
        flow = {
            "time": "2026-06-03T10:00:00Z",
            "data": {
                "action": "REJECT",
                "sourceAddress": "10.0.1.10",
                "sourcePort": 44321,
                "destinationAddress": "10.0.2.20",
                "destinationPort": 1521,
                "protocolName": "TCP",
                "flowid": "flow-1",
                "bytesOut": 2048,
                "packets": 12,
                "status": "OK",
            },
        }
        record = correlate_flow_records([flow], snapshot, [])[0]
        self.assertEqual(record["event_time"], flow["time"])
        self.assertEqual(record["inventory_snapshot_time"], snapshot["snapshot_time"])
        self.assertEqual(record["flow_id"], "flow-1")
        self.assertEqual(record["bytes_out"], 2048)
        self.assertEqual(record["packets"], 12)
        self.assertEqual(record["capture_status"], "OK")
        self.assertEqual(record["review_classification"], "rejected_protected_destination")

    def test_inactive_policy_does_not_match(self):
        snapshot = {
            "snapshot_time": "2026-06-03T10:00:00Z",
            "ip_resource_map": [
                {"private_ip": "10.0.1.10", "normalized_security_attributes": {"app": "web"}},
                {"private_ip": "10.0.2.20", "normalized_security_attributes": {"app": "db"}},
            ],
        }
        policies = [{
            "policy_id": "p1",
            "policy_lifecycle_state": "INACTIVE",
            "source_attribute": "app:web",
            "destination_attribute": "app:db",
            "target_type": "attribute",
        }]
        record = correlate_flow_records([{"data": {
            "action": "ACCEPT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.20"
        }}], snapshot, policies)[0]
        self.assertFalse(record["matched_expected_policy"])
        self.assertEqual(record["review_classification"], "accepted_requires_policy_review")

    def test_cidr_target_matches_without_resolved_endpoint_attributes(self):
        snapshot = {"snapshot_time": "2026-06-03T10:00:00Z", "ip_resource_map": []}
        policies = [{
            "policy_id": "p1",
            "policy_lifecycle_state": "ACTIVE",
            "source_type": "all_endpoints",
            "target_type": "cidr",
            "destination_cidrs": ["10.0.2.0/24"],
            "parser_confidence": "high",
        }]
        record = correlate_flow_records([{"data": {
            "action": "ACCEPT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.20"
        }}], snapshot, policies)[0]
        self.assertTrue(record["matched_expected_policy"])
        self.assertEqual(record["review_classification"], "policy_consistent_accept")


if __name__ == "__main__":
    unittest.main()
