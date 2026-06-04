"""OCI collection workflows for ZPR visibility."""

from __future__ import annotations

from typing import Any

from .jsonutil import to_plain, utc_now_iso
from .oci_clients import OciSession, client
from .policy_parser import policy_statement_records
from .security_attributes import flatten_security_attributes, render_attributes


def _list_all(oci: Any, func: Any, *args: Any, **kwargs: Any) -> list[Any]:
    return list(oci.pagination.list_call_get_all_results(func, *args, **kwargs).data)


def protected_resource_record(
    security_attributes: Any,
    *,
    resource_id: str | None,
    resource_name: str | None,
    resource_type: str,
    compartment_id: str | None,
    region: str | None,
    vcn_id: str | None = None,
    subnet_id: str | None = None,
) -> dict[str, Any] | None:
    """Build a zpr_resource-shaped record from a resource's security attributes.

    Returns None when the resource carries no security attributes (not protected).
    """
    attrs = flatten_security_attributes(security_attributes)
    if not attrs:
        return None
    record: dict[str, Any] = {
        "resource_id": resource_id,
        "resource_name": resource_name,
        "resource_type": resource_type,
        "compartment_id": compartment_id,
        "region": region,
        "security_attributes": security_attributes,
        "normalized_security_attributes": attrs,
    }
    if vcn_id:
        record["vcn_id"] = vcn_id
    if subnet_id:
        record["subnet_id"] = subnet_id
    return record


