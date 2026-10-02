# One-Click Deployment — Oracle Resource Manager

The `orm/` stack provisions the entire ZPR visibility lab **and** its Log
Analytics content + dashboard in one apply. Build the zip, upload it as a
Resource Manager stack, and apply.

**Review status (October 2, 2026):** the previously recorded RM plan is
historical and does not cover the current local ZIP. The current package must
be uploaded as a new stack version and receive a fresh plan before any apply.
Local tests and Terraform validations do not establish provider readiness. See the
[lifecycle review](resource-manager-lifecycle-review.md) and
[self-contained RM runbook](self-contained-resource-manager.md).

## What the stack creates

| Module (file) | Resources |
|---------------|-----------|
| `network.tf` | VCN (ZPR-tagged `oracle-zpr.app=fin-network`), private controller and endpoint subnets, NAT + Oracle Services Network gateway routes, security list, subnet VCN Flow Logs |
| `zpr.tf` | `app` security attribute in the `oracle-zpr` namespace + a ZPR policy (web→db allow; broad-CIDR exception) |
| `compute.tf` | 2 ZPR-tagged endpoints — `web` (app=web) and `db` (app=db) — generating intra-VCN traffic (web→db allowed; db→web denied by ZPR) |
| `storage.tf` | drift-state bucket + a bucket holding the collector package |
| `controller.tf` | controller VM + a dynamic group (matching just that instance) + least-privilege IAM policy; cloud-init installs the collector and runs `provision-la` + `deploy-dashboard` + `refresh` via **instance principal** |
| `functions.tf` | optional OCI Functions application + function resource + resource-principal IAM for `deployment_mode = "function"` |

In `controller_vm` mode, after apply the controller (no API keys) builds the LA
custom source + fields + JSON parser, imports the dashboard suite,
ingests inventory + findings + drift, publishes Monitoring metrics, and
installs a supervised 15-minute systemd timer with VCN Flow Log correlation.
Bootstrap only announces completion after its initial refresh succeeds; the
timer uses bounded retry and overlap protection. This is an installation
contract, not proof of live data until state, Log Analytics, and dashboard
queries are checked. In `function` mode, the
stack creates the Functions application, resource-principal IAM, state bucket,
flow logs, and optional function resource; invoke it through your scheduler.

## Build the stack zip

```bash
scripts/build_orm_zip.sh        # -> orm-stack.zip (terraform + package tarball + schema.yaml)
```

## Deploy via Resource Manager (Console)

1. **Developer Services → Resource Manager → Stacks → Create stack**.
2. Source: **.zip file** → upload `orm-stack.zip` (Terraform is at the zip root; `schema.yaml` drives the variable form).
3. Fill the form: Compartment, Region, Availability Domain, Oracle Linux 9 image
   (E3.Flex), optional SSH key, and Autonomy mode.
   - `controller_vm` is the default: creates the controller VM and a supervised
     15-minute systemd timer.
   - `function` creates an OCI Functions application and resource-principal IAM;
     set `function_image` after you push the OCIR image with `fn deploy`.
4. **Plan** → review → **Apply**.
5. After ~10–15 min (boot + bootstrap + flow-log latency), open **Log Analytics → Dashboards → OCI ZPR Visibility**.

## Deploy via CLI (local terraform)

```bash
cd orm && terraform init
terraform apply \
  -var config_file_profile=<oci-profile> \
  -var tenancy_ocid=<TENANCY_OCID> \
  -var compartment_ocid=<COMPARTMENT_OCID> \
  -var region=<REGION> \
  -var availability_domain=<AD> \
  -var instance_image_ocid=<OL9_E3FLEX_IMAGE_OCID>
```
(Resource Manager injects auth; `config_file_profile` is only for local runs.)

## IAM note

The controller/function dynamic group is granted the least-privilege set in
`orm/variables.tf`: Log Analytics features, management dashboards, read access
for the collector's OCI inventory calls, metrics publishing, and object writes
to the lab compartment for drift/package state. It does not use the earlier
lab-only `manage all-resources` grant.

## Teardown (stop billing)

