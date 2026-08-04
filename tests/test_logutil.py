import contextlib
import io
import json
import unittest

from oci_zpr_visibility.logutil import describe_exception, emit


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


class DescribeExceptionTests(unittest.TestCase):
    class _ServiceError(Exception):
        status = 404
        code = "NotAuthorizedOrNotFound"
        operation_name = "list_management_dashboards"

        def __str__(self):
            return (
                "Authorization failed for ocid1.tenancy.oc1..aaaa on vcn 'prod-web' "
                "at 10.0.1.7 (opc-request-id: ABC123)"
            )

    def test_service_error_keeps_actionable_status_and_code(self):
        described = describe_exception(self._ServiceError())
        self.assertIn("status=404", described)
        self.assertIn("code=NotAuthorizedOrNotFound", described)
        self.assertIn("operation=list_management_dashboards", described)

    def test_service_error_drops_the_raw_message(self):
        described = describe_exception(self._ServiceError())
        for secret in ("ocid1.tenancy", "prod-web", "10.0.1.7", "ABC123", "Authorization failed"):
            self.assertNotIn(secret, described)

    def test_plain_exception_reduces_to_its_class(self):
        self.assertEqual(describe_exception(ValueError("tenancy-name")), "ValueError")

    def test_unexpected_code_shape_is_dropped(self):
        class _Weird(Exception):
            code = "denied for vcn 'prod-web' at 10.0.1.7"

        self.assertEqual(describe_exception(_Weird()), "_Weird")


if __name__ == "__main__":
    unittest.main()
