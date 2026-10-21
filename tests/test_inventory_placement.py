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


def test_unprotected_instance_inventory_includes_vnic_placement():
    instance = SimpleNamespace(
        id="ocid.instance", display_name="vm", compartment_id="comp",
        lifecycle_state="RUNNING", availability_domain="AD-1",
        fault_domain="FAULT-DOMAIN-2", security_attributes=None,
    )
    attachment = SimpleNamespace(vnic_id="ocid.vnic")
    vnic = SimpleNamespace(
        id="ocid.vnic", vcn_id="ocid.vcn", subnet_id="ocid.subnet",
        private_ip="10.0.0.2",
    )
    net = SimpleNamespace(list_vcns=lambda cid: [])
    compute = SimpleNamespace(
        list_instances=lambda cid: [instance],
        list_vnic_attachments=lambda compartment_id, instance_id=None: [attachment],
    )
    enriched_compute = SimpleNamespace(
        list_vnic_attachments=lambda compartment_id, instance_id=None: [attachment],
    )
    enriched_net = SimpleNamespace(
        get_vnic=lambda vnic_id: SimpleNamespace(data=vnic),
        list_private_ips=lambda vnic_id=None: [],
    )
    collector = ZprCollector(_Session(), compartment_ids=["comp"])
    with mock.patch(
        "oci_zpr_visibility.collector.client",
        side_effect=[net, compute, enriched_compute, enriched_net],
    ):
        rows = collector._collect_resources(None)
    inventory = collector._base_inventory
    assert rows == []
    assert inventory[0]["private_ip"] == "10.0.0.2"
    assert inventory[0]["vcn_id"] == "ocid.vcn"
    assert inventory[0]["subnet_id"] == "ocid.subnet"
    assert inventory[0]["fault_domain"] == "FAULT-DOMAIN-2"


def test_real_vnic_shape_resolves_vcn_from_subnet_and_caches_lookup():
    # OCI Vnic has subnet_id but no vcn_id; preserve both protected/inventory rows.
    vnic = SimpleNamespace(subnet_id='subnet', private_ip='10.0.0.2')
    get_subnet = mock.Mock(return_value=SimpleNamespace(data=SimpleNamespace(vcn_id='vcn')))
    network = SimpleNamespace(get_vnic=lambda vid: SimpleNamespace(data=vnic),
                              get_subnet=get_subnet, list_private_ips=lambda **k: [])
    compute = SimpleNamespace(list_vnic_attachments=lambda *a, **k: [SimpleNamespace(vnic_id='vnic')])
    collector = ZprCollector(_Session(), compartment_ids=['comp'])
    resource = {'resource_type': 'instance', 'resource_id': 'vm', 'compartment_id': 'comp'}
    with mock.patch('oci_zpr_visibility.collector.client', side_effect=[compute, network]):
        rows = collector._enrich_compute_vnics([resource, resource])
    assert all(row['vcn_id'] == 'vcn' and row['private_ip'] == '10.0.0.2' for row in rows)
    get_subnet.assert_called_once_with('subnet')
