"""Contracts for the native OCI resource-estate dashboard view."""

import unittest

from oci_zpr_visibility import dashboard
from oci_zpr_visibility.provision_la import FIELD_TOKENS


class DashboardEstateTests(unittest.TestCase):
    def setUp(self):
        self.by_name = {
            widget["name"]: widget
            for widget in dashboard.iter_widgets(dashboard.load_dashboard())
        }

    def test_estate_widgets_cover_inventory_context(self):
        expected = {
            "Last observed inventory by family and lifecycle",
            "Last observed resource placement",
            "Last observed protection evidence",
            "Inventory collection gaps",
            "Inventory snapshot freshness",
            "Last observed inventory lifecycle",
        }
        self.assertTrue(expected <= self.by_name.keys())
        for name in expected:
            self.assertIn("OCI ZPR Visibility JSON", self.by_name[name]["query"])

    def test_inventory_aggregations_use_latest_observation_per_resource(self):
        for name in (
            "Last observed inventory by family and lifecycle",
            "Last observed inventory lifecycle",
        ):
            query = self.by_name[name]["query"]
            self.assertIn("record_type = 'resource_inventory'", query)
            self.assertIn("by resource_id, inventory_snapshot_time", query)
            self.assertIn("sort -inventory_snapshot_time | dedup resource_id", query)
            self.assertLess(query.index("| stats"), query.index("| dedup"))

    def test_freshness_uses_string_safe_latest_and_rows_expose_snapshot_time(self):
        freshness = self.by_name["Inventory snapshot freshness"]["query"]
        self.assertIn("latest(inventory_snapshot_time)", freshness)
        self.assertNotIn("max(inventory_snapshot_time)", freshness)
        for name in ("Last observed resource placement", "Last observed protection evidence"):
            self.assertIn("inventory_snapshot_time", self.by_name[name]["query"])

    def test_policy_table_preserves_statement_rows(self):
        query = self.by_name["Policy statement table"]["query"]
        self.assertIn("statement_hash, statement_index", query)
        self.assertIn("inventory_snapshot_time, run_id", query)
        self.assertNotIn("dedup", query)

    def test_observation_tables_keep_raw_fields_for_console_binding(self):
        for name in ("Last observed resource placement", "Last observed protection evidence"):
            widget = self.by_name[name]
            self.assertNotIn("| stats", widget['query'])
            self.assertIn("| fields", widget['query'])
            self.assertIn("run_id", widget['query'])
            self.assertIn("repeat", widget['description'].lower())

    def test_estate_fields_are_provisioned(self):
        required = {
            "lifecycle_state",
            "protection_status",
            "cluster_id",
            "subnet_ids",
            "availability_domain",
            "available_count",
        }
        self.assertTrue(required <= set(FIELD_TOKENS))

    def test_gap_view_is_an_explicit_collection_surface(self):
        widget = self.by_name["Inventory collection gaps"]
        self.assertIn("zpr_collection_gap", widget["query"])
        self.assertIn("'Operation'", widget["query"])


if __name__ == "__main__":
    unittest.main()
