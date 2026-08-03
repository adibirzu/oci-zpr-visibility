import unittest

from oci_zpr_visibility.metrics import build_metric_values


def _rec(rt, **kw):
    return {"record_type": rt, **kw}


class BuildMetricValuesTests(unittest.TestCase):
    def test_counts_by_category(self):
        records = [
            _rec("zpr_finding", severity="CRITICAL"),
            _rec("zpr_finding", severity="HIGH"),
            _rec("zpr_finding", severity="MEDIUM"),
            _rec("zpr_enriched_flow", review_classification="accepted_requires_policy_review"),
            _rec("zpr_enriched_flow", review_classification="rejected_policy_expected_allow"),
            _rec("zpr_enriched_flow", classification="expected_accepted"),
            _rec("zpr_collection_gap", error_category="ServiceError"),
            _rec("zpr_coverage", coverage_status="NOT_COLLECTED"),
            _rec("zpr_policy_statement"),
        ]
        m = build_metric_values(records)
        self.assertEqual(m["findings_critical_high"], 2)
        self.assertEqual(m["findings_total"], 3)
        self.assertEqual(m["flows_accepted_requires_policy_review"], 1)
        self.assertEqual(m["flows_rejected_policy_expected_allow"], 1)
        self.assertEqual(m["collection_errors"], 1)
        self.assertEqual(m["resource_coverage_gaps"], 1)
        self.assertEqual(m["heartbeat"], 1)

    def test_empty_records_zeroed_with_heartbeat(self):
        m = build_metric_values([])
        self.assertEqual(m["findings_critical_high"], 0)
        self.assertEqual(m["flows_accepted_requires_policy_review"], 0)
        self.assertEqual(m["heartbeat"], 1)

    def test_legacy_classification_is_counted_during_migration(self):
        values = build_metric_values([
            _rec("zpr_enriched_flow", classification="unexpected_accepted")
        ])
        self.assertEqual(values["flows_accepted_requires_policy_review"], 1)


if __name__ == "__main__":
    unittest.main()
