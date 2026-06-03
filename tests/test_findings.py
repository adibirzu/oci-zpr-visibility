import unittest

from oci_zpr_visibility.findings import generate_findings
from oci_zpr_visibility.policy_parser import policy_statement_records


class FindingsTests(unittest.TestCase):
    def test_generate_findings_for_unmatched_resource_and_broad_cidr(self):
        snapshot = {
            "snapshot_time": "2026-06-03T10:00:00Z",
            "zpr_policies": [
                {
                    "id": "policy-1",
                    "name": "web-db",
                    "statements": [
                        "in networks:prod allow apps:web endpoints to connect to apps:db endpoints",
                        "allow apps:ops endpoints to connect to 0.0.0.0/0",
                    ],
                }
            ],
            "security_attributes": [{"namespace_name": "apps", "name": "role"}],
            "resources": [
                {
                    "resource_id": "db-1",
                    "resource_name": "payroll-db",
                    "resource_type": "database",
                    "normalized_security_attributes": {"apps.role": "payroll-db"},
                }
            ],
        }
        records = policy_statement_records(snapshot["zpr_policies"][0], snapshot["snapshot_time"])

        findings = generate_findings(snapshot, records)
        types = {finding["finding_type"] for finding in findings}

        self.assertIn("broad_cidr_exception", types)
        self.assertIn("protected_resource_no_matching_policy", types)


if __name__ == "__main__":
    unittest.main()
