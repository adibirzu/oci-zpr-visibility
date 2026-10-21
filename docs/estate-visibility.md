# Resource estate visibility

The **Resource estate** tab in the OCI Log Analytics dashboard presents the
last observed inventory for the resource families collected by the refresh
job: Compute instances, VCNs, OKE clusters and node pools, and Autonomous
Databases. Inventory rows are emitted as `resource_inventory` records with the
resource identifier, resource family (`resource_type`), lifecycle state,
placement, protection status, and snapshot context.

The estate charts first aggregate by `resource_id` and `inventory_snapshot_time`,
then sort snapshots and deduplicate on `resource_id` before counting. OCI
requires `dedup` to operate on aggregated results. This keeps repeated
snapshots from inflating chart counts. Native tables remain raw observation
tables because the console adds raw system fields to table projections;
aggregation would break those bindings. Tables sort newest observations first
and expose snapshot time and run ID. Repeated snapshots can appear in the selected
time window; these tables are not deduplicated current-state inventories.
Multi-valued OKE subnet lists remain in the inventory payload, while the placement
table displays the observed scalar subnet and parent cluster when available.
These are observation views and do not prove
that a resource still exists or is currently readable. Placement is shown as observed OCI metadata;
missing IP data is left blank because an IP alone does not identify a resource
or establish ZPR protection.

Protection evidence is shown with the explicit `protection_status` and any
provider returned security attributes. An OKE cluster or node pool is inventory
context and does not by itself prove
native ZPR protection. The collection-gap table is the adjacent explanation
for a genuine zero: a zero inventory count can mean no matching resources or
that a collector could not read a family.

Snapshot freshness is grouped by `run_id` and reports the newest
observed snapshot and record count. It describes uploaded observations; it is
not provider-side proof that the current tenancy is complete. Use the run and
collection-health views to correlate freshness with the refresh outcome and
read-access gaps.

The dashboard queries and the parser fields are provisioned by
`provision-la`. No synthetic traffic is used by the estate view; flow widgets
remain separately marked as flow-dependent and retain their inferred ZPR
attribution qualifiers.

The parser reuses semantic Log Analytics fields: `Lifecycle State`,
`Availability Domain`, `Kubernetes Cluster ID`, `Protection Level`, `Status`,
`Operation`, and `Error Type`. JSON keys remain unchanged. This avoids spending
single-value STRING field slots on duplicate meanings. `subnet_ids` is multi-valued
STRING and `available_count` is LONG; existing fields are retained without type changes.
Oracle documents [field types and reuse](https://docs.oracle.com/en-us/iaas/log-analytics/doc/create-field.html)
and [aggregation functions](https://docs.oracle.com/en-us/iaas/log-analytics/doc/stats.html).

Dashboard imports preserve existing project-owned dashboard and saved-search IDs,
use current ETags, and add missing views. Ambiguous names, foreign ownership tags,
or read failures stop the importer; it does not delete dashboards before import.
Keep a private export before updating live content. Provider query validation
and indexed current-run records prove data availability; authenticated browser
rendering and scheduled collector execution require separate validation.

## Demo field quality and destination isolation

Raw native tables explicitly remove the host/entity/problem columns that do not
apply to policy, inventory and correlation records. Policy rows retain action,
source/destination selector types, parsed attribute and address lists, parser
confidence and unmodeled-filter evidence. Address alternatives can legitimately
be empty: an attribute selector does not imply a CIDR or IP selector.

Compute placement now includes provider VNIC observations for unprotected as
well as protected VMs, and the provider fault domain. OKE and Autonomous Database
have separate placement/lifecycle tables. Absent provider placement is left
absent. `RUNNING`, `ACTIVE`, and `AVAILABLE` are control-plane observations;
application, Kubernetes and SQL readiness need separate checks.

Use the same destination for all three commands:

```bash
oci-zpr-visibility provision-la --log-group-compartment-id <DESTINATION_COMPARTMENT_OCID> --log-group-name <LOG_GROUP_NAME>
oci-zpr-visibility refresh --state-bucket <STATE_BUCKET> --log-group-compartment-id <DESTINATION_COMPARTMENT_OCID> --log-group-name <LOG_GROUP_NAME>
oci-zpr-visibility deploy-dashboard --compartment-id <DESTINATION_COMPARTMENT_OCID> --log-group-id <LOG_GROUP_OCID>
oci-zpr-visibility validate-dashboards --compartment-id <DESTINATION_COMPARTMENT_OCID> --log-group-id <LOG_GROUP_OCID> --expected-run-id <RUN_UUID> --expected-record-count <RECORD_COUNT>
```

Provision and refresh preserve tenancy scope as their default for compatibility;
ORM passes the deployment compartment explicitly. Source/parser definitions are
tenancy-scoped; log groups, dashboards and refresh metrics use the deployment
compartment. Dashboard queries and validation constrain the exact log group.
Matching same-source records from another group cannot satisfy the acceptance
check. Family tables accept zero rows only when latest coverage confirms
`COLLECTED` and zero eligible resources; missing/partial coverage is unavailable.

The controller installs and enables its recurring schedule before initial
provider calls. A failed first run remains visible in bootstrap logs and can be
retried by cron. `flock` prevents overlapping refresh uploads. A scheduled,
indexed subsequent run is still required for live schedule acceptance.
