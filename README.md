# OCI ZPR Visibility

End-to-end starter implementation for OCI Zero Trust Packet Routing visibility:

* Enables tenancy-level ZPR with Terraform or the OCI Python SDK.
* Enables OCI VCN Flow Logs into OCI Logging.
* Routes flow logs and custom ZPR inventory records to OCI Log Analytics through Connector Hub.
* Collects ZPR configuration, policies, security attributes, protected resources, and IP/resource mappings.
* Emits normalized policy, resource, finding, and enriched flow records.
* Provides Log Analytics source and dashboard query assets.

Oracle’s current ZPR SDK exposes `ZprClient` methods including `create_configuration`, `get_configuration`, `list_zpr_policies`, and `get_zpr_policy`. The OCI Terraform provider exposes `oci_zpr_configuration` to onboard ZPR in the root compartment. VCN Flow Logs expose ACCEPT/REJECT network decisions and fields such as source/destination address, protocol, VNIC OCID, subnet OCID, and compartment OCID; they do not provide a dedicated ZPR deny-reason field, so this project uses explicit policy/resource correlation.

Primary Oracle references:

* [OCI Python SDK ZprClient](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/zpr/client/oci.zpr.ZprClient.html)
* [Terraform oci_zpr_configuration](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/zpr_configuration.html)
* [VCN Flow Log details](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_vcn_flow_logs.htm)
* [Connector Hub Terraform resource](https://registry.terraform.io/providers/oracle/oci/latest/docs/resources/sch_service_connector)

## Architecture

See [docs/architecture.md](docs/architecture.md) for the end-to-end design:
two ingestion paths (Python inventory/findings + VCN Flow Logs) converging in
OCI Log Analytics through Connector Hub, the collector internals, the detection
logic, and the IAM model.

## Install

Use an isolated virtual environment so the project's `oci>=2.176.0` does not
collide with other tools (notably the OCI CLI, which pins its own SDK version):

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/oci-zpr-visibility --help
```

## Local demo

```bash
python -m oci_zpr_visibility.cli demo --output-dir out/demo
```

This uses `examples/sample_snapshot.json` and `examples/sample_flow_logs.jsonl` to produce:

* `out/demo/snapshot.json`
* `out/demo/records.jsonl`
* `out/demo/enriched_flows.jsonl`

## Deploy

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
terraform -chdir=terraform init
terraform -chdir=terraform plan
terraform -chdir=terraform apply
```

Then emit inventory to the custom log:

```bash
python -m pip install -e .
oci-zpr-visibility collect \
  --profile DEFAULT \
  --region <REGION> \
  --emit-log-id <ZPR_INVENTORY_CUSTOM_LOG_OCID>
```

See [docs/runbook.md](docs/runbook.md) for the full operator flow.
