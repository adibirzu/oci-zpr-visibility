import unittest

from oci_zpr_visibility.jsonutil import to_plain


class _FakeOciModel:
    """Mimics an OCI SDK model: data in underscore-prefixed instance attrs,
    plus swagger_types/attribute_map metadata also set as instance attrs."""

    def __init__(self) -> None:
        self.swagger_types = {"id": "str", "zpr_status": "str"}
        self.attribute_map = {"id": "id", "zpr_status": "zprStatus"}
        self._id = "fake-zpr-configuration"
        self._zpr_status = "ENABLED"


class ToPlainTests(unittest.TestCase):
    def test_drops_oci_sdk_metadata(self):
        out = to_plain(_FakeOciModel())
        self.assertEqual(out, {"id": "fake-zpr-configuration", "zpr_status": "ENABLED"})
        self.assertNotIn("swagger_types", out)
        self.assertNotIn("attribute_map", out)


if __name__ == "__main__":
    unittest.main()
