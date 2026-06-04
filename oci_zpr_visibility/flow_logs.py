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
) -> list[dict[str, Any]]:
    """Fetch + normalize VCN flow log records from OCI Logging (GSL search)."""
    search = client(session, "loggingsearch.LogSearchClient")
    models = session.oci.loggingsearch.models
    query = f'search "{compartment_id}/{log_group_id}/{log_id}"'
    details = models.SearchLogsDetails(
        time_start=time_start, time_end=time_end, search_query=query, is_return_field_info=False
    )
    results = search.search_logs(details, limit=limit).data.results or []
    return [normalize_flow_log_record(r.data if hasattr(r, "data") else r) for r in results]
