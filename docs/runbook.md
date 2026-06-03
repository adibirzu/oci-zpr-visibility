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

## Operating model

* Run inventory collection every 15 minutes for live operations or daily for audit.
* Keep flow logs enabled on production VCNs/subnets that host ZPR-protected resources.
* Review HIGH and CRITICAL findings daily.
* Treat `unexpected_accepted` as a review queue, not as proof of a ZPR bypass.
* Treat `suspected_misconfiguration` as a connectivity triage queue where a flow was rejected even though policy correlation expected it to be allowed.
