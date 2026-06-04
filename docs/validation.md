# OCI ZPR Visibility — End-to-End Validation Report

Environment: **cap** tenancy (`pbncapgemini`, eu-frankfurt-1) staging.
Last run: 2026-06-04. All values shown as placeholders; real OCIDs/namespace
live only in the gitignored `terraform/terraform.tfvars` and the tenancy.

## Summary

| Stage | Method | Result |
|-------|--------|--------|
| Unit suite | `pytest` on isolated `.venv` (oci 2.177.0) | ✅ 6/6 |
| Local pipeline | `demo`, `findings`, `correlate` CLI | ✅ |
| ZPR onboarding | `enable-zpr` (live) | ✅ ACTIVE / ENABLED |
| **ZPR rule (real)** | `scripts/seed_cap.py` → `create_zpr_policy` | ✅ `zpr-visibility-demo` ACTIVE |
| Security attributes | `create_security_attribute` (oracle-zpr `app`) | ✅ |
| **Real inventory data** | `collect --profile cap` | ✅ 2 statements + 6 findings |
| **Rule triggering** | `scripts/trigger_rules.py` | ✅ all 5 flow classifications |
| **Log collection** | `emit` → OCI Logging → `logging-search` | ✅ 26/26 records, 4 record_types |
| LA fields | `scripts/provision_la.py` | ✅ 40 fields, LA log group |
| **Dashboard queries** | `query parse` (live LA) | ✅ 14/14 valid |
| LA JSON parser + source | `upsert_parser` | ⚠️ service-side HTTP 500 (see below) |
| Connector Hub → LA | terraform | ⏸ pending working source |

## What was validated live, end to end

1. **Real ZPR rule.** `seed_cap.py` creates the `app` security attribute and a
   ZPR policy with two statements (a `web→db` relationship and a broad-CIDR
   exception `10.0.0.0/8`). The policy is ACTIVE in cap.
2. **Real data.** `collect` reads the live policy and emits real
   `zpr_policy_statement` records (parsed at HIGH confidence) and real
   `zpr_finding` records, including a HIGH `broad_cidr_exception` for `10.0.0.0/8`.
3. **Rule triggering.** `trigger_rules.py` produces flows that exercise every
   classification: `expected_accepted`, `expected_blocked`, `unexpected_accepted`,
   `suspected_misconfiguration`, `needs_enrichment`. In production these come
   from real VCN Flow Logs (`terraform flow_log_targets`).
4. **Collection.** 26 records (real collect + triggered) emitted to the
   `zpr-inventory` custom log; `logging-search` confirms all 26 with the four
   record types intact.
5. **Dashboards.** All 14 dashboard queries pass `oci log-analytics query parse`
   against live LA, after the 40 custom fields were created. A real bug was fixed
   in the dashboard assets: `dc()` (Splunk) → `distinctcount()` (OCI LA).

## Known issue: LA custom JSON parser returns HTTP 500

`upsert_parser` for a custom JSON parser returns a deterministic
`500 InternalError` in this tenancy/region, even when the field-map shape
exactly mirrors a working built-in JSON parser (verified by cloning
`azureVnetFlowLogJsonParser`). Root-cause hypothesis: custom fields created via
`upsert_field` lack facet/table-eligibility flags that the parser validator
expects, and those flags are not settable through the public field API.

Impact: fields, log group, and all dashboard queries are validated, but JSON
records ingested via Connector Hub will not auto-extract into the custom fields
until the parser + source exist.

Workaround / next step: create the JSON parser and the `OCI ZPR Visibility JSON`
source in the OCI Console (Logging Analytics → Parsers → Create JSON parser,
mapping each `$.key` to its field), then enable the Connector Hub connector
(`create_log_analytics_connector=true`). `provision_la.py` already creates the
fields and log group and is idempotent; only the parser/source step is blocked.

## Live resources in cap (cleanup)

- ZPR configuration (ENABLED, `prevent_destroy`) + ZPR policy `zpr-visibility-demo`.
- Security attribute `app` in `oracle-zpr`.
- OCI Logging log group `zpr-visibility` + custom log `zpr-inventory` (terraform).
- LA log group `zpr-visibility-la` + 40 custom fields.

Remove logging layer: `terraform -chdir=terraform destroy`. ZPR policy/attributes
and LA fields are created by the scripts and can be deleted via API/console.

## Reproduce (full e2e)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
terraform -chdir=terraform apply        # logging layer (enable_zpr=false if already on)
.venv/bin/python scripts/seed_cap.py        --profile cap --region eu-frankfurt-1
.venv/bin/oci-zpr-visibility collect        --profile cap --region eu-frankfurt-1 --skip-resources \
    --snapshot out/cap/zpr_snapshot.json --records out/cap/zpr_records.jsonl
.venv/bin/python scripts/trigger_rules.py   --out out/cap/trigger_records.jsonl
cat out/cap/zpr_records.jsonl out/cap/trigger_records.jsonl > out/cap/all_records.jsonl
.venv/bin/oci-zpr-visibility emit           --profile cap --region eu-frankfurt-1 \
    --records out/cap/all_records.jsonl --log-id "$(terraform -chdir=terraform output -raw zpr_inventory_custom_log_ocid)"
.venv/bin/python scripts/provision_la.py    --profile cap --region eu-frankfurt-1
# then: create JSON parser+source in console, enable connector, run dashboard queries
```
