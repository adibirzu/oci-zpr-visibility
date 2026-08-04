# Serverless collector — OCI Functions

Run the ZPR Visibility collector as an OCI Function instead of a VM. The function
executes the same `refresh` unit (collect → drift → Upload API → metrics) using a
**resource principal** — no API keys, no instance to manage.

## Build & deploy

```bash
# 1. Context (one-time)
fn create context zpr --provider oracle
fn use context zpr
fn update context oracle.compartment-id <COMPARTMENT_OCID>
fn update context api-url https://functions.<region>.oraclecloud.com
fn update context registry <region>.ocir.io/<tenancy-namespace>/zpr

# 2. Application
fn create app zpr-visibility --annotation oracle.com/oci/subnetIds='["<SUBNET_OCID>"]'

# 3. Deploy this function (installs the package from GitHub at build time)
cd functions
fn -v deploy --app zpr-visibility

# 4. Configure it
fn config function zpr-visibility zpr-visibility-refresh STATE_BUCKET zpr-visibility-state
fn config function zpr-visibility zpr-visibility-refresh REGION <region>
fn config function zpr-visibility zpr-visibility-refresh FLOW_LOG_COMPARTMENT_ID <COMPARTMENT_OCID>
fn config function zpr-visibility zpr-visibility-refresh FLOW_LOG_GROUP_ID <FLOW_LOG_GROUP_OCID>
fn config function zpr-visibility zpr-visibility-refresh FLOW_LOG_ID <FLOW_LOG_OCID>

# 5. Invoke once to verify
echo '{}' | fn invoke zpr-visibility zpr-visibility-refresh
```

## IAM (resource principal)

Create a dynamic group that matches the function, then grant it the same access
the collector needs:

```
# Dynamic group: ALL {resource.type = 'fnfunc', resource.compartment.id = '<COMPARTMENT_OCID>'}

Allow dynamic-group zpr-fn to manage loganalytics-features-family in tenancy
Allow dynamic-group zpr-fn to manage management-dashboard-family in tenancy
Allow dynamic-group zpr-fn to read all-resources in tenancy
Allow dynamic-group zpr-fn to use metrics in tenancy
Allow dynamic-group zpr-fn to manage objects in compartment id <COMPARTMENT_OCID>
```

The ORM stack creates equivalent statements automatically in Function mode.
Scope object access further for production if your tenancy policy budget allows
bucket-level conditions.

## Scheduling (so it runs all the time)

The function is stateless and idempotent; the drift baseline lives in the state
bucket, so each invocation stands alone.

OCI Functions are invoked **event- or request-driven** — by the
[Events service](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm),
[Connector Hub](https://registry.terraform.io/providers/oracle/oci/latest/docs/resources/sch_service_connector),
API Gateway, Notifications, or the SDK/CLI (`oci fn function invoke ...`). There
is **no native cron-for-Functions** in core OCI today (OCI Resource Scheduler
only starts/stops Compute and Autonomous Database — it does not invoke
functions). So for time-based collection you either:

- invoke this function on a cron you already operate (any host/pipeline), or
- use the **controller-VM mode** (the ORM stack), which ships a 15-minute cron
  out of the box and needs no external scheduler.

For "collect all the time with zero external dependencies", the controller VM is
the recommended autonomous mode; the Function is ideal for event/on-demand runs
or when you already have a scheduler.

## Notes

- Function sync timeout is 300s. A very large tenancy collection can exceed that;
  if so, prefer the controller VM, or split collection (`--skip-resources` on a
  separate cadence).
- This function runs `refresh` only (it does not import the dashboard). Deploy the
  dashboard once with `deploy-dashboard` (or let the ORM controller do it).
- Set the `FLOW_LOG_*` config keys to populate traffic KPIs from live VCN Flow
  Logs. Without them the Function still uploads inventory, findings, drift,
  coverage/collection-health records, and metrics.
