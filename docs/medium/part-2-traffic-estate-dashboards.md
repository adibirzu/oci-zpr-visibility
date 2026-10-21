# Investigate OCI ZPR traffic with Log Analytics dashboards

*Part 2 of a practical Learn OCI series*


## Start with the failed connection, then test the explanation

A connection can fail even when a ZPR policy appears to allow it. Your team still needs to check the endpoint, observed traffic and other network controls. If you jump from a rejected flow to a policy change, you can change the wrong layer without fixing the application.

OCI ZPR traffic in Log Analytics helps you put the investigation evidence together: policy context, resource observations, flow actions and collection health. In Part 1, you verified collection and indexing. Here, you will add VCN Flow Logs, inspect the project's review classifications, and use dashboards to decide what to check next.

By the end, you can trace a flow observation back to its resource and policy context, check whether that context is fresh, and choose the next troubleshooting step. The correlation remains an inference.

## Keep flow evidence separate from policy inference

[VCN Flow Logs](https://docs.oracle.com/iaas/Content/Network/Concepts/vcn-flow-logs.htm) describe observed traffic collected through OCI Logging. Their action, endpoint tuple and capture status provide network evidence. The [flow-log reference](https://docs.oracle.com/iaas/Content/Logging/Reference/details_for_vcn_flow_logs.htm) explains the record fields.

The independent collector correlates those records with its inventory snapshot and the policy features it models. That comparison adds investigation context; it does not identify the provider control that caused acceptance or rejection.

[ZPR](https://docs.oracle.com/iaas/Content/zero-trust-packet-routing/overview.htm) operates alongside routes, network security groups and security lists. Your application listener and host firewall can also affect a connection. Keep those checks in the investigation.

Use these fields together:

**`action`.** What ACCEPT or REJECT action was observed?

**`review_classification`.** What comparison does the project suggest reviewing?

**`correlation_confidence` and `correlation_reason`.** How complete is the endpoint and policy context?

**`zpr_attribution`.** Is this inference or a provider-issued verdict?

**Event and snapshot times.** Does the inventory apply to the traffic window?

The project's attribution value is `INFERRED_NOT_PROVIDER_VERDICT`. A missing endpoint, reused address, overlapping private address space, stale snapshot or unsupported policy filter can limit the comparison.

## Use ZPR dashboards to choose your next check

Begin with **Collection health**. Confirm a recent run and inspect inventory and flow collection independently. An empty review table is meaningful only when the required source data is present.

Next, open **Allow block traffic**. Review the traffic distribution, trends and capture quality, then open an observation requiring investigation.

![Native Log Analytics traffic dashboard showing actions, review trends and capture quality](images/traffic-latest.png)

*Figure 1. Redacted native OCI lab capture, October 9, 2026, with Last 24 Hours selected. The action chart counts distinct modeled flow paths; trend and capture-quality widgets count observations. Their totals have different meanings.*

The latest bounded lab collection used a 15-minute window, ending at 19:17:50 UTC on October 9, 2026, and returned **574 flow records: 127 ACCEPT and 447 REJECT**. Those are observations, not application requests or unique connections. The screenshot uses a wider display window; do not equate every widget total with the bounded collection count.

The review classes guide your investigation:

- **`policy_consistent_accept`:** verify that the observed acceptance aligns with the relevant full policy.
- **`accepted_requires_policy_review`:** check endpoint mapping, complete policy intent and unmodeled filters.
- **`rejected_protected_destination`:** investigate rejected traffic targeting a resource with observed protection context.
- **`rejected_policy_expected_allow`:** check other network and application layers as well as the policy model.
- **`needs_enrichment`:** improve the inventory or policy context before drawing a conclusion.

For configuration analysis, use [Network Path Analyzer](https://docs.oracle.com/iaas/Content/Network/Concepts/path_analyzer.htm) where applicable. Keep its configuration findings separate from your application result and observed flow evidence.

## Add resource state without overstating workload health

When you inspect a flow, you also need to know which resources sit behind its endpoints. The expanded collector records Compute, VCN, OKE and Autonomous Database observations, including lifecycle state and available attribute evidence.

![Native resource-estate dashboard with Autonomous Database lifecycle rows](images/adb-placement.png)

*Figure 2. Updated native estate view with OKE and Autonomous Database observations. Both databases are AVAILABLE and now have VCN placement resolved from their actual subnets. OCIDs are shortened; SQL access and application connectivity remain unverified.*

![Native Compute and OKE tables showing real private IPs, shortened OCIDs and lifecycle state](images/compute-placement.png)

*Figure 3. Updated native Compute and OKE tables. Private IPs and shortened OCIDs show real placement without exposing public IPs or FQDNs. The latest inventory time is 19:17:26 UTC; older snapshots remain in the 24-hour view.*

The latest snapshot contains nine monitored Compute instances, all RUNNING, and two Autonomous Databases, both AVAILABLE. OKE provider inventory reports an ACTIVE pool with two ACTIVE workers. The three cluster observations include two DELETED clusters; only one represents an active cluster.

Your placement fields need the same care as lifecycle fields. OCI's VNIC response supplies a subnet ID but no VCN ID, so the collector resolves the VCN through the subnet. Autonomous Database uses the same lookup, and a node pool can use its parent cluster's reported VCN. All nine VM inventory rows now contain a provider-derived VCN, subnet and private IP. A failed lookup becomes a collection gap, not a fabricated placement value.

Exclude deleted resources when counting the active estate. If attribute evidence is unavailable, investigate the collection gap before judging protection. `UNATTRIBUTED` means no association was observed by this collection; it does not prove that every relevant protection mechanism is absent.

For OKE, compare your actual cluster and networking configuration with [Oracle's ZPR support guidance](https://docs.oracle.com/iaas/Content/ContEng/Tasks/contengusingzpr.htm). A cluster lifecycle state is not a substitute for node, pod or application checks.

## Give each view an operating question

Your dashboard suite is most useful when each view has a clear purpose:

**Executive posture.** What policy, resource and review evidence is available?

**Policy inventory.** What statements and attribute relationships were collected?

**Protected resource map.** What attribute and placement context is available?

**Resource estate.** What resource lifecycle and inventory state was observed?

**Allow block traffic.** What traffic needs review?

**Drift governance.** What retained configuration evidence needs comparison?

**Detections.** Which review candidates should an operator inspect?

**Collection health.** Is the evidence fresh, and where are the collection gaps?

![Latest native collection-health table showing successful manual runs and flow counts](images/collection-health-latest.png)

*Figure 4. Latest native run table, with the 19:17:26 UTC snapshot at the top. All visible runs were manual. The total indexed run count was verified separately from the table's base collector count.*

The enhanced suite contains **eight dashboards and 49 widgets**. Exact-group validation returned **44 DATA** and **five ZERO_ALLOWED** results, with no errors or unavailable widgets. Provider readback also confirmed every stored query matched the enhanced definition. The recreated views also rendered in the authenticated OCI console. Scheduled collection and application connectivity still need separate tests.

These views reduce the switching between policy, resource and traffic screens during an investigation. The collection-health view also tells you when the evidence is too incomplete to support a conclusion.

A zero result needs an explanation. Family-specific estate widgets are allowed to show zero only when the latest coverage evidence says collection succeeded and no eligible resources exist. Missing or partial coverage is reported as unavailable. This prevents an empty OKE or ADB table from looking like a verified empty estate.

## Practical lab: add real flows and query the result

### 1. Select an existing flow source

Use the reviewed source revision and inventory snapshot from Part 1. The estate and existing-network additions described here were tested locally on October 9, 2026; they are not evidence of an accepted live existing-VCN deployment. In OCI, identify an enabled VCN Flow Log associated with the network you intend to observe.

**OCI Logging** holds the source flow log. **Log Analytics** holds the normalized evidence. Their log-group identifiers are different.

```bash
export FLOW_COMPARTMENT_OCID='<OCI_LOGGING_COMPARTMENT_OCID>'
export FLOW_LOG_GROUP_OCID='<OCI_LOGGING_LOG_GROUP_OCID>'
export FLOW_LOG_OCID='<VCN_FLOW_LOG_OCID>'
```

In **Logging → Log Groups**, open the source log and check a recent window before correlating. Verify its resource association, capture status and sample records. If flow logging needs to be enabled, obtain the network owner's approval for the capture scope, filter and cost.

Use existing authorized application activity. If you need a test request, agree on the source, destination, port and expected application result. Record the request time. A running machine alone does not prove that the application is generating useful traffic.

### 2. Correlate flows against the snapshot

```bash
oci-zpr-visibility correlate \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --snapshot out/tutorial-live/snapshot.json \
  --compartment-id "$FLOW_COMPARTMENT_OCID" \
  --flow-log-group-id "$FLOW_LOG_GROUP_OCID" \
  --flow-log-id "$FLOW_LOG_OCID" \
  --lookback-days 1 \
  --output out/tutorial-live/enriched-flows.jsonl \
  --json
```

This CLI takes lookback **days**; the example fetches one day. The 15-minute lab receipt used a separately bounded SDK query. Do not describe this command as that same window.

Count the output and find its run ID:

```bash
python - <<'PY'
from collections import Counter
import json
from pathlib import Path
rows = [json.loads(line) for line in Path('out/tutorial-live/enriched-flows.jsonl').read_text().splitlines() if line.strip()]
print('Flow records:', len(rows))
print('Actions:', dict(Counter(row.get('action') for row in rows)))
print('Review classes:', dict(Counter(row.get('review_classification') for row in rows)))
print('Run ID:', rows[0]['run_id'] if rows else 'No records: check the source')
PY
```

If source records exist but enrichment is incomplete, check the snapshot scope, endpoint association and policy model. The standalone command creates a separate run ID and does not create a `zpr_run` refresh summary.

### 3. Upload to the same dedicated destination

```bash
oci-zpr-visibility provision-la \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --log-group-compartment-id "$LA_COMPARTMENT_OCID" \
  --log-group-name "$LA_LOG_GROUP_NAME" \
  --upload out/tutorial-live/enriched-flows.jsonl \
  --quiet
```

In Log Explorer, select the destination compartment and log group, and include the fetched event times in the time picker. Count only the enrichment run:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where run_id = '<ENRICHMENT_RUN_ID>'
| stats count as indexed_records
```

Compare it with the local file. Repeated uploads or overlapping fetch windows can duplicate observations.

### 4. Investigate a review candidate

Start with the distribution:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where record_type = 'zpr_enriched_flow'
| stats count as flow_records by review_classification
```

Then inspect accepted traffic requiring review:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where record_type = 'zpr_enriched_flow'
  and review_classification = 'accepted_requires_policy_review'
| fields event_time, source_resource_name, source_ip,
  destination_resource_name, destination_ip, destination_port,
  protocol, action, correlation_confidence, correlation_reason,
  zpr_attribution, flow_id, run_id
```

Use `rejected_policy_expected_allow` to investigate rejected traffic that the model expected to allow. Verify endpoint mapping and the complete statement before changing policy. Check the application listener, host firewall, routes, NSGs and security lists as separate layers.

### 5. Query the estate and latest observations

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where record_type = 'resource_inventory'
| fields resource_name, resource_type, 'Lifecycle State',
  'Protection Level', 'Status', inventory_snapshot_time, run_id
| sort -inventory_snapshot_time
```

The parser maps JSON keys to semantic field names: `lifecycle_state` becomes **Lifecycle State**, and `protection_status` becomes **Protection Level**.

Recurring snapshots repeat resources. For a chart of latest observed lifecycle per resource, use:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where record_type = 'resource_inventory'
| stats latest('Lifecycle State') as lifecycle by resource_id, inventory_snapshot_time
| sort -inventory_snapshot_time
| dedup resource_id
| stats count as resources by lifecycle
```

The tested query shape aggregates before `dedup`. For a Compute-only table, use `where resource_type = literal(instance)`; the native `instance` field can otherwise be interpreted as the comparison target. Oracle documents `literal()` in the [where command reference](https://docs.oracle.com/iaas/log-analytics/doc/where.html). “Latest” still means latest within the selected window, so check freshness independently. Raw native tables can show repeated observations; they need a different query shape from aggregated charts. Refer to [Log Analytics stats](https://docs.oracle.com/iaas/log-analytics/doc/stats.html) when adapting the aggregation.

### 6. Review and import the dashboard content

Preview the target configuration:

```bash
export DASHBOARD_COMPARTMENT_OCID='<DASHBOARD_COMPARTMENT_OCID>'
oci-zpr-visibility deploy-dashboard \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --compartment-id "$DASHBOARD_COMPARTMENT_OCID" \
  --log-group-id "$LA_LOG_GROUP_OCID" \
  --dry-run
```

Back up existing content and review ownership. After approval, execute the same command without `--dry-run`.

Open **Log Analytics → Dashboards** in the dashboard compartment. Set **Log Group Compartment** to the ingestion compartment and choose the relevant event window. Dashboard storage and log-data storage can be in different compartments.

Match the queries, parser and collector to the same reviewed revision. Check stored content, executed queries and fresh indexing separately. The explicit log-group argument also constrains the generated saved-search queries, so a wider console filter cannot silently mix another project's records into your suite.

For routine updates, preserve dashboard and saved-search identifiers. In this lab, the owner specifically requested deletion and recreation: all eight dashboards received new IDs, and the old IDs returned 404. Update bookmarks after a replacement.

The replacement hit the tenancy's saved-search limit after three successful imports. The remaining five dashboards reused their existing searches. Export both dashboards and their searches, preserve concurrency tokens, and prepare recovery before any deletion. Review shared-search references before cleanup; deleting unrelated searches to make room would cross the ownership boundary. The [dashboard import reference](https://docs.oracle.com/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/management-dashboard/dashboard/import.html) explains that existing resources are updated and missing resources are created.

Validate your own combined refresh run against its exact destination:

```bash
export EXPECTED_RUN_ID='<YOUR_NEW_RUN_ID>'
export EXPECTED_RECORD_COUNT='<TOTAL_JSONL_RECORDS>'
oci-zpr-visibility validate-dashboards \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --compartment-id "$LA_COMPARTMENT_OCID" \
  --log-group-id "$LA_LOG_GROUP_OCID" \
  --expected-run-id "$EXPECTED_RUN_ID" \
  --expected-record-count "$EXPECTED_RECORD_COUNT" \
  --lookback-minutes 60 \
  --quiet
```

The recorded lab run indexed all 646 records. Use the total from your file, including summary records, and select a window containing its event times. Keep the separate standalone enrichment run distinct from a full refresh run.

## Extend the test to recurring collection and existing VCNs

The `refresh` command adds previous-run state in Object Storage, policy comparison and minute-based flow collection. It now accepts the same explicit child-compartment Log Analytics destination used in Part 1:

```bash
export STATE_BUCKET='<YOUR_EXISTING_STATE_BUCKET>'
export OBSERVED_VCN_OCID='<YOUR_APPROVED_VCN_OCID>'
oci-zpr-visibility refresh \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --collection-compartment-id "$INVENTORY_COMPARTMENT_OCID" \
  --state-bucket "$STATE_BUCKET" \
  --log-group-compartment-id "$LA_COMPARTMENT_OCID" \
  --log-group-name "$LA_LOG_GROUP_NAME" \
  --flow-log-compartment-id "$FLOW_COMPARTMENT_OCID" \
  --flow-log-group-id "$FLOW_LOG_GROUP_OCID" \
  --flow-log-id "$FLOW_LOG_OCID" \
  --flow-vcn-id "$OBSERVED_VCN_OCID" \
  --flow-lookback-minutes 15 \
  --quiet
```

This command writes previous-run state, uploads normalized records and publishes metrics. Review those targets and permissions before executing it. It shows the minute-based path; the recorded lab snapshot was assembled and uploaded manually, so this command is not evidence that a deployed controller's schedule succeeded.

Before scheduling:

1. Confirm inventory scopes, the OCI Logging source, Log Analytics destination and state bucket independently.
2. Supply both flow-log identifiers, or omit both for inventory-only collection; a partial pair is rejected.
3. Review interval, filters, lookback and retention together. Overlapping windows can repeat observations.
4. Verify several scheduled runs by exact run ID and event time. One manual success is insufficient.
5. Inspect inventory gaps and flow failures independently. Policy drift needs a retained previous run; an initial empty result does not establish no change.

The existing-network ORM configuration also offers an observer mode. Create a **separate stack** with a unique prefix rather than converting a stack that owns a lab network. The relevant inputs are:

```hcl
name_prefix                    = "zpr-estate-observer"
network_mode                   = "existing"
existing_vcn_ocid               = "<EXISTING_VCN_OCID>"
existing_controller_subnet_ocid = "<CONTROLLER_SUBNET_OCID>"
existing_flow_log_group_ocid    = "<OCI_LOGGING_GROUP_OCID>"
existing_flow_log_ocid          = "<FLOW_LOG_OCID>"
observation_compartment_ocid    = "<FLOW_LOG_COMPARTMENT_OCID>"
collection_compartment_ocids    = ["<INVENTORY_COMPARTMENT_OCID>"]
controller_assign_public_ip    = false
```

These inputs supplement the stack's required tenancy, deployment compartment, region, availability domain and image values. You can omit both flow-log identifiers for inventory-only observation.

Use [Resource Manager](https://docs.oracle.com/iaas/Content/ResourceManager/Concepts/resourcemanager.htm) to create and review a saved plan before apply. Confirm that existing network, flow-log and workload resources are not changed, and review new controller resources and IAM grants. Verify that the supplied subnet and flow-log association match the intended VCN, and that the private observer can reach the required OCI endpoints.

This mode has local configuration validation; the lab did not include an accepted existing-VCN plan/apply or workload acceptance test. Treat the rollout as a separate deployment with its own evidence requirements.

## Read the ORM plan before calling the deployment complete

The upgraded lab package passed **182 local tests** and Terraform formatting and validation. Its provider saved PLAN succeeded on October 9, 2026, at **19:20:15 UTC**, with **six additions, three in-place changes and four destructions**. The replacements were the controller, web VM, database VM and collector package object; the service gateway and endpoint routes were retained.

An apply would interrupt those lab VMs. No apply was performed in this test. Independent security/release review, instance-principal execution, scheduled refresh, HTTP, SQL and Kubernetes Ready checks remain pending. The separate existing-VCN mode is locally validated, without live deployment acceptance.

The bootstrap now pins 16 dependency-wheel versions and checks their hashes. Their digests were matched against official PyPI release metadata. Terraform supplies the collector archive's SHA-256, which the guest checks before extraction; the collector wheel then installs without dependency resolution. Bootstrap still downloads SDK wheels and signed OS packages, and egress is not constrained. These controls improve artifact integrity without proving guest execution.

The controller installs its recovery schedule before the first provider calls and uses a lock to avoid overlapping refreshes. Explicit empty or blank inventory scopes fail closed; flow-log read grants follow the observation compartment independently of inventory scopes. Verify those behaviors in your deployed environment before treating them as acceptance.

## Troubleshoot and clean up by ownership

**Traffic widgets are empty.** Source flow records, fetch window, collection status and indexing.

**Review classifications look inconsistent.** Endpoint mapping, full policy semantics and confidence.

**Resource totals grow every run.** Latest observations versus raw rows.

**OKE is ACTIVE but the application fails.** Nodes, pods, service endpoints and authenticated access.

**ADB is AVAILABLE but the client fails.** Approved connection method, reachability and database authentication.

**Views render but become stale.** Schedule, run IDs, event times and the exact selected log group.

**Compute VCN is blank but a subnet exists.** Subnet lookup permission and the collector revision; the VNIC response alone has no VCN field.

**A known Compute family query returns zero.** Use `resource_type = literal(instance)` to avoid interpreting `instance` as a field.

**Dashboard import exceeds saved-search quota.** Existing-search reuse, ownership and export-backed recovery.

If you remove the observer, stop its schedule or connector first and review its destroy plan. Delete only observer-owned resources. Reused VCNs, flow logs, databases and clusters remain under their original owners. API-created Log Analytics content is outside Terraform ownership and needs a separate dependency and cleanup review.

## Next step: verify one connection through the workflow

Choose one approved source and destination in your environment. Verify the application result, find the relevant flow observation, compare the policy and resource context, and record what remains uncertain. Use the [OCI ZPR Visibility repository](https://github.com/adibirzu/oci-zpr-visibility) from the reviewed source revision to repeat that workflow.

### Public implementation resources

- [Flow collection](https://github.com/adibirzu/oci-zpr-visibility/blob/main/oci_zpr_visibility/flow_logs.py)
- [Correlation logic](https://github.com/adibirzu/oci-zpr-visibility/blob/main/oci_zpr_visibility/correlate.py)
- [Dashboard query catalog](https://github.com/adibirzu/oci-zpr-visibility/blob/main/log_analytics/dashboards/oci_zpr_visibility_dashboard.json)
- [Scheduled refresh](https://github.com/adibirzu/oci-zpr-visibility/blob/main/oci_zpr_visibility/refresh.py)
