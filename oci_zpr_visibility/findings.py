"""Risk finding generation for ZPR inventory snapshots."""

from __future__ import annotations

import ipaddress
from typing import Any

from .security_attributes import attribute_matches_reference, render_attributes


def _severity_for_cidr(cidr: str) -> str:
    network = ipaddress.ip_network(cidr, strict=False)
    if network.prefixlen == 0:
        return "CRITICAL"
    if network.version == 4 and network.prefixlen <= 8:
        return "HIGH"
    if network.version == 4 and network.is_private and network.prefixlen <= 12:
        return "MEDIUM"
    return "LOW"


def _policy_targets_resource(policy_records: list[dict[str, Any]], attrs: dict[str, str]) -> bool:
    for record in policy_records:
        destination = record.get("destination_attribute")
        if destination and attribute_matches_reference(attrs, str(destination)):
            return True
    return False


def generate_findings(snapshot: dict[str, Any], policy_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot_time = str(snapshot.get("snapshot_time", ""))
    findings: list[dict[str, Any]] = []

    for record in policy_records:
        for cidr in record.get("cidrs", []):
            severity = _severity_for_cidr(str(cidr))
            if severity in {"CRITICAL", "HIGH", "MEDIUM"}:
                findings.append(
                    {
                        "record_type": "zpr_finding",
                        "snapshot_time": snapshot_time,
                        "severity": severity,
                        "finding_type": "broad_cidr_exception",
                        "policy_id": record.get("policy_id"),
                        "policy_name": record.get("policy_name"),
                        "statement": record.get("statement"),
                        "cidr": cidr,
                        "recommendation": "Review and replace broad CIDR access with attribute-scoped ZPR relationships where possible.",
                    }
                )

    for resource in snapshot.get("resources", []):
        attrs = resource.get("normalized_security_attributes") or {}
        if not attrs:
            continue
        if _policy_targets_resource(policy_records, attrs):
            continue
        findings.append(
            {
                "record_type": "zpr_finding",
                "snapshot_time": snapshot_time,
                "severity": "HIGH",
                "finding_type": "protected_resource_no_matching_policy",
                "resource_id": resource.get("resource_id"),
                "resource_name": resource.get("resource_name"),
                "resource_type": resource.get("resource_type"),
                "compartment_id": resource.get("compartment_id"),
                "region": resource.get("region"),
                "security_attributes": ",".join(render_attributes(attrs)),
                "recommendation": "Create an explicit ZPR allow policy for approved clients or remove the security attribute if it was not intended.",
            }
        )

    known_attribute_keys = {
        f"{item.get('namespace_name')}.{item.get('name')}"
        for item in snapshot.get("security_attributes", [])
        if item.get("namespace_name") and item.get("name")
    }
    known_namespaces = {
        str(item.get("namespace_name"))
        for item in snapshot.get("security_attributes", [])
        if item.get("namespace_name")
    }
    for record in policy_records:
        for reference in record.get("attribute_references", []):
            reference_text = str(reference)
            namespace = reference_text.split(".", 1)[0].split(":", 1)[0]
            if reference_text in known_attribute_keys or namespace in known_namespaces:
                continue
            findings.append(
                {
                    "record_type": "zpr_finding",
                    "snapshot_time": snapshot_time,
                    "severity": "MEDIUM",
                    "finding_type": "policy_references_unknown_attribute",
                    "policy_id": record.get("policy_id"),
                    "policy_name": record.get("policy_name"),
                    "statement": record.get("statement"),
                    "attribute_reference": reference_text,
                    "recommendation": "Validate that the referenced security attribute namespace/key still exists and is spelled correctly.",
                }
            )

    return findings
