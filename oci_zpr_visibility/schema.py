"""Normalized record metadata for trustworthy Log Analytics evidence."""

from __future__ import annotations

import uuid
from typing import Any, Iterable

from .jsonutil import utc_now_iso

SCHEMA_VERSION = "2.0"


def new_run_id() -> str:
    """Return an opaque correlation identifier that carries no tenant detail."""
    return str(uuid.uuid4())


def normalize_record(
    record: dict[str, Any],
    *,
    run_id: str,
    inventory_snapshot_time: str | None = None,
) -> dict[str, Any]:
    """Add the common v2 evidence envelope without overwriting source fields."""
    normalized = dict(record)
    normalized.setdefault("schema_version", SCHEMA_VERSION)
    normalized.setdefault("run_id", run_id)
    if not normalized.get("event_time"):
        normalized["event_time"] = (
            normalized.get("time")
            or normalized.get("snapshot_time")
            or inventory_snapshot_time
            or utc_now_iso()
        )
    if inventory_snapshot_time:
        normalized.setdefault("inventory_snapshot_time", inventory_snapshot_time)
    return normalized


def normalize_records(
    records: Iterable[dict[str, Any]],
    *,
    run_id: str,
    inventory_snapshot_time: str | None = None,
) -> list[dict[str, Any]]:
    return [
        normalize_record(
            record,
            run_id=run_id,
            inventory_snapshot_time=inventory_snapshot_time,
        )
        for record in records
    ]


def run_record(
    *,
    run_id: str,
    event_time: str,
    collection_status: str,
    flow_collection_status: str,
    record_count: int,
    finding_count: int,
    drift_count: int,
    flow_count: int,
    collection_error_count: int = 0,
) -> dict[str, Any]:
    """Build a non-sensitive heartbeat/data-quality record for Log Analytics."""
    return normalize_record(
        {
            "record_type": "zpr_run",
            "event_time": event_time,
            "collection_status": collection_status,
            "flow_collection_status": flow_collection_status,
            "record_count": record_count,
            "finding_count": finding_count,
            "drift_count": drift_count,
            "flow_count": flow_count,
            "collection_error_count": collection_error_count,
        },
        run_id=run_id,
        inventory_snapshot_time=event_time,
    )
