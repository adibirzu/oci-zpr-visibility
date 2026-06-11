# Deployment modes — running autonomously in OCI

**Does this project need an external computer to run the scripts? No.** It is
designed to run entirely inside OCI with no laptop, bastion, or CI runner in the
loop. Your workstation is only needed if you *want* to run the CLI ad hoc.

There are three autonomous modes. All three authenticate with an OCI principal
(no API keys) and feed the same Log Analytics custom source.

| Mode | Compute | Auth | Schedule | Best for |
|------|---------|------|----------|----------|
| **Controller VM** (default, in the ORM stack) | 1 small VM | instance principal | built-in 15-min cron | zero-dependency, works in any region today |
| **OCI Function** (`functions/`) | serverless | resource principal | Events / Connector Hub / API Gateway / SDK cron (no native function cron) | no VM to patch; pay-per-run; event/on-demand |
| **Management Agent VM** | 1 VM + agent | instance principal | cron + agent | shops standardizing on Management Agent for log/metric forwarding |

## 1. Controller VM (default — already autonomous)

The Resource Manager stack provisions a small controller instance that, via
**instance principal**, bootstraps the Log Analytics fields/parser/source, imports
the dashboard, ingests the first snapshot, and installs a **15-minute cron** that
re-runs `refresh` forever. This is the answer to "can it run without an external
computer" — it already does. Nothing else is required after `terraform apply`.

```
*/15 * * * * root oci-zpr-visibility refresh --auth instance_principal \
  --region <region> --state-bucket zpr-visibility-state \
  --flow-log-compartment-id <COMPARTMENT_OCID> \
  --flow-log-group-id <FLOW_LOG_GROUP_OCID> --flow-log-id <FLOW_LOG_OCID>
```

## 2. OCI Function (serverless)

For teams that don't want a VM, the same `refresh` unit runs as an OCI Function
using a **resource principal**. Build and deploy from `functions/` (see
[functions/README.md](../functions/README.md)). State (the drift baseline) lives
in the Object Storage bucket, so each invocation is independent. Functions are
invoked event/request-driven (Events, Connector Hub, API Gateway, SDK/CLI);
there is **no native cron-for-Functions** in core OCI — OCI Resource Scheduler
only starts/stops Compute and ADB — so for periodic runs invoke it from a
scheduler you already operate, or use the controller VM for built-in cron.
Set `FLOW_LOG_COMPARTMENT_ID`, `FLOW_LOG_GROUP_ID`, and `FLOW_LOG_ID` in the
Function config when you want live traffic KPIs from VCN Flow Logs.

Trade-off: Functions have a 300-second sync timeout — fine for typical tenancies,
but a very large collection may need the VM mode (or a split cadence with
`--skip-resources`).

## 3. Management Agent VM

If your standard is the OCI **Management Agent**, run the collector on the agent
host. Be precise about the division of labour: the Management Agent is excellent
at *continuous log and metric forwarding* (for example, shipping the VCN Flow Logs
or host metrics into Logging Analytics), but it does **not** call the ZPR / Core
REST APIs itself. The ZPR inventory still comes from the collector process — so in
practice this mode is "a VM running the package on a cron, with the Management
Agent installed alongside for log/metric pipelines." It buys you the agent's
managed log collection; it does not replace the API collector.

## Which should I pick?

- Want it running today, anywhere, with one apply → **Controller VM**.
- Want serverless and pay-per-run, and you have a scheduler → **Function**.
- Already invested in Management Agent pipelines → **Management Agent VM** (plus the package on a cron).

All three are autonomous: once deployed, the dashboard stays current with no
external machine involved.
