"""Unit tests for the management-dashboard builder (no live OCI)."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from oci_zpr_visibility import dashboard, deploy_dashboard

FAKE_CMPT = "fake-compartment"


class ImportOwnershipTests(unittest.TestCase):
    def candidate(self):
        return {"displayName": "view", "dashboardId": "temporary", "freeformTags": {"platform": "oci-zpr-visibility"},
                "savedSearches": [{"id": "temporary-search", "displayName": "tile"}],
                "tiles": [{"savedSearchId": "temporary-search"}]}

    @patch("oci_zpr_visibility.deploy_dashboard.oci.pagination.list_call_get_all_results")
    def test_preserves_dashboard_and_search_ids_and_etag(self, listed):
        listed.return_value.data = [SimpleNamespace(dashboard_id="existing")]
        md = Mock()
        md.get_management_dashboard.return_value = SimpleNamespace(
            headers={"etag": "revision"}, data=SimpleNamespace(
                dashboard_id="existing", freeform_tags={"platform": "oci-zpr-visibility", "owner": "operator"},
                defined_tags={}, saved_searches=[SimpleNamespace(display_name="tile", id="existing-search")]))
        original = self.candidate()
        [(item, etag)] = deploy_dashboard.prepare_dashboard_imports(md, [original], FAKE_CMPT)
        self.assertEqual(item["dashboardId"], "existing")
        self.assertEqual(item["tiles"][0]["savedSearchId"], "existing-search")
        self.assertEqual(item["savedSearches"][0]["id"], "existing-search")
        self.assertEqual(item["freeformTags"]["owner"], "operator")
        self.assertEqual(etag, "revision")
        self.assertEqual(original["dashboardId"], "temporary")
        md.delete_management_dashboard.assert_not_called()

    @patch("oci_zpr_visibility.deploy_dashboard.oci.pagination.list_call_get_all_results")
    def test_refuses_ambiguous_names(self, listed):
        listed.return_value.data = [Mock(), Mock()]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            deploy_dashboard.prepare_dashboard_imports(Mock(), [self.candidate()], FAKE_CMPT)

    @patch("oci_zpr_visibility.deploy_dashboard.oci.pagination.list_call_get_all_results")
    def test_refuses_unowned_dashboard(self, listed):
        listed.return_value.data = [SimpleNamespace(dashboard_id="other")]
        md = Mock()
        md.get_management_dashboard.return_value.data.freeform_tags = {}
        with self.assertRaisesRegex(ValueError, "not owned"):
            deploy_dashboard.prepare_dashboard_imports(md, [self.candidate()], FAKE_CMPT)

    @patch("oci_zpr_visibility.deploy_dashboard.oci.pagination.list_call_get_all_results")
    def test_missing_dashboard_is_additive(self, listed):
        listed.return_value.data = []
        [(item, etag)] = deploy_dashboard.prepare_dashboard_imports(Mock(), [self.candidate()], FAKE_CMPT)
        self.assertEqual(item["dashboardId"], "temporary")
        self.assertIsNone(etag)


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
        # OCI LA expects its own relative-time token (e.g. "l60m"), not ISO "P30D".
        for s in self.built["savedSearches"]:
            self.assertEqual(
                s["uiConfig"]["timeSelection"]["timePeriod"], "l60m"
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

    def test_suite_builds_one_dashboard_per_logical_view(self):
        suite = deploy_dashboard.build_management_dashboards(self.dash, FAKE_CMPT)
        self.assertEqual(len(suite), len(self.dash["tabs"]))
        self.assertEqual(sum(len(item["tiles"]) for item in suite), len(dashboard.iter_widgets(self.dash)))
        self.assertEqual(suite[0]["displayName"], "OCI ZPR Visibility")
        self.assertEqual(len({item["dashboardId"] for item in suite}), len(suite))


if __name__ == "__main__":
    unittest.main()


def test_builder_can_bind_every_search_to_exact_log_group():
    suite = deploy_dashboard.build_management_dashboards(dashboard.load_dashboard(), FAKE_CMPT, log_group_id='expected-group')
    for d in suite:
        for search in d['savedSearches']:
            assert "and 'Log Group' = 'expected-group'" in search['uiConfig']['queryString'].split('|', 1)[0]
