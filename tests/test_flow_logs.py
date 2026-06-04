import unittest

from oci_zpr_visibility.correlate import correlate_flow_records
from oci_zpr_visibility.flow_logs import normalize_flow_log_record


class NormalizeFlowLogTests(unittest.TestCase):
    def test_unwraps_log_content(self):
        raw = {"data": {"logContent": {
            "data": {"action": "REJECT", "sourceAddress": "10.0.1.10",
                     "destinationAddress": "10.0.2.20", "destinationPort": 1521,
                     "protocolName": "TCP"},
            "time": "2026-06-04T10:00:00Z", "id": "abc"}}}
        norm = normalize_flow_log_record(raw)
        self.assertEqual(norm["data"]["action"], "REJECT")
        self.assertEqual(norm["data"]["sourceAddress"], "10.0.1.10")
        self.assertEqual(norm["time"], "2026-06-04T10:00:00Z")

    def test_normalized_record_feeds_correlate(self):
        snapshot = {
            "snapshot_time": "2026-06-04T00:00:00Z",
            "ip_resource_map": [
                {"private_ip": "10.0.1.10", "resource_id": "web", "normalized_security_attributes": {"app": "web"}},
                {"private_ip": "10.0.2.20", "resource_id": "db", "normalized_security_attributes": {"app": "db"}},
            ],
            "zpr_policies": [],
        }
        raw = {"data": {"logContent": {"data": {
            "action": "ACCEPT", "sourceAddress": "10.0.1.10",
            "destinationAddress": "10.0.2.20"}, "time": "2026-06-04T10:00:00Z"}}}
        norm = normalize_flow_log_record(raw)
        enriched = correlate_flow_records([norm], snapshot, [])
        self.assertEqual(enriched[0]["source_ip"], "10.0.1.10")
        self.assertEqual(enriched[0]["destination_resource_id"], "db")

    def test_passthrough_when_already_flat(self):
        raw = {"data": {"action": "ACCEPT", "sourceAddress": "1.1.1.1"}, "time": "t"}
        norm = normalize_flow_log_record(raw)
        self.assertEqual(norm["data"]["action"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
