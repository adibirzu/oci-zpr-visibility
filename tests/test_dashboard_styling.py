"""Color semantics + drill-down metadata for finding/flow widgets."""
import unittest

from oci_zpr_visibility import dashboard

SEVERITY_WIDGETS = {
    "Top findings", "KPI: Critical+High findings",
    "Missing policy findings", "Broad CIDR exceptions",
}
FLOW_WIDGETS = {
    "Enriched ACCEPT vs REJECT", "Flow path link (src to dst)",
    "Unexpected accepted flows", "Rejected protected destinations",
}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


class DashboardStylingTests(unittest.TestCase):
    def setUp(self):
        self.by_name = {w["name"]: w for w in dashboard.iter_widgets(dashboard.load_dashboard())}

    def test_severity_widgets_have_full_color_map(self):
        for name in SEVERITY_WIDGETS:
            opts = self.by_name[name].get("visualization_options", {})
            colors = opts.get("severity_colors", {})
            self.assertTrue(SEVERITIES <= set(colors), f"{name} missing severity colors: {colors}")

    def test_flow_widgets_have_classification_colors(self):
        for name in FLOW_WIDGETS:
            opts = self.by_name[name].get("visualization_options", {})
            self.assertIn("classification_colors", opts, f"{name} missing classification colors")

    def test_finding_and_flow_widgets_have_drilldown_prompt(self):
        for name in SEVERITY_WIDGETS | FLOW_WIDGETS:
            self.assertTrue(self.by_name[name].get("ask_ai_prompts"), f"{name} missing ask_ai_prompts")


if __name__ == "__main__":
    unittest.main()
