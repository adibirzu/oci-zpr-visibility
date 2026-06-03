# OCI ZPR Visibility Runbook

## Prerequisites

* OCI CLI config or an instance/resource principal with permissions for ZPR, Security Attributes, Resource Search, Networking, Logging, Connector Hub, and Log Analytics.
* A central observability compartment.
* A Log Analytics namespace and Log Analytics log group.
* VCN, subnet, or VNIC OCIDs selected for flow-log enablement.

## Deploy OCI resources

1. Copy the Terraform example values:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

2. Replace every placeholder in `terraform/terraform.tfvars` with values from your tenancy.

3. Initialize and apply:

```bash
terraform -chdir=terraform init
terraform -chdir=terraform plan
terraform -chdir=terraform apply
```

The `zpr_inventory_custom_log_ocid` output is the log ID used by the collector.

## Collect inventory and emit custom logs

```bash
python -m pip install -e .
oci-zpr-visibility collect \
  --profile DEFAULT \
  --region eu-frankfurt-1 \
  --snapshot out/zpr_snapshot.json \
  --records out/zpr_records.jsonl \
  --emit-log-id <ZPR_INVENTORY_CUSTOM_LOG_OCID>
```

For an OCI instance principal:

```bash
oci-zpr-visibility collect \
  --auth instance_principal \
  --region eu-frankfurt-1 \
  --emit-log-id <ZPR_INVENTORY_CUSTOM_LOG_OCID>
```

## Enable ZPR from the CLI

Terraform is the preferred controlled path. For SDK-driven onboarding validation:

```bash
oci-zpr-visibility enable-zpr --dry-run --output out/zpr_enable_dry_run.json
oci-zpr-visibility enable-zpr --output out/zpr_enable_response.json
```

## Correlate exported flow logs locally

If you export VCN flow records as JSONL:

```bash
oci-zpr-visibility correlate \
  --snapshot out/zpr_snapshot.json \
  --flows out/vcn_flow_logs.jsonl \
  --output out/zpr_enriched_flows.jsonl
```

Then emit the enriched records:

```bash
oci-zpr-visibility emit \
  --records out/zpr_enriched_flows.jsonl \
  --log-id <ZPR_INVENTORY_CUSTOM_LOG_OCID>
```

## Log Analytics

Create/import a custom source equivalent to `log_analytics/sources/oci_zpr_visibility_json_source.json`, using JSON parsing and `record_type` as the primary discriminator.

Use `log_analytics/dashboards/oci_zpr_visibility_dashboard.json` as the dashboard query catalog. OCI VCN Flow Logs should use the built-in VCN Flow Logs source configured in Terraform as `flow_log_analytics_source_identifier`.

## Validate log collection

After `terraform apply` creates the custom log, confirm the collection leg:

```bash
LOG_ID=$(terraform -chdir=terraform output -raw zpr_inventory_custom_log_ocid)
LG_ID=$(terraform -chdir=terraform output -raw logging_log_group_ocid)

# Emit records (use real inventory, or demo records to smoke-test)
.venv/bin/oci-zpr-visibility emit --profile <PROFILE> --region <REGION> \
  --records out/demo/records.jsonl --log-id "$LOG_ID"

# Confirm they landed in OCI Logging (GSL search; wait ~30-60s for ingestion)
oci logging-search search-logs --profile <PROFILE> \
  --search-query "search \"<TENANCY_OCID>/$LG_ID/$LOG_ID\"" \
  --time-start <RFC3339_START> --time-end <RFC3339_END> --limit 50
```

Expect one entry per emitted record, each with the original `record_type`.

## Log Analytics content (required before dashboards work)

The files under `log_analytics/` are design descriptors. A working LA deployment
also needs a JSON parser, custom fields, and a source created in LA, then the
Connector Hub connector enabled (`create_log_analytics_connector=true`). Validate
each dashboard query with the parse API (0 rows is OK; a 400 is a failure):

```bash
NS=$(oci os ns get --profile <PROFILE> --query 'data' --raw-output)
oci log-analytics query parse --namespace-name "$NS" --sub-system LOG \
  --profile <PROFILE> --query-string "<dashboard query>"
```

See [validation.md](validation.md) for the current validation status and the
exact remaining LA content gap.

## IAM (least privilege)

Collector principal (group or dynamic group `zpr-collector`):

```
Allow group zpr-collector to read zpr-family in tenancy
Allow group zpr-collector to read security-attribute-namespaces in tenancy
Allow group zpr-collector to read all-resources in tenancy
Allow group zpr-collector to use log-content in compartment <obs-compartment>
```

Connector Hub service principal (for the LA target):

```
Allow any-user to {LOG_ANALYTICS_LOG_GROUP_UPLOAD_LOGS} in compartment <obs-compartment>
  where all { request.principal.type='serviceconnector',
             target.loganalytics-log-group.id='<LA_LOG_GROUP_OCID>' }
```

## Operating model

* Run inventory collection every 15 minutes for live operations or daily for audit.
* Keep flow logs enabled on production VCNs/subnets that host ZPR-protected resources.
* Review HIGH and CRITICAL findings daily.
* Treat `unexpected_accepted` as a review queue, not as proof of a ZPR bypass.
* Treat `suspected_misconfiguration` as a connectivity triage queue where a flow was rejected even though policy correlation expected it to be allowed.
