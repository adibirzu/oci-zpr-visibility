# Dashboards and data guide

This guide explains what the current OCI ZPR Visibility dashboards mean, where
their data comes from, and the proposed direction for a more exploratory next
version. This project is an independent visibility accelerator, not an Oracle
product. Use OCI's native ZPR Visualizer for the authoritative ZPR topology and
policy view, and Network Path Analyzer (NPA) for OCI network-path configuration
analysis. This project adds historical collection, flow-log evidence,
collection coverage, and review context; it does not replace either tool.

## Current dashboard surface

The current release candidate provisions seven OCI Log Analytics Management
Dashboard views with 40 widgets:

| View | Operator question | Data used |
|---|---|---|
| Executive posture | What changed in the selected scope, and is collection current? | Latest inventory, findings, run health |
| Policy inventory | Which policy statements and endpoint scopes were collected? | Parsed policy-statement records |
| Resource coverage | Which supported resources are protected, and where are coverage gaps? | Resource and coverage records |
| Flow review | Which observed flows merit investigation against modeled policy intent? | VCN Flow Logs enriched with collected inventory and policies |
| Drift governance | Which collected policy statements changed between snapshots? | Snapshot-derived policy drift records |
| Detections | Which posture and flow-review conditions need operator attention? | Findings and explicitly labeled review classifications |
| Collection health | Which calls or stages failed, and how fresh is the latest run? | Run, collection-gap, and coverage records |

The dashboard definitions and saved-search catalog are code-backed. A rendered
dashboard, populated data, current freshness, and successful drilldowns require
separate live validation; see [validation.md](validation.md) and the lifecycle
status in [resource-manager-lifecycle-review.md](resource-manager-lifecycle-review.md).

## How project data is collected and used

```text
OCI ZPR / Security Attributes / Core inventory APIs
       │ read-only inventory snapshot
       ├── policies ── documented-syntax parser ── policy statement records
       ├── resources + VCN/VNIC/IP context ─────── resource/coverage records
       └── snapshot comparison ─────────────────── drift records

OCI VCN Flow Logs ── OCI Logging ── Connector Hub ── OCI Log Analytics
       │                                                    ▲
       └── Logging API read + correlation (when configured) │
                                                            │
collector JSONL ── Log Analytics Upload API ────────────────┘
       │
       └── common run/scope metadata ── saved searches ── dashboard widgets
```

The scheduled collector uses an OCI instance principal in the appliance; a
developer may use an API-key profile for local discovery or testing. It reads
ZPR configuration and policy statements, security-attribute namespace and
attribute definitions, and the supported resource families configured for the
run. The current implementation's resource inventory is not a promise that all
OCI ZPR-supported services are collected: consult the emitted coverage records
and [service coverage notes](services.md).

The collector normalizes data into JSON Lines records. Each record includes a
`record_type`, schema version, opaque run identifier, event time, inventory
snapshot time, and—when configured—installation and scope identifiers. Policy
statements retain parser confidence and source/destination VCN scope. Resource
records retain the available tenancy/region/compartment and VCN/VNIC/address
context used for correlation. Collection failures are summarized without
embedding exception messages or resource identifiers.

Inventory, findings, policy drift, collection coverage, and run-health records
are uploaded to the configured Log Analytics custom source through its Upload
API. VCN Flow Logs are produced separately by OCI Logging and routed to Log
Analytics through Connector Hub when that path is provisioned. Where direct
flow-log retrieval is configured, the collector may also read flow records
from Logging and correlate them before emitting enriched records. Dashboard
queries use the saved-search catalog against these sources; the dashboard does
not reach into the OCI control plane on each chart render.

The scheduled run compares the current policy snapshot with the prior stored
snapshot for drift, emits records, uploads them, and publishes health metrics.
Posture and inventory widgets should use the latest successful snapshot for the
selected scope; flow trends use the selected event-time window. Full snapshots
can appear more than once in a time window, so count queries deduplicate stable
resource or policy identities. Each dashboard must make its time range, region,
compartment/scope, source freshness, and partial-coverage state visible.

### Evidence labels and limits

| Evidence | What it supports | What it does not prove |
|---|---|---|
| Collected policy statement | The policy text and endpoint scopes returned by the OCI API for that snapshot | That a packet traversed a path or was allowed/denied |
| VCN Flow Log `ACCEPT` / `REJECT` | The network-flow observation and action recorded by Flow Logs | A ZPR-specific verdict or deny reason |
| Correlated flow classification | An inference from flow tuple, resource context, collected attributes, and parsed policy intent | Provider-confirmed ZPR enforcement or complete packet-level truth |
| Finding | A configured review condition derived from the collected snapshot | An automatic remediation recommendation or confirmed incident |
| Coverage `PARTIAL` / `NOT_COLLECTED` | A gap in the collector's observed resource-family/scope coverage | That the tenant has no resources in the gap |
| `zpr_run` record | That this run's record reached the queryable destination when independently verified | That all expected widgets, flows, or services are healthy |

