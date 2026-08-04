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

    def test_dashboard_exposes_trust_and_collection_health(self):
        by_name = {w["name"]: w for w in dashboard.iter_widgets(self.dash)}
        self.assertIn("Flow review trend", by_name)
        self.assertIn("Latest visibility runs", by_name)
        self.assertIn("Explicit resource coverage gaps", by_name)
        self.assertIn("correlation_confidence", by_name["Accepted flows requiring policy review"]["query"])
        self.assertIn("zpr_attribution", by_name["Rejected protected destinations"]["query"])
        self.assertEqual(by_name["Flow path link (src to dst)"]["visualization_type"], "link")

    def test_flow_decision_tables_carry_enforcement_honesty_qualifiers(self):
        # zpr_attribution is always INFERRED_NOT_PROVIDER_VERDICT: ZPR emits no
        # decision log, so an allow/reject row is inferred from VCN flow logs.
        # Every per-flow table must show that qualifier next to the decision,
        # otherwise a reader takes the row as a ZPR enforcement verdict.
        for w in dashboard.iter_widgets(self.dash):
            if w.get("visualization_type") != "table":
                continue
            q = w["query"]
            if "record_type = 'zpr_enriched_flow'" not in q:
                continue
            self.assertIn("zpr_attribution", q, f"{w['name']} omits zpr_attribution")
            self.assertIn(
                "correlation_confidence", q, f"{w['name']} omits correlation_confidence"
            )

    def test_customer_queries_use_review_classification_for_inferred_flows(self):
        for name in (
            "KPI: Accepted for policy review",
            "Accepted flows requiring policy review",
            "DET: Accepted policy review",
            "DET: Rejected expected allow",
        ):
            self.assertIn("review_classification", {
                w["name"]: w for w in dashboard.iter_widgets(self.dash)
            }[name]["query"])

    def test_zero_result_states_are_explicit_not_implicit(self):
        allowed = {
            w["name"] for w in dashboard.iter_widgets(self.dash) if w.get("allow_zero")
        }
        self.assertEqual(
            allowed,
            {"Detection: rejected expected allow (ZPR-Rejected-Expected-Allow)", "Collection gaps"},
        )

    def test_flow_dependent_widgets_declare_their_dependency(self):
        """Without the marker, a tenancy that never enabled VCN flow logs would
        fail the live gate on widgets that cannot have data."""
        for w in dashboard.iter_widgets(self.dash):
            if dashboard.FLOW_RECORD_TYPE in w["query"]:
                self.assertEqual(
                    w.get("data_dependency"), dashboard.FLOW_DEPENDENCY, w["name"]
                )

    def test_unknown_data_dependency_is_a_schema_error(self):
        dash = {"tabs": [{"name": "t", "widgets": [{
            "name": "w", "query": "'Log Source' = 'OCI ZPR Visibility JSON'",
            "visualization_type": "table", "layout": {"width": 6, "height": 2},
            "data_dependency": "weather",
        }]}]}
        self.assertTrue(any("data_dependency" in e for e in dashboard.validate_dashboard(dash)))


if __name__ == "__main__":
    unittest.main()
