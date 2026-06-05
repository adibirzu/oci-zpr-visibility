"""Schema + layout invariants for the OCI ZPR dashboard descriptor."""
import unittest

from oci_zpr_visibility import dashboard


class DashboardSchemaTests(unittest.TestCase):
    def setUp(self):
        self.dash = dashboard.load_dashboard()

    def test_every_widget_has_query_and_valid_visualization(self):
        errors = dashboard.validate_dashboard(self.dash)
        self.assertEqual(errors, [], f"dashboard schema errors: {errors}")

    def test_widget_widths_in_grid_and_heights_positive(self):
        for w in dashboard.iter_widgets(self.dash):
            layout = w.get("layout", {})
            self.assertIn(layout.get("width"), range(1, 13), f"{w['name']} width")
            self.assertGreater(layout.get("height", 0), 0, f"{w['name']} height")

    def test_resolved_layout_has_no_overlaps(self):
        placed = dashboard.resolve_layout(dashboard.iter_widgets(self.dash))
        for i, a in enumerate(placed):
            for b in placed[i + 1:]:
                overlap = not (
                    a["column"] + a["width"] <= b["column"]
                    or b["column"] + b["width"] <= a["column"]
                    or a["row"] + a["height"] <= b["row"]
                    or b["row"] + b["height"] <= a["row"]
                )
                self.assertFalse(overlap, f"overlap: {a['name']} vs {b['name']}")

    def test_queries_target_provisioned_source(self):
        for w in dashboard.iter_widgets(self.dash):
            self.assertIn("OCI ZPR Visibility JSON", w["query"], f"{w['name']} log source")

    def test_table_widgets_are_record_tables_not_stats(self):
        # The OCI LA console appends raw system fields (time,id,...) to ANY
        # table widget. After a `stats` aggregation those fields don't exist ->
        # 400 "Invalid field for FIELDS after STATS: Time" (kills the widget).
        # Per the working-dashboard pattern, table widgets must be raw-record
        # tables: a `| fields ...` projection with NO `stats`. Aggregations
        # belong in chart viz types (bar/hbar/sunburst).
        import re
        for w in dashboard.iter_widgets(self.dash):
            if w.get("visualization_type") != "table":
                continue
            q = w["query"]
            self.assertNotIn(
                "| stats", q,
                f"{w['name']} is a table but uses stats; use a chart or raw fields",
            )
            last = q.split("|")[-1].strip()
            self.assertTrue(
                re.match(r"fields\b", last),
                f"{w['name']} table query must end in `fields`, ends in: {last!r}",
            )

    def test_no_field_to_field_filter_after_stats(self):
        # OCI LA rejects comparing two aggregate fields in a post-stats `where`
        # ("Invalid filter FIELDS after STATS"). Drift is computed server-side
        # and emitted as zpr_policy_drift records; widgets must read those.
        import re
        for w in dashboard.iter_widgets(self.dash):
            q = w["query"]
            after = re.split(r"\|\s*stats\b", q, maxsplit=1)
            if len(after) == 2 and "| where" in after[1]:
                # a post-stats where comparing two bare field names is illegal
                self.assertNotRegex(
                    after[1],
                    r"where\s+[A-Za-z_]\w*\s*!?=\s*[A-Za-z_]\w*\s*$",
                    f"{w['name']} has a field-to-field filter after stats",
                )


if __name__ == "__main__":
    unittest.main()
