import unittest
from types import SimpleNamespace
from unittest import mock

from oci_zpr_visibility.collector import ZprCollector


class _Pagination:
    @staticmethod
    def list_call_get_all_results(fn, *args, **kwargs):
        return SimpleNamespace(data=fn(*args, **kwargs))


class _Session:
    oci = SimpleNamespace(pagination=_Pagination())
    tenancy_id = "tenancy"
    region = "eu-frankfurt-1"


class ExtendedCollectorTests(unittest.TestCase):
    def test_explicit_scope_rejects_empty_or_blank_ids(self):
        with self.assertRaises(ValueError):
            ZprCollector(_Session(), compartment_ids=[])
        with self.assertRaises(ValueError):
            ZprCollector(_Session(), compartment_ids=["  "])

    def test_oke_cluster_denial_marks_node_pool_partial(self):
        collector = ZprCollector(_Session(), compartment_ids=["comp"])
        with mock.patch("oci_zpr_visibility.collector.client", side_effect=PermissionError("denied")):
            collector._collect_extended_inventory()
        self.assertIn("oke_cluster", collector.coverage_failures)
        self.assertIn("oke_node_pool", collector.coverage_failures)

    def test_oke_and_autonomous_database_inventory_preserves_provider_fields(self):
        cluster = SimpleNamespace(id="ocid.cluster", name="cluster", compartment_id="comp",
                                  lifecycle_state="ACTIVE", vcn_id="ocid.vcn")
        pool = SimpleNamespace(id="ocid.pool", name="pool", compartment_id="comp",
                               cluster_id="ocid.cluster", lifecycle_state="NEEDS_ATTENTION",
                               subnet_ids=["ocid.subnet"])
        db = SimpleNamespace(id="ocid.db", display_name="db", compartment_id="comp",
                             lifecycle_state="AVAILABLE", subnet_id="ocid.dbsubnet",
                             availability_domain="AD-1",
                             security_attributes={"oracle-zpr": {"app": {"value": "db"}}})
        oke = SimpleNamespace(
            list_clusters=lambda cid: [cluster],
            list_node_pools=lambda cid, cluster_id=None: [pool],
        )
        database = SimpleNamespace(list_autonomous_databases=lambda cid: [db])
        collector = ZprCollector(_Session(), compartment_ids=["comp"])
        network = SimpleNamespace(get_subnet=lambda sid: SimpleNamespace(data=SimpleNamespace(vcn_id="ocid.dbvcn")))
        with mock.patch("oci_zpr_visibility.collector.client", side_effect=[oke, database, network]):
            rows = collector._collect_extended_inventory()

        by_type = {row["resource_type"]: row for row in rows}
        self.assertEqual(by_type["oke_cluster"]["vcn_id"], "ocid.vcn")
        self.assertEqual(by_type["oke_node_pool"]["subnet_ids"], ["ocid.subnet"])
        self.assertEqual(by_type["oke_node_pool"]["vcn_id"], "ocid.vcn")
        self.assertEqual(by_type["autonomous_database"]["vcn_id"], "ocid.dbvcn")
        self.assertEqual(by_type["oke_node_pool"]["protection_status"], "ATTRIBUTE_EVIDENCE_UNAVAILABLE")
        self.assertEqual(by_type["autonomous_database"]["security_attributes"]["oracle-zpr"]["app"]["value"], "db")
        self.assertEqual(by_type["autonomous_database"]["protection_status"], "ATTRIBUTES_PRESENT")

    def test_deleted_inventory_is_tombstone_and_excluded_from_live_counts(self):
        deleted = SimpleNamespace(id="gone", name="gone", lifecycle_state="DELETED")
        oke = SimpleNamespace(list_clusters=lambda cid: [deleted], list_node_pools=lambda *a, **k: [])
        database = SimpleNamespace(list_autonomous_databases=lambda cid: [])
        collector = ZprCollector(_Session(), compartment_ids=["comp"])
        with mock.patch("oci_zpr_visibility.collector.client", side_effect=[oke, database]):
            rows = collector._collect_extended_inventory()
        self.assertEqual(rows[0]["inventory_status"], "TERMINAL")
        self.assertEqual(rows[0]["protection_status"], "ATTRIBUTE_EVIDENCE_UNAVAILABLE")
        self.assertEqual(collector.coverage_counts["oke_cluster"], {"eligible": 0, "available": 0})

    def test_active_to_terminal_observations_keep_latest_state_without_live_count(self):
        active = SimpleNamespace(id="db", display_name="db", compartment_id="comp",
                                 lifecycle_state="AVAILABLE", security_attributes={"ns": {"key": {"value": "v"}}})
        terminal = SimpleNamespace(id="db", display_name="db", compartment_id="comp",
                                   lifecycle_state="TERMINATED", security_attributes={"ns": {"key": {"value": "v"}}})
        database = SimpleNamespace(list_autonomous_databases=lambda cid: [active, terminal])
        oke = SimpleNamespace(list_clusters=lambda cid: [], list_node_pools=lambda *a, **k: [])
        collector = ZprCollector(_Session(), compartment_ids=["comp"])
        with mock.patch("oci_zpr_visibility.collector.client", side_effect=[oke, database]):
            rows = collector._collect_extended_inventory()
        self.assertEqual([r["inventory_status"] for r in rows], ["OPERATIONAL", "TERMINAL"])
        self.assertEqual(collector.coverage_counts["autonomous_database"]["eligible"], 1)

    def test_service_failure_is_a_partial_collection_gap(self):
        collector = ZprCollector(_Session(), compartment_ids=["comp"])
        with mock.patch("oci_zpr_visibility.collector.client", side_effect=PermissionError("denied")):
            rows = collector._collect_extended_inventory()
        self.assertEqual(rows, [])
        self.assertTrue(any(r["resource_type"] == "oke_cluster" for r in collector.collection_errors))
        self.assertIn("autonomous_database", collector.coverage_failures)

if __name__ == "__main__":
    unittest.main()
