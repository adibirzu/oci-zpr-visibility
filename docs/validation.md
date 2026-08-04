# OCI ZPR Visibility — End-to-End Validation Report

Environment: verified OCI target; tenant, profile, region, namespace, resource
names, addresses, and identifiers are intentionally omitted.
Last run: 2026-08-03. No live identifiers are stored in this repository.

## Summary — current live acceptance

| Stage | Method | Result |
|-------|--------|--------|
| Unit suite | `pytest` | ✅ 97/97; core coverage 86% |
| Local pipeline | `demo`, `findings`, `correlate` CLI | ✅ |
| ZPR onboarding | `enable-zpr` (live) | ✅ ACTIVE / ENABLED |
| ZPR rule (real) | `scripts/seed_demo.py` → `create_zpr_policy` | ✅ ACTIVE |
| Security attributes | `create_security_attribute` (oracle-zpr `app`) | ✅ |
| Real inventory and coverage data | current-run collector | ✅ fresh evidence uploaded |
| Rule triggering | `scripts/trigger_rules.py` | ✅ all 5 flow classifications |
| LA fields + parser + source + log group | `provision-la --quiet` | ✅ every `provision_la.FIELD_TOKENS` field ready, source/parser updated |
| Current-run ingestion | `refresh --quiet` | ✅ 633/633 records indexed in the dashboard window |
| Dashboard query parse + execute | `validate-dashboards` | ✅ 40/40 queries, 0 errors; 38 data + 2 valid zero states |
| Management Dashboard import | `deploy-dashboard --quiet` | ✅ 7 dashboards, 40 tiles, 40 saved searches |

## End-to-end path (live in the approved target)

1. A read-only preflight resolves and context-binds the exact target without
   printing its identifier.
2. `refresh` collects inventory, coverage and sanitized gap records; correlates
   a uniquely selected project flow log; computes drift; uploads the evidence;
   advances state only after upload; and deletes the temporary staging file.
3. Every record is bound to an opaque current run ID and a common event time.
4. `validate-dashboards` parses and executes all 40 queries and requires the
   exact expected current-run record count inside the dashboard time window.
5. `deploy-dashboard` imports seven focused dashboards only after that gate.
6. A post-import API read verifies 7 dashboards, 40 tiles, and 40 saved searches.

## OCI Log Analytics — solved recipe (was the blocker)

A custom JSON parser create returns HTTP 500 unless configured exactly:

- `is_single_line_content=False` **with** `header_content="$:0"` (single-line=True → 500).
- `language="en_US"`, `encoding="UTF-8"`, `is_default=True`.
- Field maps: `field=LogAnalyticsField(name=<internal>)`,
  `parser_field_name`/`storage_field_name=<internal>`, `structured_column_info="$.<jsonKey>"`.
- Fields: `upsert_field` with **no** `name` creates (LA generates `udfsNN`); reuse
  existing fields by case-insensitive display name first.
- Source: `type_name="os_file"`, reference the parser; find an existing source by
  display name before upsert (OCI sets source iname = display name).

This recipe was cross-pollinated from the `oci-log-analytics-detections`
project's proven `setup_log_sources.py` and verified in the approved live target.

## Live resources

- ZPR was already enabled; no enforcement policy or security attribute was changed.
- One project-scoped flow log and one project state bucket were selected uniquely.
- LA contains the tenant-neutral project source/parser, 84 mapped fields, and
  the seven-dashboard suite.

## Reproduce (full e2e)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
terraform -chdir=terraform apply                          # logging layer
.venv/bin/oci-zpr-visibility provision-la --profile <PROFILE> --region <REGION> --quiet
.venv/bin/oci-zpr-visibility refresh --profile <PROFILE> --region <REGION> \
  --state-bucket <STATE_BUCKET> --flow-log-compartment-id <COMPARTMENT_OCID> \
  --flow-log-group-id <FLOW_LOG_GROUP_OCID> --flow-log-id <FLOW_LOG_OCID> \
  --flow-lookback-minutes 45 --json --quiet
.venv/bin/oci-zpr-visibility validate-dashboards --profile <PROFILE> --region <REGION> \
  --expected-run-id <OPAQUE_RUN_ID> --expected-record-count <UPLOADED_COUNT> --quiet
.venv/bin/oci-zpr-visibility deploy-dashboard --profile <PROFILE> --region <REGION> --quiet
```

## Continuous production path (scheduled Upload API)

The validated continuous path is to schedule the collector + LA upload (cron /
OCI Functions / OKE CronJob):

```bash
oci-zpr-visibility collect --auth instance_principal --region <REGION> \
    --snapshot /tmp/snap.json --records /tmp/recs.jsonl
python scripts/provision_la.py --upload /tmp/recs.jsonl   # idempotent provision + ingest
```

**Connector Hub does NOT fit the custom-source dashboards** (discovered live):
a `logging`-source Connector Hub connector to a LoggingAnalytics target requires
`logSourceIdentifier` to be null — it cannot target a custom source, so OCI
Logging records land under LA's built-in OCI-logs handling, not under
`OCI ZPR Visibility JSON`, and the dashboards (which filter on that source) would
not match. Therefore `create_log_analytics_connector` is left `false` for the
ZPR inventory path; ingest to the custom source via the Upload API instead.
(Connector Hub remains appropriate for VCN Flow Logs, which use the built-in
`OCI VCN Flow Unified Schema Logs` source.)
