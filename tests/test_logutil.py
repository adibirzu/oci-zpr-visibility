import contextlib
import io
import json
import unittest

from oci_zpr_visibility.logutil import emit


class EmitTests(unittest.TestCase):
    def _capture(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            emit(**kw)
        return buf.getvalue()

    def test_json_mode_emits_payload(self):
        out = self._capture(payload={"wrote": 3, "path": "x"}, human="Wrote 3 records", as_json=True)
        self.assertEqual(json.loads(out), {"wrote": 3, "path": "x"})

    def test_human_mode_emits_text(self):
        out = self._capture(payload={"wrote": 3}, human="Wrote 3 records", as_json=False)
        self.assertIn("Wrote 3 records", out)
        self.assertNotIn("{", out)


if __name__ == "__main__":
    unittest.main()
