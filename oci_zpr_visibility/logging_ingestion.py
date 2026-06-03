"""Emit normalized ZPR records to OCI Logging custom logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .oci_clients import OciSession, client


def emit_records(session: OciSession, log_id: str, records: list[dict[str, Any]], batch_size: int = 100) -> int:
    ingestion = client(session, "loggingingestion.LoggingClient")
    models = session.oci.loggingingestion.models
    emitted = 0
    now = datetime.now(timezone.utc)

    for index in range(0, len(records), batch_size):
        chunk = records[index : index + batch_size]
        entries = [
            models.LogEntry(
                data=json.dumps(record, sort_keys=True),
                id=str(uuid4()),
                time=now,
            )
            for record in chunk
        ]
        details = models.PutLogsDetails(
            specversion="1.0",
            log_entry_batches=[
                models.LogEntryBatch(
                    entries=entries,
                    source="oci-zpr-visibility",
                    type="zpr.visibility",
                    defaultlogentrytime=now,
                    subject="zpr-inventory",
                )
            ],
        )
        ingestion.put_logs(log_id=log_id, put_logs_details=details)
        emitted += len(chunk)
    return emitted
