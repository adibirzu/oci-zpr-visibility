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


if __name__ == "__main__":
    unittest.main()
