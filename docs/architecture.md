# OCI ZPR Visibility — Architecture

End-to-end system that collects every OCI Zero Trust Packet Routing (ZPR)
capability, correlates it with network traffic, and visualizes it in OCI Log
Analytics (custom source + Management Dashboard) with Monitoring alarms.

All OCIDs / namespaces / IPs in this doc are placeholders — resolve real values
from your tenancy; never inline them in committed files.

## 1. ZPR capability coverage (what we collect & visualize)

| ZPR capability | OCI API used | Record / artifact | Dashboard surface |
|----------------|--------------|-------------------|-------------------|
| ZPR configuration (tenancy enablement) | `ZprClient.get_configuration` / `create_configuration` | `zpr_configuration` (snapshot) | posture (enabled/active) |
| Security attribute namespaces | `SecurityAttributeClient.list_security_attribute_namespaces` | snapshot `security_attribute_namespaces` | — (inventory) |
| Security attributes (definitions) | `list_security_attributes` | snapshot `security_attributes` | — (inventory) |
| **Protected resources** (VCN/instance tagged) | `core.VirtualNetworkClient.list_vcns`, `core.ComputeClient.list_instances` (Resource Search omits security attrs) + VNIC/IP enrich | `zpr_resource` | Protected resources KPI, by-attribute, by-subnet, detail |
| ZPR policies + statements | `list_zpr_policies` / `get_zpr_policy` + `policy_parser` | `zpr_policy_statement` | Active policies, statement table, src↔dst matrix, sunburst |
| Policy enforcement vs traffic | VCN Flow Logs (OCI Logging) ↔ `correlate` | `zpr_enriched_flow` | ACCEPT/REJECT bar, blocked dests, unexpected-accepted, flow link |
| Policy drift over time | Object Storage snapshot state + `state.compute_drift` | `zpr_policy_drift` | Policy drift candidates |
| Governance findings | `findings.generate_findings` | `zpr_finding` | Top findings sunburst, broad-CIDR, missing-policy, KPI |

## 2. Component overview

```
                         ┌────────────────────────────────────────────────────┐
                         │                    OCI Tenancy                       │
  ┌───────────────┐ read │  ┌──────────────────────────────────────────────┐  │
  │ ZPR service   │◀──────┼──│  oci-zpr-visibility (Python)                  │  │
  │ Security Attr │◀──────┼──│   collect · findings · correlate · seed       │  │
  │ Core (VCN/    │◀──────┼──│   trigger · refresh · provision-la            │  │
  │  instances)   │       │  │   validate-dashboards · deploy-dashboard      │  │
  └───────────────┘       │  └───────┬───────────────┬──────────────┬───────┘  │
                          │  emit↓   │ upload(API)↓   │ post-metric↓ │import↓   │
              ┌───────────┼──────────┼───────────────┼──────────────┼────────┐ │
              │ OCI Logging│  OCI Log Analytics       │ OCI Monitoring│  LA    │ │
              │ custom log │  custom source + parser  │ zpr_visibility│ Mgmt   │ │
              │ + flow logs│  + 40 fields + log group │ metrics       │ Dash   │ │
              └─────┬──────┘  └──────────┬───────────┘ └──────┬───────┘ (21    │ │
                    │ Connector Hub      │ dashboard queries  │ alarms        tiles)│
                    │ (flow path)        ▼                    ▼  → Notifications │ │
                    └──────────────▶  OCI Log Analytics Dashboard "OCI ZPR Visibility"
                         └────────────────────────────────────────────────────┘
```

## 3. Two ingestion paths into Log Analytics

| Path | Producer | Ingestion | LA source |
|------|----------|-----------|-----------|
| **Inventory / findings / drift** | `collect` → `provision-la --upload` (or `refresh`) | **LA Upload API** → custom source | `OCI ZPR Visibility JSON` (custom) |
| **Network traffic** | VCN Flow Logs (service) → OCI Logging | Connector Hub → LA, or `correlate --flow-log-group-id` | `OCI VCN Flow Unified Schema Logs` (built-in) |

Why Upload API (not Connector Hub) for the inventory path: a logging-source
Connector Hub connector to a LoggingAnalytics target requires a null
`logSourceIdentifier` and cannot target a custom source, so it would not feed the
custom-source dashboards. Connector Hub is used only for VCN Flow Logs.

## 4. Collector internals

