#!/usr/bin/env python3
"""Trigger every ZPR detection classification and emit records.

Builds a snapshot whose ip_resource_map mirrors the seeded app:web / app:db
topology, then synthesizes VCN-flow-shaped events that exercise each
classification, correlates them, and writes inventory + finding + enriched-flow
records ready for `oci-zpr-visibility emit`.

In production these flows come from real VCN Flow Logs (enable them on the VCN
hosting the ZPR-protected resources, via terraform flow_log_targets). This
script is the offline trigger for validating detections end to end.

Usage:
  .venv/bin/python scripts/trigger_rules.py --out out/demo/trigger_records.jsonl
"""
from __future__ import annotations

import argparse
import sys

from oci_zpr_visibility.correlate import correlate_flow_records
from oci_zpr_visibility.findings import generate_findings
from oci_zpr_visibility.jsonutil import write_jsonl
from oci_zpr_visibility.policy_parser import policy_statement_records

SNAPSHOT = {
    "snapshot_time": "2026-06-04T00:00:00Z",
    "zpr_policies": [
        {
            "id": "ocid1.zprpolicy.demo",
            "name": "zpr-visibility-demo",
            "lifecycle_state": "ACTIVE",
            "statements": [
                "in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints",
                "in app:fin-network VCN allow app:ops endpoints to connect to '10.0.0.0/8'",
            ],
        }
    ],
    "security_attributes": [{"namespace_name": "oracle-zpr", "name": "app"}],
    "resources": [
        {"resource_id": "ocid1.instance.web", "resource_name": "web-01",
         "resource_type": "instance", "subnet_id": "ocid1.subnet.app",
         "private_ip": "10.0.1.10",
         "normalized_security_attributes": {"app": "web"}},
        {"resource_id": "ocid1.instance.db", "resource_name": "db-01",
         "resource_type": "instance", "subnet_id": "ocid1.subnet.app",
         "private_ip": "10.0.2.20",
         "normalized_security_attributes": {"app": "db"}},
        # tagged but no matching policy -> protected_resource_no_matching_policy
        {"resource_id": "ocid1.instance.payroll", "resource_name": "payroll-01",
         "resource_type": "instance", "subnet_id": "ocid1.subnet.app",
         "private_ip": "10.0.2.99",
         "normalized_security_attributes": {"app": "payroll"}},
    ],
}
SNAPSHOT["ip_resource_map"] = [
    {**r, "normalized_security_attributes": r["normalized_security_attributes"]}
    for r in SNAPSHOT["resources"]
]

# Flows engineered to hit each classification.
FLOWS = [
    # expected_accepted: web -> db, policy allows
    {"data": {"action": "ACCEPT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.20", "destinationPort": 1521, "protocolName": "tcp"}},
    # expected_blocked: web -> payroll (ZPR dest, no allow)
    {"data": {"action": "REJECT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.99", "destinationPort": 1521, "protocolName": "tcp"}},
    # unexpected_accepted: db -> web accepted but no expected policy that direction
    {"data": {"action": "ACCEPT", "sourceAddress": "10.0.2.20", "destinationAddress": "10.0.1.10", "destinationPort": 22, "protocolName": "tcp"}},
    # suspected_misconfiguration: web -> db rejected even though policy expects allow
    {"data": {"action": "REJECT", "sourceAddress": "10.0.1.10", "destinationAddress": "10.0.2.20", "destinationPort": 1521, "protocolName": "tcp"}},
    # needs_enrichment: unknown endpoints
    {"data": {"action": "ACCEPT", "sourceAddress": "203.0.113.5", "destinationAddress": "10.0.9.9", "destinationPort": 443, "protocolName": "tcp"}},
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="out/demo/trigger_records.jsonl")
    args = p.parse_args(argv)

    # Stamp records with the current time so they fall inside recent dashboard
    # windows (l60m/l7d), not a fixed past date.
    from .jsonutil import utc_now_iso
    now = utc_now_iso()
    SNAPSHOT["snapshot_time"] = now
    for flow in FLOWS:
        flow["data"].setdefault("time", now)

    policy_records = []
    for policy in SNAPSHOT["zpr_policies"]:
        policy_records.extend(policy_statement_records(policy, SNAPSHOT["snapshot_time"]))
    findings = generate_findings(SNAPSHOT, policy_records)
    enriched = correlate_flow_records(FLOWS, SNAPSHOT, policy_records)

    resource_records = [
        {"record_type": "zpr_resource", "snapshot_time": SNAPSHOT["snapshot_time"],
         "resource_id": r["resource_id"], "resource_name": r["resource_name"],
         "resource_type": r["resource_type"], "subnet_id": r["subnet_id"],
         "private_ip": r["private_ip"],
         "security_attributes": ",".join(f"app={v}" for v in r["normalized_security_attributes"].values())}
        for r in SNAPSHOT["resources"]
    ]

    all_records = [*policy_records, *resource_records, *findings, *enriched]
    write_jsonl(args.out, all_records)

    from collections import Counter
    print(f"wrote {len(all_records)} records -> {args.out}")
    print("record types:", dict(Counter(r["record_type"] for r in all_records)))
    print("flow classifications:", dict(Counter(r["classification"] for r in enriched)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
