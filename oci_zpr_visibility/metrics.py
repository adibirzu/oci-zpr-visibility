"""Publish ZPR posture counts as custom OCI Monitoring metrics for alarms.

Findings/flows live in Log Analytics, which Monitoring alarms can't read
directly. We publish per-run counts to the `zpr_visibility` metric namespace so
Terraform Monitoring alarms (terraform/) can fire on CRITICAL/HIGH findings,
unexpected-accepted / suspected-misconfiguration flows, and a missing heartbeat.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .oci_clients import OciSession, client

METRIC_NAMESPACE = "zpr_visibility"
HIGH_SEVERITIES = {"CRITICAL", "HIGH"}


def build_metric_values(records: list[dict[str, Any]]) -> dict[str, int]:
    """Pure: reduce records to the metric counts published each run."""
    findings = [r for r in records if r.get("record_type") == "zpr_finding"]
    flows = [r for r in records if r.get("record_type") == "zpr_enriched_flow"]

    def flow_count(classification: str) -> int:
        return sum(1 for f in flows if f.get("classification") == classification)

    return {
        "findings_total": len(findings),
        "findings_critical_high": sum(1 for f in findings if f.get("severity") in HIGH_SEVERITIES),
        "flows_unexpected_accepted": flow_count("unexpected_accepted"),
        "flows_suspected_misconfiguration": flow_count("suspected_misconfiguration"),
        "heartbeat": 1,
    }


def publish_metrics(session: OciSession, records: list[dict[str, Any]], compartment_id: str | None = None) -> int:
    """Post the run's metric values to the zpr_visibility Monitoring namespace."""
    oci = session.oci
    mon = client(session, "monitoring.MonitoringClient")
    # telemetry-ingestion endpoint is required for post_metric_data
    mon.base_client.endpoint = f"https://telemetry-ingestion.{session.region}.oraclecloud.com"
    compartment_id = compartment_id or session.tenancy_id
    now = datetime.now(timezone.utc)
    values = build_metric_values(records)
    models = oci.monitoring.models
    metric_data = [
        models.MetricDataDetails(
            namespace=METRIC_NAMESPACE,
            compartment_id=compartment_id,
            name=name,
            dimensions={"resourceType": "zpr"},
            datapoints=[models.Datapoint(timestamp=now, value=float(value))],
        )
        for name, value in values.items()
    ]
    mon.post_metric_data(models.PostMetricDataDetails(metric_data=metric_data))
    return len(metric_data)
