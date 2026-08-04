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
| Policy enforcement vs traffic | VCN Flow Logs (OCI Logging) ↔ `correlate` | `zpr_enriched_flow` | ACCEPT/REJECT bar, blocked dests, accepted-requires-review, flow link |
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
              │ + flow logs│  + fields + log group    │ metrics       │ Dash   │ │
              └─────┬──────┘  └──────────┬───────────┘ └──────┬───────┘ (40    │ │
                    │ Connector Hub      │ dashboard queries  │ alarms        tiles)│
                    │ (flow path)        ▼                    ▼  → Notifications │ │
                    └──────────────▶  OCI Log Analytics Dashboard "OCI ZPR Visibility"
                         └────────────────────────────────────────────────────┘
```

## 3. How logs are collected and sent to Log Analytics

This is the core data pipeline — read it top to bottom.

**A. Collect (read-only SDK calls).** `ZprCollector.collect` authenticates via
`build_session` (API key locally, **instance principal** on the controller VM)
and reads, in one pass:
- `ZprClient.get_configuration` → tenancy ZPR enablement
- `ZprClient.list_zpr_policies` + `get_zpr_policy` → policies & statements
- `SecurityAttributeClient.list_security_attribute_namespaces` + `list_security_attributes` → the `oracle-zpr` namespace and its attributes
- `core.list_vcns` + `core.list_instances` over the compartment subtree → protected resources (Resource Search omits `securityAttributes`, so Core APIs are used) + VNIC/private-IP enrichment

**B. Transform into normalized records.** The snapshot is turned into flat JSON
records, each carrying a `record_type` discriminator plus the shared evidence
envelope (`schema_version`, opaque `run_id`, `event_time`,
`inventory_snapshot_time` — see [log-format.md](log-format.md)):
- `policy_parser` → `zpr_policy_statement` (source/destination attribute, scope, CIDRs, parser confidence)
- `findings.generate_findings` → `zpr_finding` (broad-CIDR, unprotected-resource, unknown-attribute)
- `correlate` (VCN Flow Logs ↔ policy intent) → `zpr_enriched_flow` (5 classifications)
- `state.compute_drift` (vs the previous snapshot in Object Storage) → `zpr_policy_drift`
- `ZprCollector` coverage/error bookkeeping → `zpr_coverage`, sanitized `zpr_collection_gap`
- `schema.run_record` → `zpr_run` (freshness + pipeline health for one `run_id`)

**C. Serialize to JSONL.** Records are written one JSON object per line
(`records.jsonl`) — the exact shape documented in [log-format.md](log-format.md).

**D. Provision the Log Analytics target (idempotent upserts).** `provision-la`:
1. **Fields** — upserts one custom field per JSON key (authoritative token list:
   `provision_la.FIELD_TOKENS`); reuses system fields case-insensitively so
   queries use bare tokens.
2. **Parser** — a JSON parser (`oci_zpr_visibility_json_parser`) mapping each
   JSON key to its field via `structured_column_info: $.<key>`, and
   `event_time` → the system **Time** field. Must be
   `is_single_line_content=False` + `header_content="$:0"`.
3. **Source** — `OCI ZPR Visibility JSON` (type `os_file`) bound to that parser.
4. **Log group** — `zpr-visibility-la` (the ingestion target).

**E. Upload.** `upload_log_file` (LA **Upload API**) streams the JSONL to the
custom source under the log group. LA runs the parser, extracts the fields, and
stamps **Time** from `event_time`. Records are immediately queryable as
`'Log Source' = 'OCI ZPR Visibility JSON'`.

**F. Publish metrics + repeat.** `metrics.publish_metrics` posts gauges to the
`zpr_visibility` Monitoring namespace; the controller's 15-minute cron re-runs
`refresh` (collect → drift → upload → metrics), so the dashboard stays live.
Because every run uploads a *full snapshot*, dashboard count widgets dedup to
distinct identities (see §6) so totals don't multiply across runs.

## 4. Two ingestion paths into Log Analytics

| Path | Producer | Ingestion | LA source |
|------|----------|-----------|-----------|
| **Inventory / findings / drift** | `collect` → `provision-la --upload` (or `refresh`) | **LA Upload API** → custom source | `OCI ZPR Visibility JSON` (custom) |
| **Network traffic** | VCN Flow Logs (service) → OCI Logging | Connector Hub → LA, or `correlate --flow-log-group-id` | `OCI VCN Flow Unified Schema Logs` (built-in) |

Why Upload API (not Connector Hub) for the inventory path: a logging-source
Connector Hub connector to a LoggingAnalytics target requires a null
`logSourceIdentifier` and cannot target a custom source, so it would not feed the
custom-source dashboards. Connector Hub is used only for VCN Flow Logs.

## 5. Collector internals

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

Record types (discriminator `record_type`) and their fields are specified in
[log-format.md](log-format.md).

## 6. CLI surface

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
| `validate-dashboards` | Parse and execute all queries; optionally require an exact fresh run ID |
| `deploy-dashboard` | Build + import the focused Management Dashboard suite (`--dry-run`) |
| `refresh` | Scheduled unit: collect → drift → upload → publish metrics |
| `demo` | Local sample run |

## 7. Detection / dashboard model

Dashboard suite `OCI ZPR Visibility` — 7 focused dashboards / 40 widgets (KPI
tiles, severity sunburst, flow trends and Link analysis, policy/resource/drift
tables, detections, explicit resource coverage, and collection health).
`deploy_dashboard.build_management_dashboards` maps each logical view to an OCI
Management Dashboard and each widget to a saved search modelled on a working OCI
LA export:
- viz type matched to query shape; **real per-viz `visualizationOptions`**
  (empty `{}` crashes the JET renderer);
- `scopeFilters` is an object (LogGroup/Entity/LogSet), not a list;
- `timeSelection` uses LA tokens (`l60m`), not ISO-8601;
- **table** widgets are raw-record `fields` projections (never end in `stats` —
  the console appends raw system fields after STATS otherwise);
- **count** widgets dedup snapshot repeats with `distinctcount(<id>)` or an
  `eval` composite key, so totals are window-independent;
- 12-col layout via `dashboard.resolve_layout`.

The **Detections** tab expresses each detection rule as a saved search that tags
matching records with a `Detection` label via LQL `eval` (see
[detections.md](detections.md)) plus a per-rule KPI tile.

| Detection | Source record | Signal |
|-----------|---------------|--------|
| Broad CIDR exception | `zpr_finding` | policy allows `/0`–`/12` instead of attribute scope |
| Unprotected-by-policy resource | `zpr_finding` | tagged resource no policy targets |
| Unknown attribute reference | `zpr_finding` | policy references unknown namespace/key |
| Rejected protected destination | `zpr_enriched_flow` | REJECT to a ZPR destination |
| Accepted flow review | `zpr_enriched_flow` | flow-log ACCEPT with no complete modeled policy match |
| Rejected expected-allow review | `zpr_enriched_flow` | flow-log REJECT where modeled policy expected ALLOW |
| Policy drift | `zpr_policy_drift` | statement added, removed, or modified |
| Collection gap | `zpr_collection_gap` | sanitized OCI read operation failed |
| Resource coverage gap | `zpr_coverage` | supported ZPR type is not yet collected |

## 8. Continuous operation & alerting

- `refresh` (cron / OCI Functions / OKE CronJob — `deploy/oke-cronjob.yaml`):
  collect → drift (Object Storage state) → Upload API → publish metrics.
- Monitoring alarms (`terraform/alarms.tf`, gated `create_alarms`): CRITICAL/HIGH
  findings, accepted-requires-policy-review flows, rejected-policy-expected-allow
  flows, collection errors, missing heartbeat → Notifications topic.

## 9. Identity & access

Collector principal needs read on ZPR, Security Attributes, Core
(compute/network), Identity (compartment walk); write on the custom log
(`use log-content`); manage on the LA log group + state bucket; and
`post_metric_data` for metrics. See [runbook.md](runbook.md) for statements.

## 10. Failure modes designed for

- ZPR not onboarded → `get_configuration` 404 recorded as soft error.
- Resource Search omits security attributes → resources enumerated via Core APIs.
- VCN Flow Logs carry no ZPR deny-reason → attribution by explicit correlation.
- LA custom JSON parser needs `is_single_line_content=False` + `header_content="$:0"`.
- Dashboard renderer (Oracle JET) crashes on bad schema → `scopeFilters` object (not list), real per-viz `visualizationOptions`, LA-token `timeSelection`, tables never end in `stats`.
- Full-snapshot re-upload would inflate counts → count widgets dedup via `distinctcount`/`eval` composite key; default window narrowed to `l60m`.
- Attribute-reference false positives → reference key compared against attribute *names*, not namespaces.
- Policy syntax drift → parser keeps raw statement + `parser_confidence`.
