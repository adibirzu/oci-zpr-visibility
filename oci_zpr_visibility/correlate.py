"""Flow-log to ZPR inventory correlation."""

from __future__ import annotations

import ipaddress
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


def _active(policy: dict[str, Any]) -> bool:
    state = str(policy.get("policy_lifecycle_state") or "").upper()
    return not state or state == "ACTIVE"


def _address_matches(address: Any, values: Any, *, networks: bool) -> bool:
    if not address or not values:
        return False
    try:
        candidate = ipaddress.ip_address(str(address))
    except ValueError:
        return False
    for value in values:
        try:
            if networks and candidate in ipaddress.ip_network(str(value), strict=False):
                return True
            if not networks and candidate == ipaddress.ip_address(str(value)):
                return True
        except ValueError:
            continue
    return False


def _expected(
    policy_records: list[dict[str, Any]],
    src_attrs: dict[str, str],
    dst_attrs: dict[str, str],
    source_ip: Any,
    destination_ip: Any,
) -> dict[str, Any] | None:
    for policy in policy_records:
        if not _active(policy):
            continue
        source = policy.get("source_attribute")
        destination = policy.get("destination_attribute")
        if source:
            source_ok = attribute_matches_reference(src_attrs, str(source))
        elif policy.get("source_type") == "cidr":
            source_ok = _address_matches(source_ip, policy.get("source_cidrs"), networks=True)
        elif policy.get("source_type") == "ip":
            source_ok = _address_matches(source_ip, policy.get("source_ips"), networks=False)
        else:
            source_ok = policy.get("source_type") == "all_endpoints"
        target_type = policy.get("target_type")
        if destination:
            destination_ok = attribute_matches_reference(dst_attrs, str(destination))
        elif target_type == "cidr":
            destination_ok = _address_matches(
                destination_ip, policy.get("destination_cidrs") or policy.get("cidrs"), networks=True
            )
        elif target_type == "ip":
            destination_ok = _address_matches(
                destination_ip, policy.get("destination_ips") or policy.get("ips"), networks=False
            )
        elif target_type == "all_endpoints":
            destination_ok = True
        else:
            destination_ok = False
        if source_ok and destination_ok:
            statement = str(policy.get("statement") or "").lower()
            has_unmodeled_filters = any(
                token in statement
                for token in ("protocol", "connection-state", "icmp.type", "icmp.code")
            )
            confidence = "LOW" if has_unmodeled_filters else "MEDIUM"
            return {
                "policy_id": policy.get("policy_id"),
                "policy_name": policy.get("policy_name"),
                "confidence": confidence,
                "match_reason": "attributes_or_address_match",
                "has_unmodeled_filters": has_unmodeled_filters,
            }
    return None


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
        match = _expected(policy_records, src_attrs, dst_attrs, source_ip, destination_ip)
        has_expected_policy = match is not None

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

        review_classification = {
            "expected_accepted": "policy_consistent_accept",
            "unexpected_accepted": "accepted_requires_policy_review",
            "suspected_misconfiguration": "rejected_policy_expected_allow",
            "expected_blocked": "rejected_protected_destination",
            "needs_enrichment": "needs_enrichment",
        }[classification]

        event_time = raw.get("time") or data.get("time") or raw.get("datetime")

        correlated.append(
            {
                "record_type": "zpr_enriched_flow",
                "time": event_time,
                "event_time": event_time,
                "snapshot_time": event_time,
                "inventory_snapshot_time": snapshot.get("snapshot_time"),
                "action": action,
                "classification": classification,
                "review_classification": review_classification,
                "evidence_source": "OCI_VCN_FLOW_LOG_PLUS_ZPR_INVENTORY",
                "zpr_attribution": "INFERRED_NOT_PROVIDER_VERDICT",
                "correlation_confidence": match.get("confidence") if match else "LOW",
                "correlation_reason": match.get("match_reason") if match else "no_complete_policy_match",
                "source_ip": source_ip,
                "destination_ip": destination_ip,
                "source_port": data.get("sourcePort") or data.get("source_port"),
                "destination_port": data.get("destinationPort") or data.get("destination_port"),
                "protocol": data.get("protocolName") or data.get("protocol"),
                "flow_id": data.get("flowid") or data.get("flow_id"),
                "bytes_out": data.get("bytesOut") if data.get("bytesOut") is not None else data.get("bytes_out"),
                "packets": data.get("packets"),
                "capture_status": data.get("status"),
                "capture_start_time": data.get("startTime") or data.get("start_time"),
                "capture_end_time": data.get("endTime") or data.get("end_time"),
                "vnic_id": raw.get("oracle.vnicocid") or data.get("vnicId") or data.get("vnic_id"),
                "subnet_id": raw.get("oracle.vnicsubnetocid") or data.get("subnetId") or data.get("subnet_id"),
                "source_resource_id": source.get("resource_id"),
                "source_resource_name": source.get("resource_name"),
                "destination_resource_id": destination.get("resource_id"),
                "destination_resource_name": destination.get("resource_name"),
                "source_security_attributes": ",".join(render_attributes(src_attrs)),
                "destination_security_attributes": ",".join(render_attributes(dst_attrs)),
                "zpr_destination": destination_has_zpr,
                "matched_expected_policy": has_expected_policy,
                "matched_policy_id": match.get("policy_id") if match else None,
                "matched_policy_name": match.get("policy_name") if match else None,
                "has_unmodeled_policy_filters": match.get("has_unmodeled_filters") if match else False,
            }
        )

    return correlated
