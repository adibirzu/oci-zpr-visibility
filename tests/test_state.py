import unittest

from oci_zpr_visibility.state import compute_drift


def _stmt(pid, statement, h, index=0, snapshot="2026-01-01T00:00:00Z"):
    return {
        "record_type": "zpr_policy_statement",
        "policy_id": pid,
        "policy_name": "policy-placeholder",
        "statement": statement,
        "statement_hash": h,
        "statement_index": index,
        "snapshot_time": snapshot,
    }


class ComputeDriftTests(unittest.TestCase):
    def test_no_drift_when_hashes_match(self):
        prev = [_stmt("p1", "allow a to b", "h1")]
        curr = [_stmt("p1", "allow a to b", "h1")]
        self.assertEqual(compute_drift(prev, curr), [])

    def test_detects_changed_hash(self):
        prev = [_stmt("p1", "allow a to b", "h1")]
        curr = [_stmt("p1", "allow a to c", "h2", snapshot="2026-01-02T00:00:00Z")]
        drift = compute_drift(prev, curr)
        self.assertEqual(len(drift), 1)
        d = drift[0]
        self.assertEqual(d["record_type"], "zpr_policy_drift")
        self.assertEqual(d["change_type"], "MODIFIED")
        self.assertEqual((d["policy_id"], d["old_hash"], d["new_hash"]), ("p1", "h1", "h2"))
        self.assertEqual(d["old_statement"], "allow a to b")
        self.assertEqual(d["new_statement"], "allow a to c")
        self.assertEqual(d["event_time"], "2026-01-02T00:00:00Z")

    def test_new_statement_is_reported(self):
        prev = []
        curr = [_stmt("p1", "allow a to b", "h1")]
        drift = compute_drift(prev, curr)
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["change_type"], "ADDED")

    def test_removed_statement_is_reported(self):
        drift = compute_drift([_stmt("p1", "allow a to b", "h1")], [])
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["change_type"], "REMOVED")

    def test_ignores_non_policy_records(self):
        prev = [{"record_type": "zpr_finding", "policy_id": "p1"}]
        curr = [{"record_type": "zpr_finding", "policy_id": "p1"}]
        self.assertEqual(compute_drift(prev, curr), [])

    def test_statement_reordering_is_not_drift(self):
        prev = [_stmt("p1", "allow a to b", "h1", 0), _stmt("p1", "allow c to d", "h2", 1)]
        curr = [_stmt("p1", "allow c to d", "h2", 0), _stmt("p1", "allow a to b", "h1", 1)]
        self.assertEqual(compute_drift(prev, curr), [])

    def test_inserted_statement_is_added_not_multiple_modifications(self):
        prev = [_stmt("p1", "allow a to b", "h1", 0), _stmt("p1", "allow c to d", "h2", 1)]
        curr = [
            _stmt("p1", "allow x to y", "h3", 0),
            _stmt("p1", "allow a to b", "h1", 1),
            _stmt("p1", "allow c to d", "h2", 2),
        ]
        drift = compute_drift(prev, curr)
        self.assertEqual([(event["change_type"], event["new_hash"]) for event in drift], [("ADDED", "h3")])


if __name__ == "__main__":
    unittest.main()
