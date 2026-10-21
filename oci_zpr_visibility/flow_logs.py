"""Consume real OCI VCN Flow Logs from OCI Logging and feed correlation.

Replaces the synthetic `trigger` data source for the flow path: VCN Flow Logs
land in OCI Logging (enable via terraform `flow_log_targets`), are fetched here
via Logging search, normalized to the shape `correlate_flow_records` expects
(it already reads VCN unified-schema fields: sourceAddress, destinationAddress,
action, destinationPort, protocolName), and correlated against the ZPR snapshot.
"""
from __future__ import annotations

from typing import Any

from .oci_clients import OciSession, client


def validate_flow_log_source(session: OciSession, log_group_id: str, log_id: str,
                             expected_vcn_id: str) -> None:
    """Reject disabled/non-flow logs and source resources outside the selected VCN."""
    log = client(session, "logging.LoggingManagementClient").get_log(log_group_id, log_id).data
    source = getattr(getattr(log, "configuration", None), "source", None)
    if not getattr(log, "is_enabled", False) or getattr(source, "service", None) != "flowlogs":
        raise ValueError("Selected log is not an enabled VCN Flow Log")
    source_id = getattr(source, "resource", None) or ""
    if source_id == expected_vcn_id:
        return
    network = client(session, "core.VirtualNetworkClient")
    if source_id.startswith("ocid1.vnic."):
        source_id = network.get_vnic(source_id).data.subnet_id
    elif not source_id.startswith("ocid1.subnet."):
        raise ValueError("Selected flow log source is not a supported VCN, subnet or VNIC")
    if network.get_subnet(source_id).data.vcn_id != expected_vcn_id:
        raise ValueError("Selected flow log source is outside the selected VCN")


def normalize_flow_log_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a Logging search result to a {data, time} flow record.

    Logging search wraps each entry as data.logContent.{data,time}; a flat
    {data, time} record passes through unchanged so synthetic + real records
    share one code path.
    """
    data = raw.get("data", raw)
    log_content = data.get("logContent") if isinstance(data, dict) else None
    if isinstance(log_content, dict):
        return {"data": log_content.get("data", {}), "time": log_content.get("time")}
    return {"data": data, "time": raw.get("time") or (data.get("time") if isinstance(data, dict) else None)}


def fetch_flow_logs(
    session: OciSession,
    compartment_id: str,
    log_group_id: str,
    log_id: str,
    time_start: str,
    time_end: str,
    limit: int = 1000,
    expected_vcn_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch + normalize VCN flow log records from OCI Logging (GSL search)."""
    if expected_vcn_id:
        validate_flow_log_source(session, log_group_id, log_id, expected_vcn_id)
    search = client(session, "loggingsearch.LogSearchClient")
    models = session.oci.loggingsearch.models
    query = f'search "{compartment_id}/{log_group_id}/{log_id}"'
    details = models.SearchLogsDetails(
        time_start=time_start, time_end=time_end, search_query=query, is_return_field_info=False
    )
    results = search.search_logs(details, limit=limit).data.results or []
    return [normalize_flow_log_record(r.data if hasattr(r, "data") else r) for r in results]
