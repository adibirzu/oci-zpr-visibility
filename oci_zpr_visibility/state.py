"""Snapshot state persistence + policy drift detection.

Persisting the previous run's policy-statement records to Object Storage lets the
scheduled collector detect `statement_hash` drift across runs without manual
seeding (so the dashboard's drift widget fires on real changes).
"""
from __future__ import annotations

import json
from typing import Any

from .oci_clients import OciSession, client

STATE_OBJECT = "zpr-visibility/previous_records.jsonl"


def compute_drift(prev_records: list[dict[str, Any]], curr_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Emit zpr_policy_drift records where a (policy_id, statement) hash changed.

    New statements (absent previously) are not drift; only changed hashes are.
    """
    def index(records: list[dict[str, Any]]) -> dict[tuple, str]:
        out: dict[tuple, str] = {}
        for r in records:
            if r.get("record_type") != "zpr_policy_statement":
                continue
            key = (r.get("policy_id"), r.get("statement"))
            out[key] = r.get("statement_hash")
        return out

    prev = index(prev_records)
    curr = index(curr_records)
    drift: list[dict[str, Any]] = []
    for key, new_hash in curr.items():
        old_hash = prev.get(key)
        if old_hash is not None and old_hash != new_hash:
            drift.append({
                "record_type": "zpr_policy_drift",
                "policy_id": key[0],
                "statement": key[1],
                "old_hash": old_hash,
                "new_hash": new_hash,
            })
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
