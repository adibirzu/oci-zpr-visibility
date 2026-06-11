# One-Click Deployment — Oracle Resource Manager

The `orm/` stack provisions the entire ZPR visibility lab **and** its Log
Analytics content + dashboard in one apply. Build the zip, upload it as a
Resource Manager stack, and apply.

## What the stack creates

| Module (file) | Resources |
|---------------|-----------|
| `network.tf` | VCN (ZPR-tagged `oracle-zpr.app=fin-network`), public + private subnets, IGW, route table, security list, subnet VCN Flow Logs |
| `zpr.tf` | `app` security attribute in the `oracle-zpr` namespace + a ZPR policy (web→db allow; broad-CIDR exception) |
| `compute.tf` | 2 ZPR-tagged endpoints — `web` (app=web) and `db` (app=db) — generating intra-VCN traffic (web→db allowed; db→web denied by ZPR) |
| `storage.tf` | drift-state bucket + a bucket holding the collector package |
| `controller.tf` | controller VM + a dynamic group (matching just that instance) + least-privilege IAM policy; cloud-init installs the collector and runs `provision-la` + `deploy-dashboard` + `refresh` via **instance principal** |
| `functions.tf` | optional OCI Functions application + function resource + resource-principal IAM for `deployment_mode = "function"` |

In `controller_vm` mode, after apply the controller (no API keys) builds the LA
custom source + 40 fields + JSON parser, imports the 29-widget dashboard,
ingests inventory + findings + drift, publishes Monitoring metrics, and
installs a 15-minute refresh cron with VCN Flow Log correlation — so the
dashboard is **live with real data, no manual step**. In `function` mode, the
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
