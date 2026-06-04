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
| `controller.tf` | controller VM + a dynamic group (matching just that instance) + IAM policy; cloud-init installs the collector and runs `provision-la` + `deploy-dashboard` + `refresh` via **instance principal** |

After apply, the controller (no API keys) builds the LA custom source + 40
fields + JSON parser, imports the 21-widget dashboard, ingests inventory +
findings + drift, publishes Monitoring metrics, and installs a 15-minute refresh
cron — so the dashboard is **live with real data, no manual step**.

## Build the stack zip

```bash
scripts/build_orm_zip.sh        # -> orm-stack.zip (terraform + package tarball + schema.yaml)
```

## Deploy via Resource Manager (Console)

1. **Developer Services → Resource Manager → Stacks → Create stack**.
2. Source: **.zip file** → upload `orm-stack.zip` (Terraform is at the zip root; `schema.yaml` drives the variable form).
3. Fill the form: Compartment, Region, Availability Domain, Oracle Linux 9 image (E3.Flex), optional SSH key, and the "auto-provision" toggle.
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

The controller dynamic group is granted `manage all-resources in tenancy` for
the lab. For production, scope it to the least-privilege set documented in
`orm/controller.tf` (LA features, management dashboards, ZPR read, security
attributes read, virtual-network/instance read, object manage, metrics use).

## Teardown (stop billing)

```bash
cd orm && terraform destroy \
  -var config_file_profile=<oci-profile> -var tenancy_ocid=<...> -var compartment_ocid=<...> \
  -var region=<...> -var availability_domain=<...> -var instance_image_ocid=<...>
```
The 3 instances (web, db, controller) are billable while running. LA content +
dashboard created by the controller persist (they're not Terraform-managed);
remove them with the OCI console or the SDK if desired.

## Idempotency / re-deploy

`terraform apply` is idempotent; the controller's `provision-la`/`deploy-dashboard`
are upserts and `refresh` is safe to repeat. The collector package object is
re-uploaded from the zip on each apply.