```bash
python3.11 orm/rm_lifecycle.py destroy \
  --config <PRIVATE_LIFECYCLE_CONFIG> --auth config --profile <PROFILE>
# After ownership cleanup, create and review a fresh RM destroy plan/job.
```
The endpoint instances are billable while running. In `controller_vm` mode, the
controller instance is billable too; in `function` mode, the Function is
pay-per-use and has no built-in cron. The controller ownership journal removes
only verified installation-owned Log Analytics content before the reviewed RM
destroy. Shared fields and foreign dashboards/searches are preserved; ambiguous
ownership or unknown bucket objects stop teardown. Keep external ZPR/Log
Analytics singleton foundation services intact.

## Idempotency / re-deploy

Repeat deployment is not yet provider-accepted. `deploy-dashboard` now refuses
existing same-name dashboards rather than deleting them; ownership-aware upgrades
remain a blocker. Package/revision changes can replace the controller and upload
object, so review a fresh saved plan before applying any new artifact.

The ZIP builder explicitly includes only reviewed deployment files. Arbitrary
local tfvars, state, dotenv, keys, receipts, and new HCL are not included.
Collector inputs are Python modules and two reviewed descriptors, not recursive
source-directory contents. Run `bash scripts/build_orm_zip.sh` followed by
`python3.11 scripts/check_release_artifacts.py` to verify source parity. The
allowlist is not a secret scanner: reviewed source must still be redaction-checked.

## OCI4CCA IMDSv2 and failed-apply recovery

Some OCI tenancies require IMDSv2 and reject an instance launch when legacy
IMDSv1 remains enabled. Every `oci_core_instance` in this repository explicitly
sets `instance_options.are_legacy_imds_endpoints_disabled = true`. Keep that
setting when adding or changing a controller, lab endpoint, or standalone demo
instance. OCI resources that are not Compute instances do not expose IMDS and
therefore have no equivalent setting.

If a Resource Manager apply fails after creating a subset of resources, do not
retry the failed job. Update the stack source, create a fresh plan, review every
add/change/destroy action, and apply only that new plan with
`FROM_PLAN_JOB_ID`. A replacement of the stack-owned package object is expected
when its archive changes; any other destroy requires an ownership review.

`get-job-logs-content` can return a JSON envelope whose `data` field contains
the plain Terraform log. Extract that field before searching for the `Plan:`
summary or error markers. Do not expose raw job logs, OCIDs, IP addresses, or
instance user-data in troubleshooting receipts.

## Private lab traffic and collection

The endpoint subnet has a Service Gateway route to Oracle services only. The
endpoint VMs remain private but their Oracle Cloud Agent can receive an
operator-approved Run Command; the stack explicitly enables its `Compute
Instance Run Command` plugin. This is required for post-deployment test
configuration and is not a public-internet route.

Log Analytics content is provisioned in the selected stack compartment. The
collector no longer defaults new custom sources and log groups to the tenancy
root; retain tenancy-root placement only as an explicit compatibility choice
for an existing shared deployment.

On first boot, each endpoint starts a local Python application listener and a
bounded TCP/HTTP generator every 15 seconds. The web endpoint calls the
database listener on its allowed path; the database endpoint calls the web
listener on port 8080, a path intentionally lacking a ZPR allow rule. Treat successful or
failed application attempts as application evidence. Correlate a later VCN
Flow Log `ACCEPT`/`REJECT` record with the policy and endpoint attributes
before classifying the result; a flow-log rejection alone does not establish a
provider-confirmed ZPR denial.

Cloud-init user data is first-boot configuration. Updating Terraform metadata
does not rerun it on existing endpoint instances. The stack hashes each
endpoint bootstrap script and plans replacement when listener or traffic
configuration changes. Review those endpoint replacements in the exact plan;
do not treat a changed plan input as proof that the traffic scenario is active.

After a cold start, Oracle Cloud Agent can take several minutes to report the
Run Command plugin. A private endpoint without a Service Gateway route cannot
be managed through that channel. An empty short-window Logging search is a
collection-latency or coverage condition until log enablement, query scope,
and a later time window are verified.

### Historical troubleshooting receipt (superseded below)

On the OCI4CCA lab, the stack-owned Flow Log produced policy-correlated
allow/reject evidence after the endpoint traffic services started. The first
controller Run Command refresh attempt exited `127` before collector execution;
retrying with an absolute shell path still returned `127`. Treat this as an
unresolved Instance Agent command-dispatch failure, not a successful collector
refresh. Check the command content contract and controller agent configuration
before using Run Command as the bootstrap-recovery mechanism.

