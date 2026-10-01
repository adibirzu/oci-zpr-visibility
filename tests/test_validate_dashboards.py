"""Zero-row gating rules for the live dashboard validation run."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import oci

from oci_zpr_visibility import dashboard
from oci_zpr_visibility.validate_dashboards import _widget_status, _count_rows, _count_indexed_records


def test_freshness_queries_are_compartment_scoped_and_include_subtree():
    client = Mock()
    client.query.return_value.data = SimpleNamespace(total_count=1, items=[])
    assert _count_rows(client, "namespace", oci.log_analytics.models,
                       {"tenancy": "root", "query_compartment": "deployment"},
                       None, "query") == 1
    details = client.query.call_args.kwargs["query_details"]
    assert details.compartment_id == "deployment"
    assert details.compartment_id_in_subtree is True


def test_freshness_uses_exact_aggregate_instead_of_capped_record_total():
    client = Mock()
    client.query.return_value.data = SimpleNamespace(
        total_count=1, items=[{"indexed_records": 1042}])
    assert _count_indexed_records(client, "namespace", oci.log_analytics.models,
                                 {"tenancy": "root", "query_compartment": "deployment"},
                                 None, "run") == 1042
    details = client.query.call_args.kwargs["query_details"]
    assert details.compartment_id == "deployment"
    assert details.compartment_id_in_subtree is True
    assert "stats count as indexed_records" in details.query_string

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
