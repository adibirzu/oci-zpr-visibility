# Resource Manager lifecycle review — October 1, 2026

## Current verdict

The source now removes the failed Resource Manager job-side authentication
assumption and provides a private operator readiness/cleanup path. Local
validation is green. On October 1, 2026, ZIP SHA-256
`27bbf67600b763c7fe90444274fc7fb7f4bb9105f3de63ab0439097714eb5039` was
uploaded to the active named stack and its Resource Manager plan succeeded.
That historical plan has 5 adds, 5 changes and 4 destroys,
including replacement of the controller instance, its subnet, and package
object; IGW removal and NAT creation; collector revision creation; and
in-place updates to the route table, dynamic group, IAM policy, state bucket,
and ZPR policy. The endpoint instances are not planned for replacement. The
plan has not been applied; the exact action set still needs current approval.
No destroy was run. The current local/GitHub ZIP is SHA-256
`a31aa75119f0230855ea4f56d0baacce4c6b29df8a145d96f8d78f58c317dafd` and is not
the uploaded artifact. The historical plan does not cover this newer ZIP;
upload it and create/review a fresh plan before any apply.

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
4. **P2 — controller and subnet replacement remain a fresh-plan review item.**
   The latest plan proposes IGW removal/NAT creation, IAM/storage updates and
   ZPR policy normalization. It does not propose endpoint instance replacement.
   These changes are not approved by the historical plan token; obtain approval
   tied to the latest exact plan before applying.
5. **P2 — Marketplace image readiness is separate.** The image bundle/Packer
   source is code-backed only. No image build, sanitation/vulnerability scan,
   private launch acceptance, publisher review or Oracle Marketplace
   acceptance is claimed.

## Evidence

- 172 application tests passed; deterministic-core coverage was 86.19%.
- All three Terraform roots passed formatting and validation after the RM
  lifecycle correction.
- `scripts/check_release_artifacts.py` passes on the current local reproducible
  ZIP. At this review, the uploaded stack source is the historical ZIP above;
  the newer local package needs a new upload and plan.
- An earlier RM plan was provider-verified for the explicit precondition error
  and made no infrastructure changes. The latest source-matched plan
  succeeded with 5 adds, 5 changes and 4 destroys, but remains unapplied.
- Historical LA indexing/query evidence from a prior deployment is not proof
  that the current stack package is bootstrapped or producing fresh records.

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
