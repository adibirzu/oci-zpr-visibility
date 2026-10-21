"""OCI collection workflows for ZPR visibility."""

from __future__ import annotations

from typing import Any

from .jsonutil import to_plain, utc_now_iso
from .oci_clients import OciSession, client
from .policy_parser import policy_statement_records
from .security_attributes import flatten_security_attributes, render_attributes


# Current OCI ZPR-supported resource families. Collectors are implemented first
# for VCN and Compute instance; remaining rows are emitted as explicit coverage
# gaps so a zero-resource KPI never implies full-tenancy coverage.
ZPR_SUPPORTED_RESOURCE_TYPES = (
    "bastion", "instance", "instance_configuration", "autonomous_database",
    "cloud_autonomous_vm_cluster", "cloud_vm_cluster", "database", "db_system",
    "exadb_vm_cluster", "private_endpoint", "mount_target", "functions_application",
    "goldengate_deployment", "goldengate_connection", "load_balancer",
    "mysql_db_system", "mysql_replica", "vcn", "vnic", "network_firewall",
    "network_load_balancer", "cache_cluster", "opensearch_cluster", "desktop_pool",
    "stream_pool",
)

# These services are inventory-only in this collector. Their rows deliberately
# use ``resource_inventory`` and never enter the protected-resource map.
INVENTORY_RESOURCE_TYPES = ("oke_cluster", "oke_node_pool", "autonomous_database")
_NON_OPERATIONAL_STATES = frozenset({"DELETED", "TERMINATED", "DELETING", "TERMINATING"})


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
    def __init__(self, session: OciSession, compartment_ids: list[str] | None = None) -> None:
        self.session = session
        self.oci = session.oci
        self.collection_errors: list[dict[str, Any]] = []
        self.collection_error_count = 0
        self.coverage_counts: dict[str, dict[str, int]] = {}
        self.coverage_failures: set[str] = set()
        self.compartment_scope_complete = True
        self._collection_error_index: dict[tuple[str, str, str | None, str], dict[str, Any]] = {}
        self._extended_inventory_attempted = False
        self._scope_cache: list[str] | None = None
        self._base_inventory: list[dict[str, Any]] = []
        # A caller may provide an explicit, already-authorized scope. This is
        # also useful for fixture tests and avoids silently broadening a run.
        if compartment_ids is None:
            self._explicit_compartment_ids: tuple[str, ...] | None = None
        else:
            cleaned = tuple(dict.fromkeys(str(cid).strip() for cid in compartment_ids))
            if not cleaned or any(not cid for cid in cleaned):
                raise ValueError("compartment_ids must contain at least one non-empty ID")
            self._explicit_compartment_ids = cleaned

    def enable_zpr(self, dry_run: bool = False) -> dict[str, Any]:
        zpr = client(self.session, "zpr.ZprClient")
        models = self.oci.zpr.models
        details = models.CreateConfigurationDetails(compartment_id=self.session.tenancy_id, zpr_status="ENABLED")
        response = zpr.create_configuration(details, opc_dry_run=dry_run)
        return to_plain(response.data)

    def collect(self, include_resources: bool = True, resource_query: str | None = None) -> dict[str, Any]:
        self.collection_errors = []
        self.collection_error_count = 0
        self.coverage_counts = {}
        self.coverage_failures = set()
        self.compartment_scope_complete = True
        self._collection_error_index = {}
        self._extended_inventory_attempted = False
        self._scope_cache = None
        self._base_inventory = []
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
            "resource_inventory": [],
            "ip_resource_map": [],
            "collection_errors": [],
            "collection_error_count": 0,
            "resource_coverage": [],
        }
        namespaces, attributes = self._collect_security_attributes()
        snapshot["security_attribute_namespaces"] = namespaces
        snapshot["security_attributes"] = attributes

        if include_resources:
            resources = self._collect_resources(resource_query)
            snapshot["resources"] = resources
            snapshot["ip_resource_map"] = self._build_ip_map(resources)
            snapshot["resource_inventory"] = [
                *getattr(self, "_base_inventory", []),
                *self._collect_extended_inventory(),
            ]

        snapshot["collection_errors"] = list(self.collection_errors)
        snapshot["collection_error_count"] = self.collection_error_count
        snapshot["resource_coverage"] = self._coverage_records(snapshot_time, include_resources)

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
        records.extend(
            {
                **row,
                "snapshot_time": row.get("snapshot_time", snapshot_time),
                "event_time": row.get("event_time", snapshot_time),
            }
            for row in snapshot.get("resource_inventory", [])
        )
        records.extend(snapshot.get("resource_coverage", []))
        records.extend(snapshot.get("collection_errors", []))
        return records

    def _collection_error(self, *, service: str, operation: str, resource_type: str | None, exc: Exception) -> None:
        """Record one collection gap, collapsing repeats of the same failure.

        These calls sit inside per-compartment and per-resource loops, so a
        least-privilege principal in a large tenancy would otherwise emit one
        HIGH record per denied call. Identical failures collapse into a single
        record carrying `occurrence_count`; `collection_error_count` keeps the
        true total for metrics and the run heartbeat.
        """
        now = utc_now_iso()
        if resource_type:
            self.coverage_failures.add(resource_type)
        self.collection_error_count += 1
        key = (service, operation, resource_type, exc.__class__.__name__)
        existing = self._collection_error_index.get(key)
        if existing is not None:
            existing["occurrence_count"] += 1
            return
        record = {
            "record_type": "zpr_collection_gap",
            "snapshot_time": now,
            "event_time": now,
            "severity": "HIGH",
            "collection_service": service,
            "collection_operation": operation,
            "resource_type": resource_type,
            "error_category": exc.__class__.__name__,
            "occurrence_count": 1,
            "recommendation": "Verify least-privilege read access and rerun collection.",
        }
        self._collection_error_index[key] = record
        self.collection_errors.append(record)

    def _coverage_records(self, snapshot_time: str, include_resources: bool) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        # A failed compartment enumeration means only the tenancy root was
        # scanned, so every implemented collector saw a partial tenancy even
        # when its own list calls all succeeded.
        scope_incomplete = not self.compartment_scope_complete
        coverage_types = list(dict.fromkeys(ZPR_SUPPORTED_RESOURCE_TYPES))
        if self._extended_inventory_attempted:
            coverage_types = list(dict.fromkeys((*coverage_types, *INVENTORY_RESOURCE_TYPES)))
        for resource_type in coverage_types:
            counts = self.coverage_counts.get(resource_type, {})
            implemented = resource_type in {"vcn", "instance", *INVENTORY_RESOURCE_TYPES}
            if not (include_resources and implemented):
                status = "NOT_COLLECTED"
            elif scope_incomplete or resource_type in self.coverage_failures:
                status = "PARTIAL"
            else:
                status = "COLLECTED"
            records.append(
                {
                    "record_type": "zpr_coverage",
                    "snapshot_time": snapshot_time,
                    "event_time": snapshot_time,
                    "resource_type": resource_type,
                    "coverage_status": status,
                    "eligible_count": counts.get("eligible") if status in {"COLLECTED", "PARTIAL"} else None,
                    "protected_count": counts.get("protected") if status in {"COLLECTED", "PARTIAL"} else None,
                    "available_count": counts.get("available") if resource_type in INVENTORY_RESOURCE_TYPES and status in {"COLLECTED", "PARTIAL"} else None,
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
        if self._scope_cache is not None:
            return list(self._scope_cache)
        if self._explicit_compartment_ids is not None:
            self._scope_cache = list(self._explicit_compartment_ids)
            return list(self._scope_cache)
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
        except Exception as exc:
            self.compartment_scope_complete = False
            self._collection_error(
                service="Identity", operation="list_compartments", resource_type=None, exc=exc
            )
        self._scope_cache = ids
        return list(ids)

    @staticmethod
    def _operational(resource: Any) -> bool:
        return str(getattr(resource, "lifecycle_state", "") or "").upper() not in _NON_OPERATIONAL_STATES

    @staticmethod
    def _inventory_record(resource: Any, *, resource_type: str, compartment_id: str,
                          region: str | None, cluster_id: str | None = None,
                          security_attributes_supported: bool = False,
                          inventory_status: str = "OPERATIONAL") -> dict[str, Any]:
        """Serialize provider inventory fields without inferring protection."""
        record: dict[str, Any] = {
            "record_type": "resource_inventory",
            "resource_id": getattr(resource, "id", None),
            "resource_name": getattr(resource, "name", None) or getattr(resource, "display_name", None),
            "resource_type": resource_type,
            "compartment_id": getattr(resource, "compartment_id", None) or compartment_id,
            "region": region,
            "lifecycle_state": getattr(resource, "lifecycle_state", None),
            "inventory_status": inventory_status,
            "protection_status": "UNATTRIBUTED" if security_attributes_supported else "ATTRIBUTE_EVIDENCE_UNAVAILABLE",
        }
        if cluster_id:
            record["cluster_id"] = cluster_id
        for source, target in (("vcn_id", "vcn_id"), ("subnet_id", "subnet_id"),
                               ("subnet_ids", "subnet_ids"), ("availability_domain", "availability_domain"),
                               ("fault_domain", "fault_domain"),
                               ("security_attributes", "security_attributes")):
            value = getattr(resource, source, None)
            if value is not None:
                record[target] = to_plain(value)
                if source == "security_attributes":
                    record["protection_status"] = "ATTRIBUTES_PRESENT" if value else "UNATTRIBUTED"
        return record

    def _collect_extended_inventory(self) -> list[dict[str, Any]]:
        """Collect OKE topology and Autonomous Database inventory in scope."""
        self._extended_inventory_attempted = True
        compartment_ids = self._compartment_ids()
        records: list[dict[str, Any]] = []
        try:
            oke = client(self.session, "container_engine.ContainerEngineClient")
            for cid in compartment_ids:
                try:
                    clusters = _list_all(self.oci, oke.list_clusters, cid)
                    counts = self.coverage_counts.setdefault("oke_cluster", {"eligible": 0, "available": 0})
                    for cluster in clusters:
                        if not self._operational(cluster):
                            records.append(self._inventory_record(cluster, resource_type="oke_cluster", compartment_id=cid, region=self.session.region, inventory_status="TERMINAL"))
                            continue
                        counts["eligible"] += 1
                        counts["available"] += 1 if str(getattr(cluster, "lifecycle_state", "")).upper() == "ACTIVE" else 0
                        records.append(self._inventory_record(cluster, resource_type="oke_cluster", compartment_id=cid, region=self.session.region))
                        try:
                            pools = _list_all(self.oci, oke.list_node_pools, cid, cluster_id=getattr(cluster, "id", None))
                            pool_counts = self.coverage_counts.setdefault("oke_node_pool", {"eligible": 0, "available": 0})
                            for pool in pools:
                                if not self._operational(pool):
                                    records.append(self._inventory_record(pool, resource_type="oke_node_pool", compartment_id=cid, region=self.session.region, cluster_id=getattr(cluster, "id", None), inventory_status="TERMINAL"))
                                    continue
                                pool_counts["eligible"] += 1
                                pool_counts["available"] += 1 if str(getattr(pool, "lifecycle_state", "")).upper() == "ACTIVE" else 0
                                pool_record = self._inventory_record(pool, resource_type="oke_node_pool", compartment_id=cid, region=self.session.region, cluster_id=getattr(cluster, "id", None))
                                if not pool_record.get("vcn_id") and getattr(cluster, "vcn_id", None):
                                    pool_record["vcn_id"] = cluster.vcn_id
                                records.append(pool_record)
                        except Exception as exc:
                            self._collection_error(service="ContainerEngine", operation="list_node_pools", resource_type="oke_node_pool", exc=exc)
                except Exception as exc:
                    self.coverage_failures.add("oke_node_pool")
                    self._collection_error(service="ContainerEngine", operation="list_clusters", resource_type="oke_cluster", exc=exc)
        except Exception as exc:
            self.coverage_failures.add("oke_node_pool")
            self._collection_error(service="ContainerEngine", operation="client", resource_type="oke_cluster", exc=exc)

        try:
            database = client(self.session, "database.DatabaseClient")
            subnet_vcns: dict[str, str] = {}
            for cid in compartment_ids:
                try:
                    databases = _list_all(self.oci, database.list_autonomous_databases, cid)
                    counts = self.coverage_counts.setdefault("autonomous_database", {"eligible": 0, "available": 0})
                    for db in databases:
                        if not self._operational(db):
                            records.append(self._inventory_record(db, resource_type="autonomous_database", compartment_id=cid, region=self.session.region, security_attributes_supported=True, inventory_status="TERMINAL"))
                            continue
                        counts["eligible"] += 1
                        counts["available"] += 1 if str(getattr(db, "lifecycle_state", "")).upper() in {"AVAILABLE", "AVAILABLE_NEEDS_ATTENTION"} else 0
                        record = self._inventory_record(db, resource_type="autonomous_database", compartment_id=cid, region=self.session.region, security_attributes_supported=True)
                        # ADB returns its private-endpoint subnet, but no VCN.
                        # Resolve the actual subnet rather than leaving placement
                        # blank or inferring it from the deployment compartment.
                        if record.get("subnet_id") and not record.get("vcn_id"):
                            subnet_id = record["subnet_id"]
                            try:
                                if subnet_id not in subnet_vcns:
                                    network = client(self.session, "core.VirtualNetworkClient")
                                    subnet = network.get_subnet(subnet_id).data
                                    if not getattr(subnet, "vcn_id", None):
                                        raise ValueError("Subnet response has no VCN placement")
                                    subnet_vcns[subnet_id] = subnet.vcn_id
                                record["vcn_id"] = subnet_vcns[subnet_id]
                            except Exception as exc:
                                self._collection_error(service="Networking", operation="get_subnet", resource_type="autonomous_database", exc=exc)
                        if record.get("protection_status") == "ATTRIBUTES_PRESENT":
                            counts["protected"] = counts.get("protected", 0) + 1
                        records.append(record)
                except Exception as exc:
                    self._collection_error(service="Database", operation="list_autonomous_databases", resource_type="autonomous_database", exc=exc)
        except Exception as exc:
            self._collection_error(service="Database", operation="client", resource_type="autonomous_database", exc=exc)
        return records

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
        inventory: list[dict[str, Any]] = []
        for cid in self._compartment_ids():
            try:
                vcns = _list_all(self.oci, net.list_vcns, cid)
                counts = self.coverage_counts.setdefault("vcn", {"eligible": 0, "protected": 0})
                for vcn in vcns:
                    if self._operational(vcn):
                        counts["eligible"] += 1
                        inventory.append(self._inventory_record(
                            vcn, resource_type="vcn", compartment_id=cid,
                            region=region, security_attributes_supported=True,
                        ))
                        rec = protected_resource_record(
                            getattr(vcn, "security_attributes", None),
                            resource_id=vcn.id, resource_name=vcn.display_name, resource_type="Vcn",
                            compartment_id=cid, region=region, vcn_id=vcn.id,
                        )
                        if rec:
                            resources.append(rec)
                            counts["protected"] += 1
                    elif getattr(vcn, "lifecycle_state", None) in _NON_OPERATIONAL_STATES:
                        inventory.append(self._inventory_record(
                            vcn, resource_type="vcn", compartment_id=cid,
                            region=region, security_attributes_supported=True,
                            inventory_status="TERMINAL",
                        ))
            except Exception as exc:
                self._collection_error(
                    service="Networking", operation="list_vcns", resource_type="vcn", exc=exc
                )
            try:
                instances = _list_all(self.oci, compute.list_instances, cid)
                counts = self.coverage_counts.setdefault("instance", {"eligible": 0, "protected": 0})
                for inst in instances:
                    if self._operational(inst):
                        counts["eligible"] += 1
                        inventory.append(self._inventory_record(
                            inst, resource_type="instance", compartment_id=cid,
                            region=region, security_attributes_supported=True,
                        ))
                        rec = protected_resource_record(
                            getattr(inst, "security_attributes", None),
                            resource_id=inst.id, resource_name=inst.display_name, resource_type="instance",
                            compartment_id=cid, region=region,
                        )
                        if rec:
                            resources.append(rec)
                            counts["protected"] += 1
                    elif getattr(inst, "lifecycle_state", None) in _NON_OPERATIONAL_STATES:
                        inventory.append(self._inventory_record(
                            inst, resource_type="instance", compartment_id=cid,
                            region=region, security_attributes_supported=True,
                            inventory_status="TERMINAL",
                        ))
            except Exception as exc:
                self._collection_error(
                    service="Compute", operation="list_instances", resource_type="instance", exc=exc
                )
        enriched = self._enrich_compute_vnics([*resources, *inventory])
        self._base_inventory = [row for row in enriched if row.get("record_type") == "resource_inventory"]
        return [row for row in enriched if row.get("record_type") != "resource_inventory"]

    def _enrich_compute_vnics(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compute = client(self.session, "core.ComputeClient")
        network = client(self.session, "core.VirtualNetworkClient")
        subnet_vcns: dict[str, str] = {}
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
                    subnet_id = getattr(vnic, "subnet_id", None)
                    vcn_id = getattr(vnic, "vcn_id", None)
                    if subnet_id and not vcn_id:
                        try:
                            if subnet_id not in subnet_vcns:
                                subnet = network.get_subnet(subnet_id).data
                                if not getattr(subnet, "vcn_id", None):
                                    raise ValueError("Subnet response has no VCN placement")
                                subnet_vcns[subnet_id] = subnet.vcn_id
                            vcn_id = subnet_vcns[subnet_id]
                        except Exception as exc:
                            self._collection_error(service="Networking", operation="get_subnet", resource_type="instance", exc=exc)
                    private_ips = _list_all(self.oci, network.list_private_ips, vnic_id=vnic_id)
                    for private_ip in private_ips or [None]:
                        enriched.append(
                            {
                                **resource,
                                "vnic_id": vnic_id,
                                "vcn_id": vcn_id,
                                "subnet_id": subnet_id,
                                "private_ip": getattr(private_ip, "ip_address", None) if private_ip else getattr(vnic, "private_ip", None),
                            }
                        )
            except Exception as exc:
                self._collection_error(
                    service="Compute", operation="enrich_vnics", resource_type="instance", exc=exc
                )
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
