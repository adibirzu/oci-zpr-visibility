# Existing estate observation and live lab verification

Goal: choose an existing VCN in ORM, observe explicitly selected compartments,
and show Compute, OKE and Autonomous Database lifecycle/placement alongside
actual flow evidence without changing network enforcement on existing assets.

## Acceptance

- Default lab deployments keep their current behavior; existing-network mode
  creates no demo endpoints, VCN, routes, security lists or demo ZPR policy.
- Existing controller subnet must belong to selected VCN; private operation
  requires owner-provided OCI/API and bootstrap egress.
- Explicit collection scopes reach controller and Function refresh invocations.
- OKE/ADB resource inventory is distinct from verified security attributes and
  real VCN flow observations. Missing permissions produce collection gaps.
- Dashboard views use latest lifecycle observations per resource and expose
  source, collection scope, freshness and missing evidence.
- Focused tests, full Python suite, coverage gate, Terraform validation and
  sanitized package inspection pass locally before any new live deployment.

## Boundaries and rollback

Local source changes are reversible. Starting verified existing lab VMs is the
only requested cloud mutation for this increment. ORM source update, IAM changes,
new flow logs, enforcement attributes, traffic generators on third-party assets,
and saved-plan apply require exact target/impact review. A lifecycle state alone
cannot establish real traffic, query success or authenticated dashboard acceptance.

## Tasks

1. Inspect live owned lab resources and start eligible stopped endpoints/controller.
2. Extend read-only OKE/ADB inventory and conservative error/protection evidence.
3. Add ORM existing-network mode and explicit scope/flow inputs.
4. Integrate scope plumbing, native estate views and local review artifact.
5. Run local gates and independent advisory correctness review; retain live
   acceptance/strict security review holds explicitly when unavailable.
