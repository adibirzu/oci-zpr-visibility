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
        self.assertEqual(enriched[1]["classification"], "expected_blocked")


if __name__ == "__main__":
    unittest.main()