Unsupported or ambiguous syntax, incomplete endpoint identity, missing flow-log
coverage, permission failures, and stale inventory should produce an
inconclusive/partial state—not a confident allow/deny conclusion. Specifically,
`REJECT` must never be presented as “blocked by ZPR” without a provider-supplied
ZPR verdict. See [log-format.md](log-format.md) for fields and review-class
definitions.

## Next-version dashboard direction

The next dashboard iteration is a product/design proposal, not an implemented
web console. Keep OCI Log Analytics Management Dashboards as a useful native
surface, while exploring a private read-only console organized as a persistent
filter bar plus operator-oriented tabs:

1. **Overview** — freshness, protected-resource denominator, high-priority
   findings, observed flow volume, collection/coverage status.
2. **Topology** — policy-intent edges and observed-flow edges rendered as
   distinct layers; filters for region, VCN, compartment, attribute, resource,
   and time. Link out to OCI ZPR Visualizer and NPA for their native analyses.
3. **Traffic** — accepted/rejected observations over time, top communicating
   pairs, protocol/port breakdown, and source-to-destination matrix, only where
   the underlying flow records carry those fields.
4. **Policies** — searchable statement list, parsed endpoints and VCN scopes,
   namespace-aware attribute references, parser confidence, and policy-change
   before/after timeline.
5. **Coverage** — protected versus eligible/inventory-observed resources,
   unprotected-resource review, collected/partial/not-collected families, and
   freshness by scope.
6. **Findings** — severity and type filters; linked detail showing the
   originating observation, policy text, endpoint attributes, confidence,
   evidence timestamp, and investigation steps.
7. **Collection health** — last successful inventory and upload, flow-log
   source coverage, query/ingestion freshness, permissions and failure stages.

Every chart should cross-filter a linked table or details panel. Selecting a
resource, flow, or finding should preserve the current scope and time filters,
show the source record and evidence type, and provide useful next actions. The
UI should have explicit empty, stale, partial-coverage, permission-denied, and
query-failure states. Do not invent latency, packet loss, throughput, or an
enforcement reason unless an OCI source provides that measurement.

### Reference views and transferable patterns

These are design references, not claims that OCI exposes equivalent data or
that this project implements matching features:

| Reference | Documented view/pattern | Transfer to this project |
|---|---|---|
| [OCI ZPR Visualizer](https://docs.oracle.com/en-us/iaas/Content/zero-trust-packet-routing/zpr-visualizer.htm) | Visual relationships between security attributes, protected resources, policy statements; identifies resources without attributes; scoped to region/tenancy | Add historical inventory/change context and clearly separate policy-intent edges from observed-flow edges; link to the native visualizer |
| [OCI Network Path Analyzer](https://docs.oracle.com/iaas/Content/Network/Concepts/path_analyzer.htm) | Configuration-based network-path analysis for route/security connectivity issues | Link to NPA for path troubleshooting; do not represent the collector's policy correlation as path simulation |
| [Google Cloud Flow Analyzer](https://docs.cloud.google.com/network-intelligence-center/docs/flow-analyzer/overview) | Guided five-tuple filters, selectable data-volume/latency display options where the data supports them, query-based analysis, and flow drilldown | Guided flow filters, linked summaries/details, and saved filter context; expose only metrics present in OCI evidence |
| [Azure Traffic Analytics](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics) | Flow-log-backed traffic analytics over a central Log Analytics workspace, with resource/scope context and traffic/security analysis | Make source, workspace/log group, scope, time window, and flow-log coverage obvious; retain a queryable evidence trail |
| [AWS Network Firewall dashboard](https://docs.aws.amazon.com/network-firewall/latest/developerguide/nwfw-using-dashboard.html) and [available flow/alert metrics](https://docs.aws.amazon.com/network-firewall/latest/developerguide/nwfw-detailed-monitoring-metrics.html) | Multiple visualizations for flow/alert data, including top talkers and protocol/application-related data where configured; availability depends on logging setup | Use modular views and scope filters, explain logging prerequisites, and hide or mark unavailable any panel whose source is not configured |

OCI product documentation describes the native Visualizer as a policy/resource
relationship view. Cross-VCN policies are also documented by Oracle; preserve
source and destination VCN scopes as first-class topology dimensions rather
than collapsing endpoints to IP alone. See [cross-VCN ZPR announcement](https://blogs.oracle.com/cloud-infrastructure/introducing-zpr-with-cross-vcn-support)
and the [policy syntax reference](https://docs.oracle.com/en-us/iaas/Content/zero-trust-packet-routing/zpr-policy-syntax.htm).

## Design and implementation gates

Before adding a new visualization, document its source record, query, grouping,
time semantics, deduplication rule, scope filters, evidence class, empty/error
states, and any cost implications. The next-version gate should include:

- query-catalog tests for every panel, including parse and live execution;
- current-run, stale-data, partial-coverage, empty, and permission-denied tests;
- authorization and compartment/region/scope isolation for every read endpoint;
- accessible keyboard-operable tab and drilldown journeys;
- explicit visual distinction between modeled policy relationships and logged
  traffic observations;
- redacted screenshots and comparison against the current OCI dashboards;
- no policy or security-attribute mutation endpoints in the read-only console.

The sequence and release status are tracked in [ROADMAP.md](../ROADMAP.md).
