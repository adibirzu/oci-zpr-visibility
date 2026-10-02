# Resource Manager lifecycle review — October 2, 2026

## Current verdict

**October 2, 2026 local gate:** 188 tests pass, pure-core coverage is 87.82%,
all three Terraform roots format and validate, Actionlint is clean, and the
release archive parity check passes. The regenerated offline Marketplace
payload also passes its SHA-256 manifest and CycloneDX JSON checks. The current
`orm-stack.zip` SHA-256 is
`1fd839256b177c566566d167b71762f197488c9caede5735354eef67d584c47e`.

**Resource Manager source update is provider-verified:** this exact archive was
uploaded to the existing active `ZIP_UPLOAD` stack in the selected deployment
compartment, preserving its six variables. A fresh plan for this source
succeeded with **7 adds, 5 updates, and 4 destroys**. It is not applied. The
exact plan includes replacement of the controller VM, its subnet, and the
package object; deletion of the old internet gateway and creation of a NAT
gateway; and updates to the route table, dynamic group, IAM policy, state
bucket, and ZPR policy resource metadata. The web/database instances are
`no-op`, and their user-data is unchanged. The ZPR policy statements are
unchanged. The IAM change narrows several grants from tenancy to compartment,
but still grants `manage loganalytics-features-family` in tenancy; review that
scope before apply. Starting the two endpoint instances was separately
requested and is provider-verified; they are now `RUNNING`. The controller is
still `STOPPED` because this plan would replace it.

**Current Log Analytics inventory is provider-verified:** the deployment
compartment contains the ZPR JSON source, its parser, seven ZPR dashboards, and
98 fields mapped to that source. A scoped last-24-hour query returned 42 records
across seven record types: one collection gap, 25 coverage records, five
findings, two policy-drift records, two policy statements, six resources, and
one run. It returned no `zpr_enriched_flow` records. Thus existing content and
historical collection data are present, but current traffic-to-Log-Analytics
and dashboard HIT status are not yet proven. The direct Logging Search query
returned `NotAuthorizedOrNotFound`; until its permission/resource scope is
disambiguated, it is not evidence that Flow Logs are absent.

The earlier October 1 plan (5 adds, 5 changes, 4 destroys) is superseded by the
fresh plan above. No apply or destroy has run. Applying the current plan remains
gated on review and current approval tied to its exact action set. No image
build, private image launch, vulnerability scan, publisher review, or Oracle
Marketplace acceptance is claimed.

## Findings and fixes

1. **P1 — RM Resource Principal was unavailable to `data.external`.** The
   October 1 plan ran the `python3` external program and found OCI CLI, but the
   helper's `oci --auth resource_principal` probe returned unavailable. The
   Terraform precondition failed after the plan calculated 5 adds, 5 changes,
   4 destroys. Fix: remove the external provider and all Terraform job-side
   `local-exec` lifecycle hooks. Readiness and cleanup now use the private
   lifecycle output from an explicitly authenticated operator CLI profile;
   see `docs/self-contained-resource-manager.md`.
2. **P1 — stack success cannot prove application readiness.** No RM job-side
   authenticated guest polling is claimed. The controller's supervised
   bootstrap status is checked with scoped OCI Run Command after apply; it
   validates current-run indexing and dashboard query execution.
3. **P1 — safe destruction requires content cleanup before infrastructure.**
   The operator lifecycle path checks bucket/controller/attribute ownership,
   requests guest cleanup, verifies the receipt, deletes only known state
   objects and retires the exact lab attribute before the RM destroy job.
   Foreign content/shared fields and unknown bucket objects block cleanup.
4. **P2 — the current saved plan contains disruptive replacement and IAM changes.**
   The controller and controller subnet are replaced, the old internet gateway
   is deleted, and the package object is replaced. The endpoint instances are
   `no-op` because their first-boot user-data matches the existing instances.
   Review the full saved plan, cost/availability impact, and the remaining
   tenancy-scoped Log Analytics grant before any apply. Do not reuse approval
   for the historical October 1 plan.
5. **P2 — Marketplace image readiness is separate.** The image bundle/Packer
   source is code-backed only. No image build, sanitation/vulnerability scan,
   private launch acceptance, publisher review or Oracle Marketplace
   acceptance is claimed.

## Evidence

- 172 application tests passed; deterministic-core coverage was 86.19%.
- All three Terraform roots passed formatting and validation after the RM
  lifecycle correction.
- `scripts/check_release_artifacts.py` passes on the current local reproducible
  ZIP, and that exact ZIP is now provider-uploaded and planned.
- The current source-matched RM plan succeeded with 7 adds, 5 updates and 4
  destroys, and remains unapplied pending exact-plan approval.
- Provider reads confirm ZPR Log Analytics source/parser/dashboard inventory
  and recent records, but no recent flow records, current controller refresh,
  endpoint application response, dashboard query HIT, or scheduled refresh.

## Release acceptance still required

1. Obtain current approval for the latest successful plan after reviewing its
   complete action JSON, replacements, IAM/network changes and cost effects.
2. Apply only that exact saved plan, then run the operator lifecycle readiness
   check. Verify fresh records, dashboard queries, timer schedule, restart
   recovery and both allowed/blocked lab traffic.
3. Test idempotent upgrade/redeploy. With separate current approval, run the
   ownership-checked cleanup and exact-plan destroy; verify preservation of
   pre-existing/shared LA content and foundation singleton services.
4. Independently build/sanitize/scan the Marketplace image, verify IMDSv2 and
   first-boot SSH regeneration, test launch/refresh/restart, then complete
   publisher and Oracle review. Local release readiness is not listing
   acceptance.