class ZprCollector:
    def __init__(self, session: OciSession) -> None:
        self.session = session
        self.oci = session.oci

    def enable_zpr(self, dry_run: bool = False) -> dict[str, Any]:
        zpr = client(self.session, "zpr.ZprClient")
        models = self.oci.zpr.models
        details = models.CreateConfigurationDetails(compartment_id=self.session.tenancy_id, zpr_status="ENABLED")
        response = zpr.create_configuration(details, opc_dry_run=dry_run)
        return to_plain(response.data)

    def collect(self, include_resources: bool = True, resource_query: str | None = None) -> dict[str, Any]:
        snapshot_time = utc_now_iso()
        snapshot: dict[str, Any] = {
            "snapshot_time": snapshot_time,
            "tenancy_id": self.session.tenancy_id,
            "region": self.session.region,
            "zpr_configuration": self._safe_get_configuration(),
            "zpr_policies": self._collect_policies(),
            "security_attribute_namespaces": [],
            "security_attributes": [],
            "resources": [],
            "ip_resource_map": [],
        }
        namespaces, attributes = self._collect_security_attributes()
        snapshot["security_attribute_namespaces"] = namespaces
        snapshot["security_attributes"] = attributes

        if include_resources:
            resources = self._collect_resources(resource_query)
            snapshot["resources"] = resources
            snapshot["ip_resource_map"] = self._build_ip_map(resources)

        return snapshot

    def records_for_snapshot(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        snapshot_time = str(snapshot["snapshot_time"])
        records: list[dict[str, Any]] = []
        for policy in snapshot.get("zpr_policies", []):
            records.extend(policy_statement_records(policy, snapshot_time))

        for resource in snapshot.get("resources", []):
            attrs = resource.get("normalized_security_attributes") or {}
            if not attrs:
                continue
            records.append(
                {
                    "record_type": "zpr_resource",
                    "snapshot_time": snapshot_time,
                    "resource_id": resource.get("resource_id"),
                    "resource_name": resource.get("resource_name"),
                    "resource_type": resource.get("resource_type"),
                    "compartment_id": resource.get("compartment_id"),
                    "region": resource.get("region"),
                    "vcn_id": resource.get("vcn_id"),
                    "subnet_id": resource.get("subnet_id"),
                    "vnic_id": resource.get("vnic_id"),
                    "private_ip": resource.get("private_ip"),
                    "security_attributes": ",".join(render_attributes(attrs)),
                }
            )
        return records

    def _safe_get_configuration(self) -> dict[str, Any] | None:
        zpr = client(self.session, "zpr.ZprClient")
        try:
            return to_plain(zpr.get_configuration(compartment_id=self.session.tenancy_id).data)
        except Exception as exc:  # OCI returns NotAuthorizedOrNotFound before ZPR onboarding in some tenancies.
            return {"error": exc.__class__.__name__, "message": str(exc)}

    def _collect_policies(self) -> list[dict[str, Any]]:
        zpr = client(self.session, "zpr.ZprClient")
        policies = _list_all(self.oci, zpr.list_zpr_policies, compartment_id=self.session.tenancy_id)
        full: list[dict[str, Any]] = []
        for policy in policies:
            policy_id = getattr(policy, "id", None)
            if not policy_id:
                full.append(to_plain(policy))
                continue
            full.append(to_plain(zpr.get_zpr_policy(policy_id).data))
        return full

    def _collect_security_attributes(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        sec = client(self.session, "security_attribute.SecurityAttributeClient")
        namespaces = _list_all(
            self.oci,
            sec.list_security_attribute_namespaces,
            compartment_id=self.session.tenancy_id,
            compartment_id_in_subtree=True,
        )
        namespace_records = [to_plain(item) for item in namespaces]
        attribute_records: list[dict[str, Any]] = []
        for namespace in namespaces:
            namespace_id = getattr(namespace, "id", None)
            namespace_name = getattr(namespace, "name", None)
            if not namespace_id:
                continue
            for attr in _list_all(self.oci, sec.list_security_attributes, namespace_id):
                record = to_plain(attr)
                record["namespace_id"] = namespace_id
                record["namespace_name"] = namespace_name
                attribute_records.append(record)
        return namespace_records, attribute_records

    def _compartment_ids(self) -> list[str]:
        """Tenancy root + all ACTIVE subtree compartments (best-effort)."""
        ids = [self.session.tenancy_id]
        try:
            identity = client(self.session, "identity.IdentityClient")
            ids += [
                c.id
                for c in _list_all(
                    self.oci, identity.list_compartments, self.session.tenancy_id,
                    compartment_id_in_subtree=True, access_level="ANY", lifecycle_state="ACTIVE",
                )
            ]
        except Exception:
            pass
        return ids

    def _collect_resources(self, query: str | None) -> list[dict[str, Any]]:
        """Enumerate ZPR-protectable resources (VCNs, instances) via Core APIs.

        Resource Search does not return securityAttributes, so the previous
        search-based discovery always found zero protected resources. Core
        list_vcns / list_instances DO return security_attributes.
        """
        net = client(self.session, "core.VirtualNetworkClient")
        compute = client(self.session, "core.ComputeClient")
        region = self.session.region
        resources: list[dict[str, Any]] = []
        for cid in self._compartment_ids():
            try:
                for vcn in _list_all(self.oci, net.list_vcns, cid):
                    rec = protected_resource_record(
                        getattr(vcn, "security_attributes", None),
                        resource_id=vcn.id, resource_name=vcn.display_name, resource_type="Vcn",
                        compartment_id=cid, region=region, vcn_id=vcn.id,
                    )
                    if rec:
                        resources.append(rec)
            except Exception:
                pass
            try:
                for inst in _list_all(self.oci, compute.list_instances, cid):
                    rec = protected_resource_record(
                        getattr(inst, "security_attributes", None),
                        resource_id=inst.id, resource_name=inst.display_name, resource_type="instance",
                        compartment_id=cid, region=region,
                    )
                    if rec:
                        resources.append(rec)
            except Exception:
                pass
        return self._enrich_compute_vnics(resources)

    def _enrich_compute_vnics(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compute = client(self.session, "core.ComputeClient")
        network = client(self.session, "core.VirtualNetworkClient")
        enriched: list[dict[str, Any]] = []
        for resource in resources:
            if str(resource.get("resource_type", "")).lower() not in {"instance", "computeinstance"}:
                enriched.append(resource)
                continue
            compartment_id = resource.get("compartment_id")
            instance_id = resource.get("resource_id")
            if not compartment_id or not instance_id:
                enriched.append(resource)
                continue
            try:
                attachments = _list_all(self.oci, compute.list_vnic_attachments, compartment_id, instance_id=instance_id)
                if not attachments:
                    enriched.append(resource)
                    continue
                for attachment in attachments:
                    vnic_id = getattr(attachment, "vnic_id", None)
                    if not vnic_id:
                        continue
                    vnic = network.get_vnic(vnic_id).data
                    private_ips = _list_all(self.oci, network.list_private_ips, vnic_id=vnic_id)
                    for private_ip in private_ips or [None]:
                        enriched.append(
                            {
                                **resource,
                                "vnic_id": vnic_id,
                                "subnet_id": getattr(vnic, "subnet_id", None),
                                "private_ip": getattr(private_ip, "ip_address", None) if private_ip else getattr(vnic, "private_ip", None),
                            }
                        )
            except Exception:
                enriched.append(resource)
        return enriched

    def _build_ip_map(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapped: list[dict[str, Any]] = []
        for resource in resources:
            private_ip = resource.get("private_ip")
            if not private_ip:
                continue
            mapped.append(
                {
                    "private_ip": private_ip,
                    "vnic_id": resource.get("vnic_id"),
                    "subnet_id": resource.get("subnet_id"),
                    "resource_id": resource.get("resource_id"),
                    "resource_name": resource.get("resource_name"),
                    "resource_type": resource.get("resource_type"),
                    "compartment_id": resource.get("compartment_id"),
                    "region": resource.get("region"),
                    "normalized_security_attributes": resource.get("normalized_security_attributes") or {},
                }
            )
        return mapped
