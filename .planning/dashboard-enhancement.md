# Dashboard Enhancement Spec (native OCI Log Analytics)

Goal: turn the 14 bare query-widgets into an attractive, one-command-deployable
OCI Log Analytics dashboard. Uses ECC `dashboard-builder` skill conventions and
the validated `OCI ZPR Visibility JSON` source (all 14 queries already HIT).

## Current state
- `log_analytics/dashboards/oci_zpr_visibility_dashboard.json`: 5 tabs, 14 widgets, each `{name, query}` only — no visualization metadata.
- Import is manual (runbook). `validate_dashboards.py` executes queries (HIT/MISS/ERROR) but does not deploy.

## Target design

### Visualization mapping (add `visualization_type` + `visualization_options` + `layout` per widget)
| Widget | Viz | Layout |
|--------|-----|--------|
| Active ZPR policies, Protected resources | `tile` (KPI) | 3x3 |
| Open findings by severity | `tile` per severity / `pie` | 3x3 / 6x5 |
| Top findings (severity×type) | `sunburst` | 6x6 |
| Policy statement table, Resource detail | `table` / `records` | 12x5 |
| Source↔destination matrix | `bar` / `hbar` | 6x5 |
| Enriched ACCEPT vs REJECT | `bar` (stacked by classification) | 6x5 |
| Rejected protected destinations, Unexpected accepted | `link` (src→dst) | 12x6 |
| Policy drift candidates | `table` | 12x5 |

### New KPI tile row (tab 1)
- Active policies · Protected resources · Open CRITICAL+HIGH findings · Blocked flows (24h) · Unexpected-accepted (24h).

### Severity color semantics
- CRITICAL=red, HIGH=orange, MEDIUM=amber, LOW=grey via `visualization_options` color maps; consistent across widgets.

### Drill-downs
- Finding/flow widgets carry `ask_ai_prompts` + link parameters into the records view filtered by `record_type`/`severity`.

### Layout
- 12-column grid; set only `width`/`height` (let placement compute row/column), no overlapping tiles.

## Deliverables
1. Enriched `oci_zpr_visibility_dashboard.json` with viz metadata + new widgets.
2. `oci-zpr-visibility deploy-dashboard` subcommand (new module
   `oci_zpr_visibility/deploy_dashboard.py`): builds + imports the dashboard and
   embedded saved searches into OCI LA (idempotent, like `provision_la`).
3. Extended `validate_dashboards.py` to cover the new widgets; live 14→N HIT.
4. Unit tests: dashboard JSON schema (every widget has a valid `visualization_type`,
   widths 1–12, queries non-empty); layout non-overlap.
5. Docs: update `docs/architecture.md` + `docs/runbook.md` (deploy step) + screenshots note.

## Acceptance
- `pytest` green (new dashboard schema/layout tests).
- `oci-zpr-visibility validate-dashboards` → all widgets HIT in the staging tenancy.
- `oci-zpr-visibility deploy-dashboard --dry-run` shows the import plan; live deploy renders the dashboard with the new visualizations.
