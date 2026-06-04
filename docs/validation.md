# OCI ZPR Visibility — End-to-End Validation Report

Environment: **cap** tenancy (`pbncapgemini`, eu-frankfurt-1) staging.
Last run: 2026-06-04. All values shown as placeholders; real OCIDs/namespace
live only in the gitignored `terraform/terraform.tfvars` and the tenancy.

## Summary — fully green

| Stage | Method | Result |
|-------|--------|--------|
| Unit suite | `pytest` on isolated `.venv` (oci 2.177.0) | ✅ 6/6 |
| Local pipeline | `demo`, `findings`, `correlate` CLI | ✅ |
| ZPR onboarding | `enable-zpr` (live) | ✅ ACTIVE / ENABLED |
| ZPR rule (real) | `scripts/seed_cap.py` → `create_zpr_policy` | ✅ `zpr-visibility-demo` ACTIVE |
| Security attributes | `create_security_attribute` (oracle-zpr `app`) | ✅ |
| Real inventory data | `collect --profile cap` | ✅ 2 statements + 6 findings |
| Rule triggering | `scripts/trigger_rules.py` | ✅ all 5 flow classifications |
| Log collection | `emit` → OCI Logging → `logging-search` | ✅ all records, 4 record_types |
| LA fields + parser + source + log group | `scripts/provision_la.py` | ✅ 40 fields, JSON parser, source, log group |
| LA ingestion | `provision_la.py --upload` (Upload API) | ✅ status 200 |
| **Dashboards (execute)** | `scripts/validate_dashboards.py` | ✅ **21/21 widgets HIT, 0 MISS, 0 ERROR** |

## End-to-end path (all live in cap)

1. `seed_cap.py` creates the `app` security attribute + the `zpr-visibility-demo`
   ZPR policy (web→db relationship + broad-CIDR exception `10.0.0.0/8`).
2. `collect` reads the live policy → real `zpr_policy_statement` + `zpr_finding`
   records (incl. HIGH `broad_cidr_exception`).
3. `trigger_rules.py` produces flows covering every classification.
4. `provision_la.py` creates the LA custom fields, JSON parser, source
   (`OCI ZPR Visibility JSON`), and log group, then `--upload` ingests the records.
5. `validate_dashboards.py` executes all 14 dashboard queries → **14/14 HIT**.

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
project's proven `setup_log_sources.py` and verified live in cap.

## Live resources in cap

- ZPR configuration (ENABLED, `prevent_destroy`) + ZPR policy `zpr-visibility-demo`.
- Security attribute `app` in `oracle-zpr`.
- OCI Logging log group `zpr-visibility` + custom log `zpr-inventory` (terraform).
- LA: 40 custom fields, parser `oci_zpr_visibility_json_parser`, source
  `OCI ZPR Visibility JSON`, log group `zpr-visibility-la`.

## Reproduce (full e2e)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
terraform -chdir=terraform apply                          # logging layer
.venv/bin/python scripts/seed_cap.py        --profile cap --region eu-frankfurt-1
.venv/bin/oci-zpr-visibility collect        --profile cap --region eu-frankfurt-1 --skip-resources \
    --snapshot out/cap/zpr_snapshot.json --records out/cap/zpr_records.jsonl
.venv/bin/python scripts/trigger_rules.py   --out out/cap/trigger_records.jsonl
cat out/cap/zpr_records.jsonl out/cap/trigger_records.jsonl > out/cap/all_records.jsonl
.venv/bin/python scripts/provision_la.py    --profile cap --region eu-frankfurt-1 --upload out/cap/all_records.jsonl
.venv/bin/python scripts/validate_dashboards.py --profile cap --region eu-frankfurt-1   # expect 14/14 HIT
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