```
build_session (oci_clients: api_key | instance_principal | resource_principal;
               every client gets retry/backoff + (10,180)s timeout)
   │
ZprCollector.collect ──▶ snapshot.json
   ├─ zpr.get_configuration(compartment_id=tenancy)        → zpr_configuration
   ├─ zpr.list_zpr_policies / get_zpr_policy               → zpr_policies
   ├─ security_attribute.list_namespaces / list_attributes → namespaces + attrs
   └─ core.list_vcns + list_instances (subtree) + VNIC/IP  → protected resources
        │
  policy_parser.parse_statement   → zpr_policy_statement (src/dst attr, scope, CIDRs, confidence)
  findings.generate_findings      → zpr_finding (broad_cidr / no_policy / unknown_attr)
  correlate.correlate_flow_records→ zpr_enriched_flow (5 classifications)
  state.compute_drift (vs OS)     → zpr_policy_drift
        │
  jsonutil.to_plain / write_jsonl → records.jsonl
        ├─ emit_records → OCI Logging custom log (loggingingestion.put_logs)
        └─ provision_la.upload_log_file → LA custom source (Upload API)
  metrics.publish_metrics → Monitoring zpr_visibility namespace (alarms)
```

Record types (discriminator `record_type`): `zpr_policy_statement`,
`zpr_resource`, `zpr_finding`, `zpr_enriched_flow`, `zpr_policy_drift`.

## 5. CLI surface

`oci-zpr-visibility <cmd>` (console script). `--version`; cloud commands take
`--auth/--config-file/--profile/--region` (validated via typed `RunConfig`) and
`--json`.

| Command | Purpose |
|---------|---------|
| `enable-zpr` | Enable ZPR in the tenancy root |
| `collect` | Collect ZPR inventory → snapshot + records (+`--emit-log-id`) |
| `findings` / `correlate` | Generate findings / correlate flows (local or `--flow-log-group-id` live) |
| `emit` | Send records to an OCI custom log |
| `seed` | Create the `app` security attribute + a ZPR policy |
| `trigger` | Synthesize flows covering every classification |
| `provision-la` | Create LA fields/parser/source/log group; `--upload` ingests |
| `validate-dashboards` | Execute all dashboard queries (HIT/MISS/ERROR) |
| `deploy-dashboard` | Build + import the Management Dashboard (`--dry-run`) |
| `refresh` | Scheduled unit: collect → drift → upload → publish metrics |
| `demo` | Local sample run |

## 6. Detection / dashboard model

Dashboard `OCI ZPR Visibility` — 5 tabs / 21 widgets (KPI tiles, severity
sunburst, ACCEPT/REJECT bar, src→dst flow table, policy/resource/drift tables).
`deploy_dashboard.build_management_dashboard` maps each widget to a saved search
(viz type matched to query shape; empty `visualizationOptions`; 12-col layout via
`dashboard.resolve_layout`).

| Detection | Source record | Signal |
|-----------|---------------|--------|
| Broad CIDR exception | `zpr_finding` | policy allows `/0`–`/12` instead of attribute scope |
| Unprotected-by-policy resource | `zpr_finding` | tagged resource no policy targets |
| Unknown attribute reference | `zpr_finding` | policy references unknown namespace/key |
| Rejected protected destination | `zpr_enriched_flow` | REJECT to a ZPR destination |
| Unexpected accepted flow | `zpr_enriched_flow` | ACCEPT with no matching policy |
| Suspected misconfiguration | `zpr_enriched_flow` | REJECT where policy expected ALLOW |
| Policy drift | `zpr_policy_drift` | `statement_hash` changed across runs |

## 7. Continuous operation & alerting

- `refresh` (cron / OCI Functions / OKE CronJob — `deploy/oke-cronjob.yaml`):
  collect → drift (Object Storage state) → Upload API → publish metrics.
- Monitoring alarms (`terraform/alarms.tf`, gated `create_alarms`): CRITICAL/HIGH
  findings, unexpected-accepted, suspected-misconfiguration, missing heartbeat →
  Notifications topic.

## 8. Identity & access

Collector principal needs read on ZPR, Security Attributes, Core
(compute/network), Identity (compartment walk); write on the custom log
(`use log-content`); manage on the LA log group + state bucket; and
`post_metric_data` for metrics. See [runbook.md](runbook.md) for statements.

## 9. Failure modes designed for

- ZPR not onboarded → `get_configuration` 404 recorded as soft error.
- Resource Search omits security attributes → resources enumerated via Core APIs.
- VCN Flow Logs carry no ZPR deny-reason → attribution by explicit correlation.
- LA custom JSON parser needs `is_single_line_content=False` + `header_content="$:0"`.
- Dashboard renderer crashes on bad viz/options → viz type matched to query shape, `visualizationOptions` kept empty.
- Policy syntax drift → parser keeps raw statement + `parser_confidence`.