The endpoint Run Command plugins remained unavailable after a private Service
Gateway route and explicit plugin enablement. Do not use that condition as
evidence that the traffic service did not start, and do not substitute an
unauthorized SSH path. Treat endpoint service status and the dedicated denied
port as unverified until the agent bootstrap/network path is repaired or an
approved private-access method is supplied.

### Bootstrap repair receipt — October 1, 2026

Controller Run Command delivery is now provider-verified (`ACKED` and output)
after the owning policy added compartment-scoped
`use instance-agent-command-execution-family` with an instance-self condition.
The first diagnostic confirmed cloud-init failed; a command's nonzero exit is
not the same as a channel-delivery failure. Text output truncates long traces,
so query a bounded error summary and resume the same command when a short poll
ends before a terminal state.

The actual initial provisioning failure was `upsert_field` HTTP 400 with
`error_code=LIMIT_EXCEEDED`: the tenancy exhausted single-valued STRING fields.
No shared fields were deleted. The updated parser maps JSON
`collection_operation` to native `Operation`, `error_category` to native
`Category`, and creates `occurrence_count` as LONG. Collection-gap dashboard
queries use those same native names. Existing JSON records remain readable;
this does not change the record schema.

Further local repairs pass the dashboard compartment explicitly, place signer
initialization inside package-download retries, and retain assets under
`/opt/zpr-visibility/package`. The validator accepts `--compartment-id` and
uses subtree queries for every widget and the current-run gate.

These source repairs alone do not establish current ingestion, scheduled
refresh, or fresh indexed allow/reject evidence. Verify the deployed controller,
then the selected-compartment log group and all 43 current widget queries.

For the separate baked-dependency image pipeline and open launch/publisher
gates, see [Compute image delivery](marketplace-image.md).

### Content recovery and controller upgrade — October 1, 2026

A fresh guest diagnostic confirmed the installed package still lacked native
field aliases, the bootstrap log ended at the STRING quota error, and neither
the initial-refresh marker nor refresh timer existed. Missing sources/parsers/
groups were consequences of that first failure: `ensure_fields` precedes every
later provisioning step. Resource Manager apply success did not rerun cloud-init.

The operator ran the corrected provisioning scripts under a fresh target-bound
action receipt. Read-back verified one ZPR source, one parser, one deployment
log group, and seven dashboards. All 40 widget queries parsed before import.
This is content-creation evidence, not yet scheduled-refresh or indexing proof.

The collector archive now normalizes entry order, ownership, modes, timestamps,
and gzip metadata, and fixes the archive file mtime because the OCI provider
includes it in source diffs. Identical source builds yield identical bytes.
An explicit SHA-256 revision tracks both collector bytes and the bootstrap
template, so real upgrades still upload/rebootstrap. Terraform's
controller lifecycle replaces the stateless controller when its package object
changes; metadata-only updates must not silently leave old guest code running.
Review the complete saved plan and obtain destructive approval for replacement.
Leave endpoint instances, state bucket, and shared content intact. No local
Terraform apply may compete with Resource Manager ownership.

During recovery, an older local OCI SDK rejected the Management Dashboard
subtree keyword. Explicit selection of a compatible Python/SDK interpreter
resolved the local contract error; no additional IAM grants were needed.

The operator's initial refresh completed successfully: 34 inventory/coverage
records, five findings, two drift records, 1,000 observed enriched flows, and
one run heartbeat (1,042 records accepted for upload), with seven metrics
published. A subsequent exact `stats count` query confirmed all 1,042 records
indexed. All 40 widget queries executed: 39 returned data, one explicitly
allowed zero, and none errored. Use a two-hour validation window for this
acceptance run because the collected flow events already cover an earlier
hour; a later sliding one-hour window legitimately excludes some older events.
The freshness validator now uses an exact count aggregate rather than an
estimated/capped record-list total.

Observed flow counts were 218 ACCEPT and 782 REJECT. Correlation classified
174 expected accepts, 44 unexpected accepts, 78 expected blocks, and 704 needing
enrichment. These are review classifications, not provider-confirmed ZPR
verdicts. Collection also emitted one deduplicated gap record, so this is not
full-resource-family or gap-free acceptance.

An earlier October 1, 2026 plan failed its Resource Principal precondition and
was not applied. A later plan for an earlier uploaded artifact proposed five
adds, five changes, and four destroys; it remains historical and is not approval
for this source tree or ZIP. Upload the current artifact and create/review a
fresh plan before any apply. The live controller's timer/readiness state is
unverified; historical Log Analytics indexing is not current-run evidence.
