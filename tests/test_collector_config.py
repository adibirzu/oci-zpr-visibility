import unittest
from unittest import mock

from oci_zpr_visibility import collector as collector_mod
from oci_zpr_visibility.collector import ZPR_SUPPORTED_RESOURCE_TYPES, ZprCollector


class _FakeSession:
    """Minimal stand-in for OciSession (no cloud, no real SDK)."""

    oci = None
    tenancy_id = "fake-tenancy"
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
        compartment_id is supplied. Reproduces the live target failure."""
        fake_zpr = _RecordingZpr()
        session = _FakeSession()
        collector = ZprCollector(session)

        with mock.patch.object(collector_mod, "client", return_value=fake_zpr):
            result = collector._safe_get_configuration()

        self.assertEqual(fake_zpr.calls.get("compartment_id"), session.tenancy_id)
        self.assertEqual(result, {"zpr_status": "ENABLED"})


class CollectorCoverageTests(unittest.TestCase):
    def test_unimplemented_resource_types_are_explicit_coverage_gaps(self):
        collector = ZprCollector(_FakeSession())
        collector.coverage_counts = {"vcn": {"eligible": 3, "protected": 2}}
        records = collector._coverage_records("2026-01-01T00:00:00Z", True)
        by_type = {record["resource_type"]: record for record in records}
        self.assertEqual(set(by_type), set(ZPR_SUPPORTED_RESOURCE_TYPES))
        self.assertEqual(by_type["vcn"]["coverage_status"], "COLLECTED")
        self.assertEqual(by_type["vcn"]["protected_count"], 2)
        self.assertEqual(by_type["load_balancer"]["coverage_status"], "NOT_COLLECTED")
        self.assertIsNone(by_type["load_balancer"]["eligible_count"])

    def test_failed_implemented_collector_reports_partial_coverage(self):
        collector = ZprCollector(_FakeSession())
        collector.coverage_counts = {"vcn": {"eligible": 2, "protected": 1}}
        collector.coverage_failures = {"vcn"}
        records = collector._coverage_records("2026-01-01T00:00:00Z", True)
        by_type = {record["resource_type"]: record for record in records}
        self.assertEqual(by_type["vcn"]["coverage_status"], "PARTIAL")
        self.assertEqual(by_type["vcn"]["eligible_count"], 2)


if __name__ == "__main__":
    unittest.main()
