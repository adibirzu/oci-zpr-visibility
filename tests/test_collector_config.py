import unittest
from unittest import mock

from oci_zpr_visibility import collector as collector_mod
from oci_zpr_visibility.collector import ZprCollector


class _FakeSession:
    """Minimal stand-in for OciSession (no cloud, no real SDK)."""

    oci = None
    tenancy_id = "ocid1.tenancy.oc1..fake"
    region = "eu-frankfurt-1"


class _RecordingZpr:
    def __init__(self) -> None:
        self.calls: dict = {}

    def get_configuration(self, **kwargs):
        self.calls = kwargs

        class _Resp:
            data = {"zpr_status": "ENABLED"}

        return _Resp()


class GetConfigurationTests(unittest.TestCase):
    def test_get_configuration_passes_tenancy_compartment(self):
        """The ZPR service returns 400 MissingParameter unless the root
        compartment_id is supplied. Reproduces the live cap-tenant failure."""
        fake_zpr = _RecordingZpr()
        session = _FakeSession()
        collector = ZprCollector(session)

        with mock.patch.object(collector_mod, "client", return_value=fake_zpr):
            result = collector._safe_get_configuration()

        self.assertEqual(fake_zpr.calls.get("compartment_id"), session.tenancy_id)
        self.assertEqual(result, {"zpr_status": "ENABLED"})


if __name__ == "__main__":
    unittest.main()
