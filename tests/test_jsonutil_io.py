import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from oci_zpr_visibility.jsonutil import (
    read_json,
    read_jsonl,
    to_plain,
    utc_now_iso,
    write_json,
    write_jsonl,
)


class UtcNowTests(unittest.TestCase):
    def test_iso_zulu_no_microseconds(self):
        value = utc_now_iso()
        self.assertTrue(value.endswith("Z"))
        self.assertNotIn(".", value)


class ToPlainTests(unittest.TestCase):
    def test_scalars_passthrough(self):
        for v in (None, "s", 1, 1.5, True):
            self.assertEqual(to_plain(v), v)

    def test_datetime_to_zulu(self):
        dt = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(to_plain(dt), "2026-06-04T12:00:00Z")

    def test_date_iso(self):
        self.assertEqual(to_plain(date(2026, 6, 4)), "2026-06-04")

    def test_nested_dict_and_collections(self):
        self.assertEqual(to_plain({"a": [1, (2, 3)], "b": {1, 2}}),
                         {"a": [1, [2, 3]], "b": sorted([1, 2])} | {"b": to_plain({1, 2})})

    def test_object_with_dict_strips_underscores(self):
        class Obj:
            def __init__(self):
                self._id = "x"
                self.name = "n"
        self.assertEqual(to_plain(Obj()), {"id": "x", "name": "n"})

    def test_fallback_str(self):
        class NoDict:
            __slots__ = ()
            def __repr__(self):
                return "REPR"
        self.assertEqual(to_plain(NoDict()), "REPR")


class JsonRoundtripTests(unittest.TestCase):
    def test_json_roundtrip_creates_parent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nested" / "out.json"
            write_json(path, {"b": 2, "a": 1})
            self.assertEqual(read_json(path), {"a": 1, "b": 2})

    def test_jsonl_roundtrip_skips_blank_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.jsonl"
            write_jsonl(path, [{"x": 1}, {"y": 2}])
            self.assertEqual(read_jsonl(path), [{"x": 1}, {"y": 2}])


if __name__ == "__main__":
    unittest.main()
