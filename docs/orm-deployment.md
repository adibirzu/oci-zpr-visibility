# One-Click Deployment — Oracle Resource Manager

The `orm/` stack provisions the entire ZPR visibility lab **and** its Log
Analytics content + dashboard in one apply. Build the zip, upload it as a
Resource Manager stack, and apply.

Use `network_mode = existing` for observation in an owner supplied VCN. In this
mode the stack references the VCN, controller subnet, and selected flow log,
creates no endpoint instances, flow-log resources, routes, security lists, VCN
security attributes, or ZPR policies, and does not modify the existing network.
`observation_compartment_ocid` identifies the compartment containing the supplied
Logging group/log and defaults to the deployment compartment. The subnet is
checked by OCI data lookup and a Terraform postcondition that its VCN matches
`existing_vcn_ocid`.

Flow-log IDs are optional together: omit both for inventory-only observation, or
provide both to enable traffic correlation. `collection_compartment_ocids`
selects the exact inventory compartments independently of the flow-log location.
The existing-mode controller is private by default; lab mode retains its public
controller default. IAM inventory reads are scoped to the selected compartments;
flow-log reads are granted separately in the observation compartment. ZPR policy
and security-attribute discovery still require tenancy-level read permissions.
These generated policies need plan review and runtime validation before they
can be described as provider-verified. An explicit empty collection list or
blank compartment entry is rejected.

## What the stack creates

| Module (file) | Resources |
|---------------|-----------|
| `network.tf` | VCN (ZPR-tagged `oracle-zpr.app=fin-network`), public + private subnets, IGW, route table, security list, subnet VCN Flow Logs |
| `zpr.tf` | `app` security attribute in the `oracle-zpr` namespace + a ZPR policy (web→db allow; broad-CIDR exception) |
| `compute.tf` | 2 ZPR-tagged endpoints — `web` (app=web) and `db` (app=db) — generating intra-VCN traffic (web→db allowed; db→web denied by ZPR) |
| `storage.tf` | drift-state bucket + a bucket holding the collector package |
| `controller.tf` | controller VM + a dynamic group (matching just that instance) + least-privilege IAM policy; cloud-init installs the collector and runs `provision-la` + `deploy-dashboard` + `refresh` via **instance principal** |
| `functions.tf` | optional OCI Functions application + function resource + resource-principal IAM for `deployment_mode = "function"` |

In existing mode, provide `existing_vcn_ocid`, `existing_controller_subnet_ocid`,
`existing_flow_log_group_ocid`, and `existing_flow_log_ocid`. Existing flow logs
are passed through as read targets and are not reconfigured.

In `controller_vm` mode, after apply the controller (no API keys) builds the LA
custom source + fields + JSON parser, imports the dashboard suite,
ingests inventory + findings + drift, publishes Monitoring metrics, and
installs a 15-minute refresh cron with VCN Flow Log correlation — so the
dashboard is **live with real data, no manual step**. In `function` mode, the
stack creates the Functions application, state bucket,
flow logs, and optional function resource; invoke it through your scheduler.

## Build the stack zip

```bash
scripts/build_orm_zip.sh        # -> orm-stack.zip (terraform + package tarball + schema.yaml)
scripts/build_orm_zip.sh /tmp/orm-stack.zip  # disposable output path
```

The builder needs Python 3.11 and setuptools 68 or newer. It produces a collector
wheel, included in the package archive; the controller installs that wheel with
dependency resolution disabled. Terraform embeds the archive SHA-256 in
cloud-init and rejects a mismatched download before extraction. Bootstrap SDK
dependencies are version-pinned with wheel hashes in
`orm/bootstrap-requirements.txt` for Python 3.11 on x86_64 Linux. The guest still
needs access to signed Oracle Linux package repositories, PyPI wheel downloads,
and the required OCI APIs. This is not a fully offline or constrained-egress
deployment. Review changes to that lock file before building a release.

## Deploy via Resource Manager (Console)

1. **Developer Services → Resource Manager → Stacks → Create stack**.
2. Source: **.zip file** → upload `orm-stack.zip` (Terraform is at the zip root; `schema.yaml` drives the variable form).
3. Fill the form: Compartment, Region, Availability Domain, Oracle Linux 9 image
   (E3.Flex), optional SSH key, Network ownership, and Autonomy mode. For
   `existing`, fill the existing VCN/subnet/flow-log IDs and optional observation
   compartment.
   - `controller_vm` is the default: creates the controller VM and built-in
     15-minute cron.
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
cd orm && terraform destroy \
  -var config_file_profile=<oci-profile> -var tenancy_ocid=<...> -var compartment_ocid=<...> \
  -var region=<...> -var availability_domain=<...> -var instance_image_ocid=<...>
```
The endpoint instances are billable while running. In `controller_vm` mode, the
controller instance is billable too; in `function` mode, the Function is
pay-per-use and has no built-in cron. LA content + dashboard created by the
controller persist (they're not Terraform-managed); remove them with the OCI
console or the SDK if desired.

## Idempotency / re-deploy

`terraform apply` is idempotent; the controller's `provision-la`/`deploy-dashboard`
are upserts and `refresh` is safe to repeat. The collector package object is
re-uploaded from the zip on each apply.

### Existing-network rollout boundary

Create a **separate observer stack** with a unique `name_prefix` (for example
`zpr-estate-observer`). Do not change an established lab stack to existing mode:
its owned lab resources would become removal candidates. The moved blocks
preserve singleton addresses when upgrading the default lab configuration;
only a reviewed stateful saved plan proves migration safety for a real stack.

Flow-log references are optional as a pair. When supplied, both Terraform and
refresh validate that the enabled service flow log observes the selected VCN,
or a subnet/VNIC in that VCN. A mismatch fails validation before correlation.
Exact `collection_compartment_ocids` reach both controller and Function refresh;
these scopes describe inventory and may include resources in other VCNs. Only
traffic from the explicitly selected flow log is correlated in this increment.

The form uses documented Resource Manager string controls for existing Logging
OCIDs and a typed list for collection scopes; it does not promise a Logging
resource picker. This was checked against Oracle's
[schema documentation](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager_topic-schema.htm).

New collector fields must be provisioned and fresh records ingested before
importing/accepting the expanded native dashboard suite. Source changes and
local Terraform validation do not prove guest bootstrap or dashboard freshness.

Function IAM matches the exact Terraform-managed function OCID. Leaving
`function_image` empty creates no Function dynamic group or policy; manually
created functions require separately reviewed principal grants.

## Upgrade acceptance

Existing lab upgrades retain endpoint Service Gateway routes and use moved
addresses when lab-only resources gain a count. Listener/traffic bootstrap
changes can replace the endpoints; controller bootstrap changes can replace the
controller. Read the exact saved ORM plan before apply. The deployment keeps
IMDSv1 disabled and Run Command configured, but a configured plug-in is not
guest readiness. The enhanced package is locally validated; the current live
upgrade has not been applied. See [estate visibility](estate-visibility.md) for
explicit Log Analytics destination and scheduled-run acceptance checks.
