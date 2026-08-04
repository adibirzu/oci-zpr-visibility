"""Normalized record metadata for trustworthy Log Analytics evidence."""

from __future__ import annotations

import uuid
from typing import Any, Iterable

from .jsonutil import utc_now_iso

SCHEMA_VERSION = "2.0"

# Single vocabulary for zpr_run.flow_collection_status. Every producer must use
# these tokens: the "Flow collection status" widget groups on the raw value, and
# validate-dashboards decides whether flow-dependent widgets are applicable by
# looking for a run whose status is not NOT_CONFIGURED.
FLOW_STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
FLOW_STATUS_SUCCEEDED = "SUCCEEDED"
FLOW_STATUS_FAILED = "FAILED"
FLOW_COLLECTION_STATUSES = (
    FLOW_STATUS_NOT_CONFIGURED,
    FLOW_STATUS_SUCCEEDED,
    FLOW_STATUS_FAILED,
)


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
    if flow_collection_status not in FLOW_COLLECTION_STATUSES:
        raise ValueError(
            f"flow_collection_status must be one of {FLOW_COLLECTION_STATUSES}, "
            f"got {flow_collection_status!r}"
        )
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
