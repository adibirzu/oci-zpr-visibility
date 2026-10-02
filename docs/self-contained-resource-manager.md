# Resource Manager deployment and lifecycle

The uploaded stack is self-contained for infrastructure provisioning and guest
runtime. It does not invoke Codex, JD, an OCI skill pack, a workstation script,
GitHub checkout, or an external scheduler. The controller installs its locked
runtime, configures Log Analytics content with an instance principal, gates its
own refresh timer on successful current-run indexing, and records readiness in
`/var/lib/zpr-visibility/status.json`.

## Resource Manager boundary

The Resource Manager Terraform job creates OCI resources through the OCI
Terraform provider. It must not rely on the job process having OCI CLI Resource
Principal authentication. On October 1, 2026, a candidate plan found Python and
OCI CLI but reported Resource Principal unavailable to its external/local-exec
process. The plan failed closed after calculating five additions, five
changes, and four destroys; it was not applied. The external provider and
job-side hooks were removed. Readiness and cleanup now use a private sensitive
Terraform output and an explicitly authenticated operator CLI profile.

This distinction is intentional: an RM job succeeding proves Terraform
resource lifecycle, not guest bootstrap, Log Analytics indexing, dashboard
query execution, or scheduled refresh. Do not report a working deployment until
those checks pass.

## Deploy and verify

1. Build and validate the release candidate:

   ```bash
   bash scripts/build_orm_zip.sh
   python3.11 -m pytest -q -p no:cacheprovider
   terraform -chdir=orm fmt -check -recursive
   terraform -chdir=orm init -backend=false -input=false -lockfile=readonly
   terraform -chdir=orm validate
   ```

2. Upload the ZIP to Resource Manager, create a fresh plan, review all actions
   and replacement/cost effects, and approve that exact plan before applying.
3. Use the private `lifecycle_config` Terraform output to create a mode-0600
   local file. Prefer extracting from Resource Manager state; state and output
   contain identifiers and must not be committed or attached to tickets:

   ```bash
   lifecycle_tmp="$(mktemp -d)"
   chmod 700 "$lifecycle_tmp"
   trap 'rm -f "$lifecycle_tmp/state.json" "$lifecycle_tmp/lifecycle.json"; rmdir "$lifecycle_tmp"' EXIT
   oci --profile <PROFILE> resource-manager stack get-stack-tf-state \
     --stack-id <STACK_OCID> --file "$lifecycle_tmp/state.json"
   python3.11 scripts/extract_lifecycle_config.py \
     --state "$lifecycle_tmp/state.json" \
     --output "$lifecycle_tmp/lifecycle.json"
   ```

4. From an operator machine with OCI CLI and a named profile authorized for
   scoped Run Command/Object Storage/Log Analytics checks, run:

   ```bash
   python3.11 orm/rm_lifecycle.py wait \
     --config "$lifecycle_tmp/lifecycle.json" --auth config --profile <PROFILE>
   ```

   This verifies bucket/controller ownership and polls the controller status
   over OCI Run Command. Readiness requires a configured flow source, uploaded
   current-run records, indexing of the exact run, and successful execution of
   all dashboard queries. It reports only a summary.
5. Separately verify the 15-minute systemd timer and restart recovery through
   an approved private access channel. Stack `ACTIVE` or apply success alone is
   not application acceptance.

The state output and CLI results may contain tenant identifiers. Keep them
private. Do not check in state, plan files, lifecycle JSON, CLI receipts, or
Terraform variables.

## Upgrade and destroy

Keep `installation_id` stable for upgrades. Dashboard updates require the
ownership journal's exact IDs/tags. Shared/native fields and saved searches
referenced by foreign dashboards are preserved. When the operator cannot
prove a complete cross-compartment dashboard-reference scan, saved searches
are preserved rather than deleted; review the machine-readable cleanup result
before teardown. Same-name foreign content,
missing ownership, ambiguous inventory, and unknown state-bucket objects fail
closed. Legacy content is not adopted automatically.

Before destroying the stack, obtain the current sensitive `lifecycle_config`
from that stack's state and run:

```bash
python3.11 orm/rm_lifecycle.py destroy \
  --config <PRIVATE_LIFECYCLE_CONFIG> --auth config --profile <PROFILE>
```

This verifies exact bucket/controller/lab-attribute ownership, invokes guest
cleanup through Instance Agent, validates its cleanup receipt, deletes only
known state objects, and retires only the owned lab attribute. Unknown objects,
unowned content, permission errors, or stale ownership block cleanup. Export
evidence retained for audit first. Then create a fresh Resource Manager destroy
plan/job, review the full action set, and apply only with exact-plan approval.
Tenancy-wide ZPR enablement and Log Analytics onboarding are external singleton
foundation operations and are never removed by this stack.

This teardown requires an operator OCI CLI/profile by design; the Resource
Manager job itself has no supported authenticated lifecycle hook here. It is
skill-independent and does not require Codex or a separate automation service.

## Deployment scope and current status

The Terraform root provisions the isolated lab, not the default
existing-environment product mode. It manages the lab attribute and policy,
two endpoints with test listeners/traffic, flow logs, the private controller,
NAT, state/package buckets, and Log Analytics content. It does not enable
tenancy-wide ZPR or onboard the Log Analytics singleton. Log Analytics
namespace content-management IAM remains tenancy-scoped where the service
requires it; review this permission, retention and cost before deployment.

The active stack's last uploaded ZIP had SHA-256
`27bbf67600b763c7fe90444274fc7fb7f4bb9105f3de63ab0439097714eb5039`. Its
October 1, 2026 plan succeeded with five additions, five changes and four
destroys, including controller/subnet replacement, IGW removal/NAT creation,
and related IAM/storage/ZPR metadata changes. It remains unapplied. The current
local ZIP is `02eb0961100b976b89cb37c500ae53601598467a6fd1c955c7e1b0625f5c160e`;
it has not been uploaded or planned, so the earlier plan must not be applied to
it. Upload the exact current artifact and review a fresh plan first. Marketplace
image sanitation, launch testing, publisher eligibility and Oracle acceptance
are separate gates.
