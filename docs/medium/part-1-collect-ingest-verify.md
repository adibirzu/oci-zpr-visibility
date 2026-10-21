# Analyze OCI ZPR data in Log Analytics: collect, ingest and verify

*Part 1 of a practical Learn OCI series*


## Bring policy context into your network investigation

When a connection fails, your team needs more than a policy screenshot. You need to know which resources were observed, what security attributes they carried, and whether the inventory is current enough to explain the traffic you are investigating.

OCI ZPR data in Log Analytics gives you a place to search those observations and retain them across collection runs. You can compare policy statements, resource context and collection health before adding the VCN Flow Logs covered in Part 2.

Start with one approved compartment. Collect its records, upload them, and check that the exact run is indexed. An older chart can still look healthy after a collection fails, so verify freshness before building dashboards.

## Combine Oracle services with a scoped collector

[Zero Trust Packet Routing](https://docs.oracle.com/iaas/Content/zero-trust-packet-routing/overview.htm) uses security attributes and policies to express network access intent. [OCI Log Analytics](https://docs.oracle.com/iaas/log-analytics/home.htm) provides the log analysis workspace. The independent [OCI ZPR Visibility project](https://github.com/adibirzu/oci-zpr-visibility) connects the two by reading configuration and resource APIs and producing normalized JSON records.

The project addresses a practical gap: you need to search policy context alongside traffic, keep earlier snapshots, and see where collection failed. It complements the native [ZPR Visualizer](https://docs.oracle.com/iaas/Content/zero-trust-packet-routing/zpr-visualizer.htm): use the Visualizer for native relationships and Log Analytics for the project's retained observations and queries.

Your collection follows this path:

```text
ZPR configuration and OCI resource APIs
  → snapshot and normalized JSONL
  → Log Analytics fields, JSON parser and source
  → compartment-scoped log group
  → Log Explorer queries and dashboards
```

Keep the services and permissions distinct:

**Collection.** Configure approved compartments and API read access. Verify snapshot, record types and collection gaps.

**Parsing.** Configure fields, JSON parser and source. Verify extracted fields and event time.

**Ingestion.** Configure destination log group and upload access. Verify records indexed for the new run ID.

**Analysis.** Configure compartment, log group and time window. Verify queries return the intended evidence.

The collector and its review rules are independent project code, not an Oracle product or an official Oracle deliverable.

## Read the records before interpreting the dashboard

Start with the record families that answer your operating questions:

- `zpr_policy_statement`: what policy statements were collected?
- `zpr_resource` and `resource_inventory`: what resource and attribute evidence was observed?
- `zpr_finding`: which configuration patterns need review?
- `zpr_coverage` and `zpr_collection_gap`: where is collection complete, partial or unavailable within the configured scope?
- `zpr_run`: did this collection run succeed, and was flow collection configured?

`COLLECTED`, `PARTIAL` and `NOT_COLLECTED` describe collector visibility. They do not certify security coverage or tenancy-wide completeness. Likewise, a finding is a rule-based review candidate; confirm the original policy before changing it.

Every normalized record carries time and run context. `event_time` determines the Log Analytics time selection, `inventory_snapshot_time` identifies the snapshot, and `run_id` groups records produced by the collector.

![Native Log Analytics collection-health dashboard showing run metadata and collection statuses](images/collection-health-latest.png)

*Figure 1. Latest native collection-health table, October 9, 2026. The 19:17:26 UTC run reports 574 flows and zero collection errors. Its `record_count` is the base collector count, not the total 646-record upload. The 24-hour selector includes earlier manual runs; this does not establish scheduled collection.*

## Fix the field model before trusting the table

The first policy table in this lab had timestamps but mostly empty Entity, Entity Type and Host Name columns. A policy observation has no host identity to populate those columns. Your first check should be the original JSON and the parser mapping, followed by the table query.

The updated parser exposes the policy's `attribute_references`, `cidrs` and `ips` as multi-value fields. It also retains action, source and destination selector details, statement hashes and parsing confidence. A reused field must have the correct type and multi-value setting; a same-named incompatible field now stops provisioning instead of silently accepting a broken mapping.

In the table query, select the fields that answer the policy question and remove inappropriate system columns:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where record_type = 'zpr_policy_statement'
| fields policy_name, action, attribute_references, cidrs, ips,
  parser_confidence, statement_hash, statement_index, run_id,
  -Entity, -'Entity Type', -'Host Name (Server)', -'Problem Priority', -Label
```

The [fields command](https://docs.oracle.com/iaas/log-analytics/doc/fields.html) can add or remove result columns. A policy may use attribute selectors without CIDRs, or CIDRs without named resources. Those empty alternatives are valid; filling them with made-up values would weaken the investigation.

## Verify indexing before building views

In **Log Analytics → Log Explorer**, select the ingestion compartment, the dedicated log group, and a window containing your collection's event time. First query the record families:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| stats count as records by record_type
```

Then filter the exact new run:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where run_id = '<YOUR_RUN_ID>'
| stats count as indexed_records
```

Compare this count with the local JSONL file, rather than the `record_count` field alone. That field counts the collector's base records. The complete file can also contain findings, enriched flows and the run summary.

Once indexing matches, inspect policy context:

```text
'Log Source' = 'OCI ZPR Visibility JSON'
  and 'Log Group' = '<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
| where record_type = 'zpr_policy_statement'
| fields policy_name, statement, parser_confidence,
  statement_hash, statement_index, run_id
```

The policy table can contain several statements per policy and repeated snapshots. Its row count is not necessarily the number of policies. `parser_confidence` is a categorical parsing assessment, not a probability that a policy is secure.

![Native policy-inventory dashboard showing statement metadata and resource relationships](images/policy-fields.png)

*Figure 2. Native OCI policy table after the dashboard replacement on October 9, 2026. Parsed policy and selector fields replace empty host-oriented columns. Private policy text is hidden; inspect the complete statement in your own environment.*

Check the JSONL output, extracted fields and indexed count separately. If a policy field is missing from the source file, changing the dashboard cannot recover it. If it exists in JSON but is blank in Log Explorer, check the parser.

## Practical lab: collect and upload your first scope

### 1. Prepare access and choose the source revision

Use Python 3.10 or later, an OCI profile and a region where Log Analytics is enabled. The scoped collection and estate features described here were tested in a local working revision on October 9, 2026. Before following the commands, check that your revision includes them; a public clone may not yet contain those changes. Choose an inventory compartment and a separate ingestion compartment if your operating model requires it.

Review the [Log Analytics Quick Start](https://docs.oracle.com/iaas/log-analytics/doc/quick-start.html), [ZPR IAM policy reference](https://docs.oracle.com/iaas/Content/zero-trust-packet-routing/policy-reference.htm), and [Log Analytics IAM catalog](https://docs.oracle.com/iaas/log-analytics/doc/iam-policies-catalog-logging-analytics.html). Collection needs read access; provisioning, upload, queries and dashboard management have separate requirements.

Install a reviewed source revision:

```bash
git clone https://github.com/adibirzu/oci-zpr-visibility.git
cd oci-zpr-visibility
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
oci-zpr-visibility --version
git rev-parse HEAD
oci-zpr-visibility collect --help
```

Before a live collection, confirm that help includes `--collection-compartment-id`. If it is missing, stop and obtain the revision supporting this walkthrough. Removing the flag would broaden the scope rather than fix the version mismatch.

### 2. Run the sample workflow, then collect real inventory

First check the local pipeline:

```bash
oci-zpr-visibility demo --output-dir out/tutorial-demo
```

This uses bundled examples. Keep its output separate from your real collection:

```bash
export OCI_PROFILE='<YOUR_OCI_PROFILE>'
export OCI_REGION='<YOUR_OCI_REGION>'
export INVENTORY_COMPARTMENT_OCID='<INVENTORY_COMPARTMENT_OCID>'
export LA_COMPARTMENT_OCID='<LA_COMPARTMENT_OCID>'
umask 077
mkdir -p out/tutorial-live

oci-zpr-visibility collect \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --collection-compartment-id "$INVENTORY_COMPARTMENT_OCID" \
  --snapshot out/tutorial-live/snapshot.json \
  --records out/tutorial-live/inventory.jsonl \
  --json
```

Repeat the scope flag for each additional approved inventory compartment. These are exact scopes, not a recursive child-compartment selection. ZPR configuration reads can still require tenancy-level permissions because its service scope differs from resource collection.

Summarize the output without printing raw inventory:

```bash
python - <<'PY'
from collections import Counter
import json
from pathlib import Path
rows = [json.loads(line) for line in Path('out/tutorial-live/inventory.jsonl').read_text().splitlines() if line.strip()]
print('JSONL records:', len(rows))
print('Record types:', dict(Counter(row['record_type'] for row in rows)))
for row in rows:
    if row['record_type'] == 'zpr_run':
        print({key: row.get(key) for key in ('run_id', 'collection_status', 'flow_collection_status', 'collection_error_count')})
PY
```

Expect `NOT_CONFIGURED` for flow collection in this inventory-only step. Investigate collection gaps before concluding that an absent resource family has no resources.

### 3. Configure a dedicated Log Analytics destination

The updated CLI accepts an explicit ingestion compartment. Keep its destination separate from the inventory and OCI Logging source scopes:

```bash
export LA_LOG_GROUP_NAME='zpr-tutorial-la'
oci-zpr-visibility provision-la \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --log-group-compartment-id "$LA_COMPARTMENT_OCID" \
  --log-group-name "$LA_LOG_GROUP_NAME" \
  --quiet
```

This provisions or reuses the fields, parser, source and named group. The custom fields, parser and source remain namespace-level content; the log group belongs to your selected compartment. Omitting `--log-group-compartment-id` retains the tenancy-root default, so include it in your runbook.

Copy the destination group's OCID from **Administration → Log Groups** into your private environment:

```bash
export LA_LOG_GROUP_OCID='<DESTINATION_LOG_ANALYTICS_LOG_GROUP_OCID>'
```

Replace that placeholder in the query examples with your own value. It refers to the Log Analytics destination, not the OCI Logging group that holds VCN Flow Logs.

In **Log Analytics → Administration**, check:

1. **Fields:** the query fields exist with the intended types.
2. **Parsers:** **OCI ZPR Visibility JSON Parser** maps the JSON fields, including event time.
3. **Sources:** **OCI ZPR Visibility JSON** selects that parser.
4. **Log Groups:** `zpr-tutorial-la` belongs to your ingestion compartment.

The parser maps `event_time` to system Time. For the estate fields, it maps `lifecycle_state` to **Lifecycle State** and `protection_status` to **Protection Level**. Match these display names when querying. See [Create a Field](https://docs.oracle.com/iaas/log-analytics/doc/create-field.html) for the field model.

### 4. Upload once and verify the new run

Upload once to the same explicit destination:

```bash
oci-zpr-visibility provision-la \
  --profile "$OCI_PROFILE" \
  --region "$OCI_REGION" \
  --log-group-compartment-id "$LA_COMPARTMENT_OCID" \
  --log-group-name "$LA_LOG_GROUP_NAME" \
  --upload out/tutorial-live/inventory.jsonl \
  --quiet
```

Alternatively, use **Administration → Uploads → Upload Files**, choosing the file, destination log group and custom source. Follow [Upload Logs on Demand](https://docs.oracle.com/iaas/logging-analytics/doc/upload-logs-demand.html) for the wizard.

Choose one upload method. Upload acceptance does not prove indexing, and repeating an upload can add duplicate observations. Use the run-ID query above to verify the result.

## Compare your run with the recorded lab result

The recorded lab snapshot was collected on October 9, 2026, at **19:17:26 UTC**. Its combined upload contained **646 records**, including **34 resource-inventory observations** and **574 real flow observations**. The other records carried policy, findings, coverage and run context.

The validator checked the exact destination log group and run ID, then found all 646 records indexed. It also executed all **49 dashboard widget queries**: **44 returned data**, and **five returned permitted zero states**. Collection gaps were zero for this recorded run. These are lab receipts, not expected counts for your tenancy.

Your inventory-only file from this part will contain fewer record families. Match your own JSONL length and run ID; do not try to reproduce the lab count by uploading twice.

## Troubleshoot the collection and ingestion layers

**An API call is denied.** Profile, region, selected scope and operation-specific IAM access.

**A resource family is absent.** Coverage and collection-gap records.

**Upload is accepted but queries are empty.** Ingestion compartment, log group, indexing and event-time selection.

**Rows exist but fields are blank.** Original JSON, parser mappings, field types and whether the selected columns apply to that record family.

**Counts differ between widgets.** Policy statements versus policies; observations versus distinct resources.

Keep snapshots and raw records private. Share only approved, sanitized examples. If you created tutorial content solely for this test, review dependencies before deleting it; fields and sources may be shared by other collectors.

## Next step: add observed traffic to the same investigation

Use the [project's collection and ingestion workflow](https://github.com/adibirzu/oci-zpr-visibility) with a reviewed revision and verify one exact run in your environment. In Part 2, you will add VCN Flow Logs and use the same source to investigate traffic, resource state and collection freshness.

### Public implementation resources

- [Collector implementation](https://github.com/adibirzu/oci-zpr-visibility/blob/main/oci_zpr_visibility/collector.py)
- [Log Analytics provisioner](https://github.com/adibirzu/oci-zpr-visibility/blob/main/oci_zpr_visibility/provision_la.py)
- [Bundled examples](https://github.com/adibirzu/oci-zpr-visibility/tree/main/examples)
