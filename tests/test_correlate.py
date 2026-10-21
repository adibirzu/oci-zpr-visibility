import unittest

from oci_zpr_visibility.correlate import correlate_flow_records
from oci_zpr_visibility.policy_parser import policy_statement_records


class CorrelateTests(unittest.TestCase):
    def test_cross_vcn_scope_requires_inventory_membership(self):
        snapshot = {"resources": [
            {"resource_type": "Vcn", "resource_id": "vcn-a", "normalized_security_attributes": {"app": "source"}},
            {"resource_type": "Vcn", "resource_id": "vcn-b", "normalized_security_attributes": {"app": "destination"}},
        ], "ip_resource_map": [
            {"private_ip": "10.0.0.1", "vcn_id": "vcn-a", "normalized_security_attributes": {"app": "web"}},
            {"private_ip": "10.1.0.1", "vcn_id": "vcn-b", "normalized_security_attributes": {"app": "db"}},
        ]}
        policy = policy_statement_records({"id": "p", "lifecycle_state": "ACTIVE", "statements": [
            "in app:source VCN allow app:web endpoints to connect to app:db endpoints in app:destination VCN"
        ]}, "t")
        flow = {"data": {"sourceAddress": "10.0.0.1", "destinationAddress": "10.1.0.1", "action": "ACCEPT"}}
        self.assertTrue(correlate_flow_records([flow], snapshot, policy)[0]["matched_expected_policy"])
        snapshot["resources"][1]["resource_id"] = "vcn-other"
        self.assertFalse(correlate_flow_records([flow], snapshot, policy)[0]["matched_expected_policy"])

    def test_scoped_policy_after_nonmatching_policy_does_not_crash(self):
        snapshot = {"resources": [
            {"resource_type": "Vcn", "resource_id": "vcn-a",
             "normalized_security_attributes": {"networks": "prod"}},
        ], "ip_resource_map": [
            {"private_ip": "10.0.0.1", "vcn_id": "vcn-a",
             "normalized_security_attributes": {"apps.role": "web"}},
            {"private_ip": "10.0.0.2", "vcn_id": "vcn-a",
             "normalized_security_attributes": {"apps.role": "db"}},
        ]}
        policies = [
            {"policy_id": "nonmatch", "policy_lifecycle_state": "ACTIVE",
             "source_attribute": "apps:other", "destination_attribute": "apps:db",
             "target_type": "attribute"},
            {"policy_id": "scoped-match", "policy_lifecycle_state": "ACTIVE",
             "source_vcn_scope": "networks:prod", "destination_vcn_scope": "networks:prod",
             "source_attribute": "apps:web", "destination_attribute": "apps:db",
             "target_type": "attribute"},
        ]
        flow = {"data": {"sourceAddress": "10.0.0.1", "destinationAddress": "10.0.0.2",
                         "action": "ACCEPT"}}

        record = correlate_flow_records([flow], snapshot, policies)[0]

        self.assertTrue(record["matched_expected_policy"])
        self.assertEqual(record["matched_policy_id"], "scoped-match")

    def test_capture_context_does_not_resolve_ambiguous_peer(self):
        snapshot = {"ip_resource_map": [
            {"private_ip": "10.0.0.1", "vnic_id": "local", "vcn_id": "a", "resource_id": "source"},
            {"private_ip": "10.0.0.2", "vcn_id": "a", "resource_id": "peer-a"},
            {"private_ip": "10.0.0.2", "vcn_id": "b", "resource_id": "peer-b"},
        ]}
        flow = {"oracle.vnicocid": "local", "oracle.vcnocid": "a", "data": {
            "sourceAddress": "10.0.0.1", "destinationAddress": "10.0.0.2", "action": "ACCEPT"}}
        record = correlate_flow_records([flow], snapshot, [])[0]
        self.assertEqual(record["source_resource_id"], "source")
        self.assertIsNone(record["destination_resource_id"])
        self.assertEqual(record["correlation_reason"], "ambiguous_destination_address")

    def test_capture_context_can_identify_destination_side_for_ingress_flow(self):
        snapshot = {"ip_resource_map": [
            {"private_ip": "10.0.0.2", "vcn_id": "a", "resource_id": "peer-a"},
            {"private_ip": "10.0.0.2", "vcn_id": "b", "resource_id": "peer-b"},
            {"private_ip": "10.0.0.1", "vnic_id": "local", "vcn_id": "a", "resource_id": "destination"},
        ]}
        flow = {"oracle.vnicocid": "local", "oracle.vcnocid": "a", "data": {
            "sourceAddress": "10.0.0.2", "destinationAddress": "10.0.0.1", "action": "ACCEPT"}}
        record = correlate_flow_records([flow], snapshot, [])[0]
        self.assertIsNone(record["source_resource_id"])
        self.assertEqual(record["destination_resource_id"], "destination")
        self.assertEqual(record["correlation_reason"], "ambiguous_source_address")

    def test_correlates_expected_and_rejected_flows(self):
        snapshot = {
            "snapshot_time": "2026-06-03T10:00:00Z",
            "resources": [{"resource_type": "Vcn", "resource_id": "vcn-prod",
                "normalized_security_attributes": {"networks": "prod"}}],
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
                    "vcn_id": "vcn-prod",
                    "normalized_security_attributes": {"apps.role": "web"},
                },
                {
                    "private_ip": "10.0.2.20",
                    "resource_id": "db-1",
                    "resource_name": "db",
                    "vcn_id": "vcn-prod",
                    "normalized_security_attributes": {"apps.role": "db"},
                },
                {
                    "private_ip": "10.0.2.30",
                    "resource_id": "payroll-db",
                    "resource_name": "payroll-db",
                    "vcn_id": "vcn-prod",
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

    def test_duplicate_ip_across_vcns_is_inconclusive_without_flow_context(self):
        snapshot = {
            "snapshot_time": "2026-06-03T10:00:00Z",
            "ip_resource_map": [
                {"private_ip": "10.0.1.10", "resource_id": "web-a", "vcn_id": "vcn-a",
                 "normalized_security_attributes": {"apps.role": "web"}},
                {"private_ip": "10.0.1.10", "resource_id": "web-b", "vcn_id": "vcn-b",
                 "normalized_security_attributes": {"apps.role": "web"}},
                {"private_ip": "10.0.2.20", "resource_id": "db", "vcn_id": "vcn-a",
                 "normalized_security_attributes": {"apps.role": "db"}},
            ],
        }
        policies = policy_statement_records({
            "id": "p1", "lifecycle_state": "ACTIVE",
            "statements": ["allow apps:web endpoints to connect to apps:db endpoints"],
        }, snapshot["snapshot_time"])

        record = correlate_flow_records([{"data": {
            "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.20", "action": "ACCEPT"
        }}], snapshot, policies)[0]

        self.assertIsNone(record["source_resource_id"])
        self.assertEqual(record["correlation_reason"], "ambiguous_source_address")
        self.assertEqual(record["review_classification"], "needs_enrichment")


if __name__ == "__main__":
    unittest.main()
