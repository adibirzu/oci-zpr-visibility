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
            _rec("zpr_enriched_flow", classification="unexpected_accepted"),
            _rec("zpr_enriched_flow", classification="suspected_misconfiguration"),
            _rec("zpr_enriched_flow", classification="expected_accepted"),
            _rec("zpr_policy_statement"),
        ]
        m = build_metric_values(records)
        self.assertEqual(m["findings_critical_high"], 2)
        self.assertEqual(m["findings_total"], 3)
        self.assertEqual(m["flows_unexpected_accepted"], 1)
        self.assertEqual(m["flows_suspected_misconfiguration"], 1)
        self.assertEqual(m["heartbeat"], 1)

    def test_empty_records_zeroed_with_heartbeat(self):
        m = build_metric_values([])
        self.assertEqual(m["findings_critical_high"], 0)
        self.assertEqual(m["flows_unexpected_accepted"], 0)
        self.assertEqual(m["heartbeat"], 1)


if __name__ == "__main__":
    unittest.main()
