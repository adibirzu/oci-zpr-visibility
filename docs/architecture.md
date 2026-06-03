# OCI ZPR Visibility — Architecture

End-to-end architecture for collecting OCI Zero Trust Packet Routing (ZPR)
configuration, correlating it with VCN Flow Logs, and surfacing posture and
detections in OCI Log Analytics.

All OCIDs, namespaces, and IPs in this document are placeholders. Resolve real
values from your tenancy; never inline them in committed files.

## 1. Component overview

```
                          ┌──────────────────────────────────────────────┐
                          │                OCI Tenancy                     │
                          │                                                │
   ┌───────────────┐      │  ┌────────────┐      ┌──────────────────┐      │
   │  ZPR service  │◀─────┼──│  Collector │      │  VCN Flow Logs   │      │
   │ (root cmpt)   │ read │  │  (Python)  │      │  (ACCEPT/REJECT) │      │
   └───────────────┘      │  └─────┬──────┘      └────────┬─────────┘      │
   ┌───────────────┐ read │        │ emit JSON            │ service log     │
   │ Security Attr │◀─────┼────────┤                      │                 │
   │ namespaces    │      │        ▼                      ▼                 │
   └───────────────┘      │  ┌──────────────┐      ┌──────────────┐         │
   ┌───────────────┐ read │  │ Custom log   │      │ Flow service │         │
   │ Resource      │◀─────┼──│ (CUSTOM)     │      │ log          │         │
   │ Search + VNIC │      │  └──────┬───────┘      └──────┬───────┘         │
   └───────────────┘      │         │                     │                 │
                          │         │  OCI Logging log group               │
                          │         ▼                     ▼                 │
                          │     ┌─────────────────────────────────┐        │
                          │     │      Connector Hub (x2)         │        │
                          │     │  logging → loggingAnalytics     │        │
                          │     └────────────────┬────────────────┘        │
                          │                      ▼                          │
                          │            ┌───────────────────┐                │
                          │            │  OCI Log Analytics │                │
                          │            │  (namespace + LG)  │                │
                          │            │  custom JSON source│                │
                          │            └─────────┬─────────┘                │
                          │                      ▼                          │
                          │            ┌───────────────────┐                │
                          │            │  Dashboard (5 tabs)│                │
                          │            │  ZPR detections    │                │
                          │            └───────────────────┘                │
                          └──────────────────────────────────────────────┘
```

## 2. Data planes

There are two independent ingestion paths that converge in Log Analytics:

| Path | Producer | OCI Logging log | Connector | LA source |
|------|----------|-----------------|-----------|-----------|
| **Inventory / findings** | `oci-zpr-visibility collect`/`emit` (Python) | `zpr-inventory` (CUSTOM) | `zpr-inventory-to-log-analytics` | `OCI ZPR Visibility JSON` (custom) |
| **Network traffic** | OCI VCN Flow Logs (service) | `zpr-flow-*` (SERVICE) | `zpr-flow-logs-to-log-analytics` | `OCI VCN Flow Unified Schema Logs` (built-in) |

The collector also performs **local correlation** (`correlate`) joining exported
flow JSONL with the ZPR snapshot when a fully managed connector path is not
desired; those `zpr_enriched_flow` records are emitted on the inventory path.

## 3. Collector internals (`oci_zpr_visibility`)

```
build_session ──▶ ZprCollector.collect ──▶ snapshot.json
   (oci_clients)         │
                         ├─ zpr.get_configuration(compartment_id=tenancy)   → zpr_configuration
                         ├─ zpr.list_zpr_policies / get_zpr_policy           → zpr_policies
                         ├─ security_attribute.list_*                        → namespaces + attributes
                         ├─ resource_search.search_resources                 → attributed resources
                         └─ core.Compute/VirtualNetwork (VNIC/IP enrich)     → ip_resource_map
                                  │
   policy_parser.parse_statement ─┤  (regex relation + CIDR/IP + confidence)
   findings.generate_findings ────┤  → zpr_finding (broad_cidr / no_policy / unknown_attr)
   correlate.correlate_flow_records┘ → zpr_enriched_flow (expected/unexpected/blocked/misconfig)
                                  │
   jsonutil.to_plain / write_jsonl┘  → records.jsonl ──▶ logging_ingestion.emit_records ──▶ Custom log
```

Record types emitted (discriminated by `record_type`):

- `zpr_policy_statement` — one per parsed statement (source/dest attribute, scope, CIDRs, confidence).
- `zpr_resource` — protected resource with normalized security attributes + VNIC/IP.
- `zpr_finding` — `broad_cidr_exception` | `protected_resource_no_matching_policy` | `policy_references_unknown_attribute`.
- `zpr_enriched_flow` — flow classified as `expected_accepted` | `unexpected_accepted` | `expected_blocked` | `suspected_misconfiguration` | `needs_enrichment`.

## 4. Detection logic (what the dashboard surfaces)

| Detection | Source record | Signal |
|-----------|---------------|--------|
| Broad CIDR exception | `zpr_finding` | Policy allows `/0`–`/12` CIDR instead of attribute-scoped relationship |
| Unprotected-by-policy resource | `zpr_finding` | Resource carries a security attribute but no policy targets it |
| Unknown attribute reference | `zpr_finding` | Policy references a namespace/key not present in the tenancy |
| Rejected protected destination | `zpr_enriched_flow` | `action=REJECT` to a ZPR-attributed destination |
| Unexpected accepted flow | `zpr_enriched_flow` | `action=ACCEPT` to a ZPR destination with no matching expected policy |
| Suspected misconfiguration | `zpr_enriched_flow` | `action=REJECT` even though policy correlation expected ALLOW |
| Policy drift | `zpr_policy_statement` | `statement_hash` for a `policy_id` changes over time |

## 5. Identity & access

The collector principal (API key, instance principal, or resource principal)
needs read on: ZPR, Security Attributes, Resource Search, Core (compute/network),
and write (`use log-content`) on the custom log. Connector Hub needs a service
policy allowing `loggingAnalytics` ingestion in the target compartment. See
[runbook.md](runbook.md) for the concrete policy statements.

## 6. Deployment topology

- **Terraform** (`terraform/`) provisions: `oci_zpr_configuration` (root), the
  Logging log group, flow service logs (per target), the custom log, and the two
  Connector Hub connectors. `oci_zpr_configuration` has `prevent_destroy`.
- **Python package** runs on a schedule (cron / OKE CronJob / Functions) to emit
  inventory + findings every 15 min (live) or daily (audit).
- **Log Analytics** holds the custom JSON source + the 5-tab dashboard.

## 7. Failure modes designed for

- ZPR not onboarded → `get_configuration` returns 404; collector records it as a
  soft error instead of crashing.
- VCN Flow Logs have **no ZPR deny-reason field**; deny attribution is done by
  explicit policy/resource correlation, not by parsing a flow field.
- Policy syntax drift → parser keeps the raw statement and emits
  `parser_confidence` rather than discarding unparseable statements.
