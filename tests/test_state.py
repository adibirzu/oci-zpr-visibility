import unittest

from oci_zpr_visibility.state import compute_drift


def _stmt(pid, statement, h):
    return {"record_type": "zpr_policy_statement", "policy_id": pid, "statement": statement, "statement_hash": h}


class ComputeDriftTests(unittest.TestCase):
    def test_no_drift_when_hashes_match(self):
        prev = [_stmt("p1", "allow a to b", "h1")]
        curr = [_stmt("p1", "allow a to b", "h1")]
        self.assertEqual(compute_drift(prev, curr), [])

    def test_detects_changed_hash(self):
        prev = [_stmt("p1", "allow a to b", "h1")]
        curr = [_stmt("p1", "allow a to b", "h2")]
        drift = compute_drift(prev, curr)
        self.assertEqual(len(drift), 1)
        d = drift[0]
        self.assertEqual(d["record_type"], "zpr_policy_drift")
        self.assertEqual((d["policy_id"], d["old_hash"], d["new_hash"]), ("p1", "h1", "h2"))

    def test_new_statement_is_not_drift(self):
        prev = []
        curr = [_stmt("p1", "allow a to b", "h1")]
        self.assertEqual(compute_drift(prev, curr), [])

    def test_ignores_non_policy_records(self):
        prev = [{"record_type": "zpr_finding", "policy_id": "p1"}]
        curr = [{"record_type": "zpr_finding", "policy_id": "p1"}]
        self.assertEqual(compute_drift(prev, curr), [])


if __name__ == "__main__":
    unittest.main()
