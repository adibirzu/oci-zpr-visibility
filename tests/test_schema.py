import unittest

from oci_zpr_visibility.schema import SCHEMA_VERSION, normalize_record, run_record


class SchemaTests(unittest.TestCase):
    def test_normalize_record_adds_evidence_envelope(self):
        record = normalize_record(
            {"record_type": "zpr_resource", "snapshot_time": "2026-01-01T00:00:00Z"},
            run_id="run-1",
            inventory_snapshot_time="2026-01-01T00:00:00Z",
        )
        self.assertEqual(record["schema_version"], SCHEMA_VERSION)
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["event_time"], "2026-01-01T00:00:00Z")
        self.assertEqual(record["inventory_snapshot_time"], "2026-01-01T00:00:00Z")

    def test_run_record_contains_health_counts_without_target_identity(self):
        record = run_record(
            run_id="run-1",
            event_time="2026-01-01T00:00:00Z",
            collection_status="SUCCEEDED",
            flow_collection_status="SKIPPED",
            record_count=4,
            finding_count=1,
            drift_count=0,
            flow_count=0,
        )
        self.assertEqual(record["record_type"], "zpr_run")
        self.assertEqual(record["record_count"], 4)
        self.assertNotIn("tenancy_id", record)
        self.assertNotIn("compartment_id", record)

    def test_missing_event_time_falls_back_to_inventory_snapshot(self):
        record = normalize_record(
            {"record_type": "zpr_enriched_flow", "event_time": None},
            run_id="run-1",
            inventory_snapshot_time="2026-01-01T00:00:00Z",
        )
        self.assertEqual(record["event_time"], "2026-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
