"""Unit tests for the management-dashboard builder (no live OCI)."""
import unittest

from oci_zpr_visibility import dashboard, deploy_dashboard

FAKE_CMPT = "ocid1.tenancy.oc1..fake"


class BuildManagementDashboardTests(unittest.TestCase):
    def setUp(self):
        self.dash = dashboard.load_dashboard()
        self.built = deploy_dashboard.build_management_dashboard(
            self.dash, compartment_id=FAKE_CMPT, display_name="OCI ZPR Visibility"
        )

    def test_one_tile_and_saved_search_per_widget(self):
        n = len(dashboard.iter_widgets(self.dash))
        self.assertEqual(len(self.built["tiles"]), n)
        self.assertEqual(len(self.built["savedSearches"]), n)

    def test_tiles_reference_existing_saved_searches(self):
        ss_ids = {s["id"] for s in self.built["savedSearches"]}
        for tile in self.built["tiles"]:
            self.assertIn(tile["savedSearchId"], ss_ids)
            for key in ("row", "column", "width", "height"):
                self.assertIn(key, tile)

    def test_saved_search_carries_query_and_viz(self):
        for s in self.built["savedSearches"]:
            ui = s["uiConfig"]
            self.assertTrue(ui["queryString"])
            self.assertIn("OCI ZPR Visibility JSON", ui["queryString"])
            self.assertTrue(ui["visualizationType"])

    def test_compartment_propagated(self):
        self.assertEqual(self.built["compartmentId"], FAKE_CMPT)
        for s in self.built["savedSearches"]:
            self.assertEqual(s["compartmentId"], FAKE_CMPT)


if __name__ == "__main__":
    unittest.main()
