"""Flow-log to ZPR inventory correlation."""

from __future__ import annotations

from typing import Any

from .security_attributes import attribute_matches_reference, render_attributes


def _data(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("data")
    return value if isinstance(value, dict) else record


def _ip_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for entry in snapshot.get("ip_resource_map", []):
        ip = entry.get("private_ip")
        if ip:
            mapping[str(ip)] = entry
    for resource in snapshot.get("resources", []):
        ip = resource.get("private_ip")
        if ip and ip not in mapping:
            mapping[str(ip)] = resource
    return mapping


def _expected(policy_records: list[dict[str, Any]], src_attrs: dict[str, str], dst_attrs: dict[str, str]) -> bool:
    for policy in policy_records:
        source = policy.get("source_attribute")
        destination = policy.get("destination_attribute")
        source_ok = not source or attribute_matches_reference(src_attrs, str(source))
        destination_ok = not destination or attribute_matches_reference(dst_attrs, str(destination))
        if source_ok and destination_ok:
            return True
    return False


def correlate_flow_records(
    flow_records: list[dict[str, Any]],
    snapshot: dict[str, Any],
    policy_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ip_lookup = _ip_map(snapshot)
    correlated: list[dict[str, Any]] = []

    for raw in flow_records:
        data = _data(raw)
        source_ip = data.get("sourceAddress") or data.get("source_address")
        destination_ip = data.get("destinationAddress") or data.get("destination_address")
        action = data.get("action")
        source = ip_lookup.get(str(source_ip), {}) if source_ip else {}
        destination = ip_lookup.get(str(destination_ip), {}) if destination_ip else {}
        src_attrs = source.get("normalized_security_attributes") or {}
        dst_attrs = destination.get("normalized_security_attributes") or {}
        destination_has_zpr = bool(dst_attrs)
        has_expected_policy = _expected(policy_records, src_attrs, dst_attrs) if src_attrs or dst_attrs else False

        if action == "ACCEPT" and has_expected_policy:
            classification = "expected_accepted"
        elif action == "ACCEPT" and destination_has_zpr:
            classification = "unexpected_accepted"
        elif action == "REJECT" and has_expected_policy:
            classification = "suspected_misconfiguration"
        elif action == "REJECT" and destination_has_zpr:
            classification = "expected_blocked"
        else:
            classification = "needs_enrichment"

        correlated.append(
            {
                "record_type": "zpr_enriched_flow",
                "time": raw.get("time") or data.get("time") or raw.get("datetime"),
                "action": action,
                "classification": classification,
                "source_ip": source_ip,
                "destination_ip": destination_ip,
                "destination_port": data.get("destinationPort") or data.get("destination_port"),
                "protocol": data.get("protocolName") or data.get("protocol"),
                "source_resource_id": source.get("resource_id"),
                "source_resource_name": source.get("resource_name"),
                "destination_resource_id": destination.get("resource_id"),
                "destination_resource_name": destination.get("resource_name"),
                "source_security_attributes": ",".join(render_attributes(src_attrs)),
                "destination_security_attributes": ",".join(render_attributes(dst_attrs)),
                "zpr_destination": destination_has_zpr,
                "matched_expected_policy": has_expected_policy,
            }
        )

    return correlated
