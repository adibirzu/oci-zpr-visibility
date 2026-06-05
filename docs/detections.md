# ZPR Detection Rules

The dashboard's **Detections** tab turns ZPR records into detection rules. Each
rule matches a violation class and tags the matching records with a **Detection
label** (via Log Analytics `eval`), so the records are visible, queryable, and
ready to drive an OCI LA alert.

## Why `eval`-based labels (not source label conditions)

OCI Log Analytics also supports *inline label tagging* on a custom source
(`label_conditions` + a registered `Tag`/Label). On this tenancy the inline-label
registration path via the SDK proved unreliable and would require mutating the
live source (risking ingestion). The `eval Detection = '<label>'` approach is
**non-destructive**, applies the same labeling at query time, renders in the
dashboard, and is directly promotable to an alert — without touching the source.
If you prefer native labels, define them in **Administration → Labels** in the
console, then add a source label condition mapping the same field/value.

## Detection catalog

| Detection label | Record / condition | Severity | Meaning | Action |
|-----------------|--------------------|----------|---------|--------|
| `ZPR-Over-Permissive` | `zpr_enriched_flow` `classification = unexpected_accepted` | HIGH | A connection was **allowed** but matches no intended ZPR relationship — an over-permissive path. | Add an explicit ZPR relationship that captures the legitimate need, or remove the path. |
| `ZPR-Suspected-Misconfig` | `zpr_enriched_flow` `classification = suspected_misconfiguration` | HIGH | A connection to a **protected destination** was **rejected** where policy appears to intend allow. | Reconcile the policy statement with the intended relationship; check attribute tagging. |
| `ZPR-Blocked-Protected` | `zpr_enriched_flow` `action = REJECT and zpr_destination = true` | MEDIUM | Traffic blocked at a ZPR-protected destination (expected zero-trust behaviour; watch for spikes). | Confirm the blocks are intended; investigate sources generating them. |
| `ZPR-Broad-CIDR` | `zpr_finding` `finding_type = broad_cidr_exception` | HIGH | A policy grants a **broad CIDR** (e.g. `10.0.0.0/8`) instead of attribute-scoped access, weakening zero trust. | Replace the CIDR grant with attribute-to-attribute relationships. |
| `ZPR-Policy-Drift` | `zpr_policy_drift` (statement hash changed) | MEDIUM | A policy statement changed across runs. | Confirm the change was intended and reviewed. |

## Promoting a detection to an OCI LA alert

Each rule is just a saved query. To alert, create a **Scheduled Task → Alert** in
Log Analytics with the rule's query, for example:

```
'Log Source' = 'OCI ZPR Visibility JSON'
| where record_type = 'zpr_enriched_flow' and classification = 'unexpected_accepted'
| eval Detection = 'ZPR-Over-Permissive'
| stats count as hits by Detection, source_resource_name, destination_resource_name
```

Set a threshold (e.g. `hits > 0`), a schedule, and a notifications topic. The
`Detection` field gives every alerting/triage surface a consistent label.
