# Use it on your existing ZPR setup

The bundled Resource Manager stack creates a self-contained demo (a VCN, two
endpoints, a policy, flow logs). If you **already run ZPR** in a tenancy, you
don't want the demo lab — you want the same visibility against your real
policies, attributes, and traffic. This guide covers that path.

## 1. Discover what you already have

`discover` does a **read-only** pass over your tenancy and prints a summary plus
the exact commands to stand up continuous collection. It needs only read access
to ZPR, Security Attributes, Core (VCN/Compute), Identity, and Logging.

```bash
oci-zpr-visibility discover --auth api_key --profile <profile> --region <region>
# or on an OCI instance / function:
oci-zpr-visibility discover --auth instance_principal
oci-zpr-visibility discover --json   # machine-readable
```

Example output:

```
=== OCI ZPR discovery ===
tenancy : ocid1.tenancy.oc1..xxxx
region  : eu-frankfurt-1
ZPR     : enabled (ENABLED)

Policies (1):
  - zpr-visibility-demo  [ACTIVE]  2 statement(s)

oracle-zpr attributes: app, db, fin-network, ops, web
Protected resources  : 3 (Vcn=1, instance=2)

VCN Flow Logs found (13):
  - <FLOW_LOG_NAME>
      group: ocid1.loggroup.oc1.<region>.xxxx
      log  : ocid1.log.oc1.<region>.xxxx
  ...
```

It searches the tenancy root **and the ACTIVE compartment subtree** for VCN Flow
Logs (`source.service == flowlogs`). To scope to one compartment, pass
`--compartment-id <ocid>`.

If `ZPR: NOT enabled`, enable it once (tenancy-wide, singleton) before
collection has anything to read:

```bash
oci-zpr-visibility enable-zpr --profile <profile> --region <region>
# or the Console / Terraform oci_zpr_configuration
```

If **Protected resources = 0**, your resources don't carry `oracle-zpr`
attributes yet — tag the VCNs/instances you want governed, then re-run discover.
(Note: OCI Resource Search omits `securityAttributes`, so this tool enumerates
via `list_vcns` / `list_instances` — that is expected.)

## 2. Provision the Log Analytics source (idempotent)

Creates the custom fields (`provision_la.FIELD_TOKENS`), the JSON parser, the
`OCI ZPR Visibility JSON` custom source, and the `zpr-visibility-la` log group.
Safe to re-run.

```bash
oci-zpr-visibility provision-la --auth api_key --profile <profile> --region <region>
```

Required IAM (the on-demand-upload set):
`use loganalytics-ondemand-upload`, `use loganalytics-log-group`,
`read loganalytics-source`.

## 3. Run one refresh (collect → correlate → upload → metrics)

Use the flow-log OCIDs that `discover` printed. The `--state-bucket` is any
Object Storage bucket the principal can write — it holds the previous snapshot
for drift detection.

```bash
oci-zpr-visibility refresh \
  --auth api_key --profile <profile> --region <region> \
  --state-bucket <bucket> \
  --flow-log-compartment-id <flow_log_compartment_ocid> \
  --flow-log-group-id <flow_log_group_ocid> \
  --flow-log-id <flow_log_ocid>
```

Omit the `--flow-log-*` flags to upload inventory, findings, and drift without
live traffic correlation (the allow/block KPIs will be empty until you add them).

## 4. Import the dashboard

```bash
oci-zpr-visibility deploy-dashboard --auth api_key --profile <profile> --region <region>
```

Open **Log Analytics → Dashboards → OCI ZPR Visibility** — the focused dashboard
suite described in [the README](../README.md#what-the-dashboard-shows).

## 5. Make it continuous

Pick the mode that matches how you operate — same `refresh` unit either way.

### Controller VM (cron)

On any OCI compute instance with an instance-principal dynamic group granted the
collector permissions, install the package and add a 15-minute cron:

```cron
*/15 * * * * /opt/zpr/.venv/bin/oci-zpr-visibility refresh \
  --auth instance_principal --region <region> \
  --state-bucket <bucket> \
  --flow-log-compartment-id <c> --flow-log-group-id <g> --flow-log-id <l> >> /var/log/zpr-refresh.log 2>&1
```

### OCI Function (serverless)

Deploy `functions/func.py` (resource principal) and pass the same values as
function config (`STATE_BUCKET`, `REGION`, `FLOW_LOG_COMPARTMENT_ID`,
`FLOW_LOG_GROUP_ID`, `FLOW_LOG_ID`). Drive it from Connector Hub, API Gateway, or
a scheduler. See [deployment-modes.md](deployment-modes.md).

## IAM the collector needs (read-only, plus LA upload)

| Purpose | Policy verbs (examples) |
|---------|-------------------------|
| Read ZPR | `read zpr-policy`, `read zpr-configuration` |
| Read attributes | `read security-attribute-namespaces`, `read security-attributes` |
| Read inventory | `read vcns`, `read instances`, `read vnics`, `read subnets`, `read compartments` |
| Read flow logs | `read log-groups`, `read log-content` |
| Upload to LA | `use loganalytics-ondemand-upload`, `use loganalytics-log-group`, `read loganalytics-source` |
| Dashboard | `manage management-dashboard`, `manage management-saved-search` |
| Metrics | `use metrics` (publish) |
| Drift state | `manage objects` (the state bucket only) |
