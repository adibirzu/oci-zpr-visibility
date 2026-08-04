"""Zero-row gating rules for the live dashboard validation run."""
import unittest

from oci_zpr_visibility import dashboard
from oci_zpr_visibility.validate_dashboards import _widget_status

FLOW_WIDGET = {"name": "KPI: Blocked flows", "data_dependency": dashboard.FLOW_DEPENDENCY}
INVENTORY_WIDGET = {"name": "KPI: Active policies"}
ALLOW_ZERO_WIDGET = {"name": "Collection gaps", "allow_zero": True}


class WidgetStatusTests(unittest.TestCase):
    def test_rows_always_count_as_data(self):
        self.assertEqual(_widget_status(3, FLOW_WIDGET, flow_configured=False), "DATA")
        self.assertEqual(_widget_status(3, INVENTORY_WIDGET, flow_configured=True), "DATA")

    def test_flow_widget_without_flow_collection_is_not_applicable(self):
        self.assertEqual(
            _widget_status(0, FLOW_WIDGET, flow_configured=False), "NOT_APPLICABLE"
        )

    def test_flow_widget_stays_strict_once_flow_collection_is_configured(self):
        self.assertEqual(_widget_status(0, FLOW_WIDGET, flow_configured=True), "ZERO")

    def test_inventory_widget_is_never_exempted_by_flow_state(self):
        self.assertEqual(_widget_status(0, INVENTORY_WIDGET, flow_configured=False), "ZERO")

    def test_explicit_allow_zero_still_wins(self):
        self.assertEqual(
            _widget_status(0, ALLOW_ZERO_WIDGET, flow_configured=True), "ZERO_ALLOWED"
        )


if __name__ == "__main__":
    unittest.main()
