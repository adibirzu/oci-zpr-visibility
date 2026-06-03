# OCI ZPR Visibility — Validation Report

Environment: **cap** tenancy (`pbncapgemini`, eu-frankfurt-1) staging.
Date: 2026-06-03. All values shown as placeholders; real OCIDs/namespace live
only in the gitignored `terraform/terraform.tfvars` and the tenancy.

## Summary

| Stage | Method | Result |
|-------|--------|--------|
| Unit suite | `pytest` on isolated `.venv` (oci 2.177.0) | ✅ 6/6 |
| Local pipeline | `demo`, `findings`, `correlate` CLI | ✅ correct classifications/findings |
| ZPR onboarding | `enable-zpr` (live) | ✅ ACTIVE / ENABLED |
| Collector (live) | `collect --profile cap` | ✅ runs; config object returned |
| Terraform IaC | `validate` + `plan` + `apply` (logging layer) | ✅ 2 resources created |
| **Log collection** | `emit` → OCI Logging → `logging-search` | ✅ 9/9 records, all 4 record_types |
| Log Analytics reachability | `log-analytics namespace list`, `query parse` | ✅ onboarded, query API live |
| **LA custom source + dashboards** | `query parse` against dashboard queries | ⚠️ blocked — see gap below |

## What was validated live

### Log collection (end-to-end into OCI Logging)
1. `terraform apply` created the Logging log group + `zpr-inventory` custom log.
2. `oci-zpr-visibility emit` sent 9 records (2 `zpr_policy_statement`,
   4 `zpr_finding`, 2 `zpr_enriched_flow`, 1 `zpr_resource`) to the custom log.
3. `oci logging-search search-logs` returned all 9 records within ~40s, each
   JSON-parseable with the expected `record_type`. The collection leg works.

### Log Analytics platform
- LA is **onboarded** in cap (`is-onboarded: true`, `is-data-ever-ingested: true`).
- The LA query API (`oci log-analytics query parse`, `--sub-system LOG`) is live
  and validates field references against LA metadata.

## Gap: Log Analytics custom content is not yet deployable

`query parse` on a dashboard query returns:

```
InvalidParameter: Invalid field for STATS BY: finding_type.
```

The dashboard queries reference bare custom field names (`record_type`,
`finding_type`, `severity`, `policy_id`, `classification`, …) that do **not**
exist as LA fields. The files under `log_analytics/` are **design descriptors**,
not LA-importable artifacts. A working LA deployment additionally requires:

1. A **JSON parser** (`UpsertLogAnalyticsParserDetails`) mapping each JSON key in
   the emitted records to an LA field.
2. **Custom fields** whose names the dashboard queries can reference. (A direct
   `upsert_field` with name `record_type` returns `Field not found`, so field
   creation must go through the parser-driven path / correct naming convention —
   this needs to be modeled against current OCI LA field conventions.)
3. A **source** (`UpsertLogAnalyticsSourceDetails`, JSON) binding the parser, so
   records ingested via Connector Hub are attributed to `OCI ZPR Visibility JSON`.
4. A **Connector Hub** connector (`oci_sch_service_connector` in `main.tf`,
   `create_log_analytics_connector=true`) from the custom log to the LA log group
   using that source identifier.

Acceptance test for that work: every query in
`log_analytics/dashboards/oci_zpr_visibility_dashboard.json` must pass
`oci log-analytics query parse` (0 rows is fine; a 400 is a failure).

## Live resources created in cap (cleanup)

- ZPR configuration (root) — ENABLED (has `prevent_destroy` in Terraform).
- Logging log group `zpr-visibility` + custom log `zpr-inventory`.

Managed by `terraform/` state. To remove the logging layer:
`terraform -chdir=terraform destroy` (ZPR config is protected; disable via the
ZPR API/console if intended).

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
.venv/bin/oci-zpr-visibility collect --profile cap --region eu-frankfurt-1 \
  --snapshot out/cap/zpr_snapshot.json --records out/cap/zpr_records.jsonl
# emit + search: see runbook.md "Validate log collection"
```
