# Live Console Verification — cap (pbncapgemini), eu-frankfurt-1

Captured 2026-06-05 against the live lab. OCIDs / private IPs redacted per policy.

## 1. Dashboard renders in the OCI LA console (the fix)

Screenshot: `screenshots/01_dashboard.png` — **OCI ZPR Visibility** dashboard,
all 21 widgets rendering with real data, **no error banner**.

Before the fix the console rendered every widget blank (Oracle JET unhandled
exception) or showed *"Invalid field for FIELDS after STATS: Time"*. These were
invisible to SDK `validate-dashboards` because that path never instantiates the
JET visualization layer. Root causes fixed (commit `fix(dashboard): render in
OCI LA console`):

| Symptom (console only) | Root cause | Fix |
|---|---|---|
| Whole dashboard blank, JET `reading 'localName'` | `scopeFilters: []` (array) | scopeFilters as an object (LogGroup/Entity/LogSet) |
| Widgets never paint | `visualizationOptions: {}` empty | real per-viz keys (bar/hbar/sunburst/table/tile) |
| Time binding off | `timeSelection: "P30D"` (ISO) | LA token `"l30d"` |
| `Invalid field for FIELDS after STATS: Time` | `table` widgets ending in `stats` (console appends raw `time,id,…`) | tables are raw-record `fields` projections, never end in `stats` |
| Drift widget errors / 0 rows | post-`stats` field-to-field `where` (unsupported) | read emitted `zpr_policy_drift` records; added `old_hash`/`new_hash` fields |

Verified live: **0 failing widget queries, 0 console error banners** (captured
via CDP Network on a fresh browser tab).

Live KPI values at capture (**Last 7 Days** window): Active policies **3**,
Protected resources **10**, Critical+High findings **231**, Blocked flows
**23**, Unexpected accepted **26** — all five KPIs populated, including the two
flow KPIs (VCN Flow Logs lag ~10–15 min, so a ≥6h window is needed for those;
counts accumulate across the 15-min collector cron over the window). A 60-min
window shows the policy/resource/finding widgets but 0 flows, which is expected.

## 2. Security attributes ARE present (`oracle-zpr` namespace)

```
Security Attribute Namespaces:  oracle-zpr  state=ACTIVE
Attributes in 'oracle-zpr':     app (List, ACTIVE) + values: web, db, fin-network, ops, …
```

## 3. ZPR configuration + policy

```
ZPR Configuration:  state=ACTIVE  zpr_status=ENABLED
ZPR Policies (1):   zpr-visibility-demo  state=ACTIVE
  stmt: in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints
  stmt: in app:fin-network VCN allow app:ops endpoints to connect to '10.0.0.0/8'
```

## 4. Protected resources (security-attributed, enforce mode)

| Kind | Name | oracle-zpr.app |
|------|------|----------------|
| VCN | zpr-visibility-vcn | value=fin-network, mode=enforce |
| Instance | zpr-visibility-web | value=web, mode=enforce |
| Instance | zpr-visibility-db | value=db, mode=enforce |

Resource enumeration uses the Core APIs (`list_vcns`/`list_instances`), not
Resource Search — Resource Search omits `securityAttributes`.
