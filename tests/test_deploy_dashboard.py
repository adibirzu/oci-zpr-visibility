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

    def test_scope_filters_is_object_not_array(self):
        # JET crashes if scopeFilters is a list; it must be an object with a
        # LogGroup scope rooted at the compartment (matches a working OCI LA
        # dashboard export). An empty list triggers "reading 'localName'".
        for s in self.built["savedSearches"]:
            scope = s["uiConfig"]["scopeFilters"]
            self.assertIsInstance(scope, dict)
            self.assertIn("LogGroup", scope)
            self.assertEqual(
                scope["LogGroup"]["values"][0]["value"], FAKE_CMPT
            )
            self.assertIn("filters", scope)

    def test_time_selection_uses_la_format(self):
        # OCI LA expects its own "l30d" token, not ISO-8601 "P30D".
        for s in self.built["savedSearches"]:
            self.assertEqual(
                s["uiConfig"]["timeSelection"]["timePeriod"], "l30d"
            )

    def test_visualization_options_non_empty(self):
        # An empty visualizationOptions object breaks JET viz binding.
        for s in self.built["savedSearches"]:
            opts = s["uiConfig"]["visualizationOptions"]
            self.assertIsInstance(opts, dict)
            self.assertTrue(opts, f"empty viz options for {s['displayName']}")

    def test_compartment_propagated(self):
        self.assertEqual(self.built["compartmentId"], FAKE_CMPT)
        for s in self.built["savedSearches"]:
            self.assertEqual(s["compartmentId"], FAKE_CMPT)


if __name__ == "__main__":
    unittest.main()
