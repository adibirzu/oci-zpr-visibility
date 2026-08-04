"""Snapshot state persistence + policy drift detection.

Persisting the previous run's policy-statement records to Object Storage lets the
scheduled collector detect `statement_hash` drift across runs without manual
seeding (so the dashboard's drift widget fires on real changes).
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .oci_clients import OciSession, client
from .jsonutil import utc_now_iso

STATE_OBJECT = "zpr-visibility/previous_records.jsonl"


def compute_drift(prev_records: list[dict[str, Any]], curr_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Emit added, removed, and modified policy-statement evidence.

    Hash multisets are compared first so harmless statement reordering does not
    become drift. Removed and added hashes at the same statement position are
    paired as a modification; unmatched deltas remain explicit additions or
    removals.
    """

    def policies(records: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
        grouped: dict[Any, list[dict[str, Any]]] = {}
        for record in records:
            if record.get("record_type") == "zpr_policy_statement":
                grouped.setdefault(record.get("policy_id"), []).append(record)
        return grouped

    previous = policies(prev_records)
    current = policies(curr_records)
    event_time = next(
        (
            record.get("event_time") or record.get("snapshot_time")
            for record in curr_records
            if record.get("event_time") or record.get("snapshot_time")
        ),
        utc_now_iso(),
    )
    drift: list[dict[str, Any]] = []

    def emit_change(
        change_type: str,
        policy_id: Any,
        *,
        old: dict[str, Any] | None = None,
        new: dict[str, Any] | None = None,
    ) -> None:
        drift.append(
            {
                "record_type": "zpr_policy_drift",
                "event_time": event_time,
                "snapshot_time": event_time,
                "change_type": change_type,
                "policy_id": policy_id,
                "policy_name": (new or old or {}).get("policy_name"),
                "statement_index": (new or old or {}).get("statement_index"),
                "old_statement": old.get("statement") if old else None,
                "new_statement": new.get("statement") if new else None,
                "old_hash": old.get("statement_hash") if old else None,
                "new_hash": new.get("statement_hash") if new else None,
            }
        )

    for policy_id in sorted(set(previous) | set(current), key=str):
        old_records = previous.get(policy_id, [])
        new_records = current.get(policy_id, [])
        old_counts = Counter(record.get("statement_hash") for record in old_records)
        new_counts = Counter(record.get("statement_hash") for record in new_records)
        removed_counts = old_counts - new_counts
        added_counts = new_counts - old_counts

        removed: list[dict[str, Any]] = []
        added: list[dict[str, Any]] = []
        for record in sorted(old_records, key=lambda item: (item.get("statement_index") is None, item.get("statement_index") or 0)):
            statement_hash = record.get("statement_hash")
            if removed_counts[statement_hash]:
                removed.append(record)
                removed_counts[statement_hash] -= 1
        for record in sorted(new_records, key=lambda item: (item.get("statement_index") is None, item.get("statement_index") or 0)):
            statement_hash = record.get("statement_hash")
            if added_counts[statement_hash]:
                added.append(record)
                added_counts[statement_hash] -= 1

        added_by_index = {
            record.get("statement_index"): record
            for record in added
            if record.get("statement_index") is not None
        }
        paired_added_ids: set[int] = set()
        paired_removed_ids: set[int] = set()
        for old in removed:
            new = added_by_index.get(old.get("statement_index"))
            if new is not None:
                emit_change("MODIFIED", policy_id, old=old, new=new)
                paired_removed_ids.add(id(old))
                paired_added_ids.add(id(new))

        for old in removed:
            if id(old) not in paired_removed_ids:
                emit_change("REMOVED", policy_id, old=old)
        for new in added:
            if id(new) not in paired_added_ids:
                emit_change("ADDED", policy_id, new=new)

    return drift


def load_previous_records(session: OciSession, bucket: str, namespace: str | None = None) -> list[dict[str, Any]]:
    """Read the previous run's records from Object Storage (empty if absent)."""
    os_client = client(session, "object_storage.ObjectStorageClient")
    ns = namespace or os_client.get_namespace().data
    try:
        resp = os_client.get_object(ns, bucket, STATE_OBJECT)
        text = resp.data.content.decode("utf-8") if hasattr(resp.data, "content") else resp.data.text
    except Exception:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def save_records(session: OciSession, bucket: str, records: list[dict[str, Any]], namespace: str | None = None) -> None:
    """Persist this run's records to Object Storage for the next run's drift check."""
    os_client = client(session, "object_storage.ObjectStorageClient")
    ns = namespace or os_client.get_namespace().data
    body = "\n".join(json.dumps(r, sort_keys=True) for r in records)
    os_client.put_object(ns, bucket, STATE_OBJECT, body.encode("utf-8"))
