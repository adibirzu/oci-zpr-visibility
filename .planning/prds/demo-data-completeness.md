# Demo data, dashboard replacement, and ORM acceptance

User outcome: start monitored Compute servers, show applicable log fields with
real observations, replace owned dashboard content, and verify ORM delivery.

1. Data/view quality: audit each record family against parser mappings; show
   applicable policy, resource, flow, coverage and run fields first. Native
   Entity/host fields must not be invented for non-host policy events. Expose
   absent source data and unsupported families explicitly.
2. Collection/deployment: carry an explicit LA destination compartment and group
   through provision, scheduled refresh, controller bootstrap and validation.
   Successful upload, indexed rows, scheduled runs and guest/workload health are
   separate acceptance checks.
3. Live demo: freshly verify exact monitored instances before START; verify
   convergence and flow collection. Keep project ownership and network policy
   intact. Database starts retain the earlier explicit authorization.
4. Replacement: export exact project-owned dashboards and concurrency tokens,
   validate all new queries, preview exact deletes and rollback artifacts before
   obtaining the skill-required destructive approval token. Never delete foreign
   same-name resources or undiscovered saved searches.
5. ORM: package/validate locally, inspect exact existing stack and state, obtain
   a reviewed saved plan, and show any IAM, cost or replacement changes before
   apply. A package or plan is not end-to-end acceptance.

Local code edits and scoped Compute starts are authorized. No commit, push,
publishing or external messaging is authorized. Preserve existing dirty edits.
Shared-workspace agents are bounded local helpers; isolation is unproven and
no independent security/release acceptance is claimed. Dispatch ceiling: three
initial tasks, two repair attempts per task, two review cycles. Coordinator
performs cloud actions and inspects/reruns local changes.

Current handoff: 9 Compute RUNNING, 2 ADB AVAILABLE; latest 581 indexed records and 509 observed flows. Eight enhanced dashboards updated in place, 49 widget checks passed. Backed-up replacement awaits exact destructive token. ORM PLAN only; independent security/release review and runtime acceptance are holds. Bootstrap hashes added; broad egress and online bootstrap remain. Scope validation is executed in Terraform, including null defaults and invalid lists. No apply, commit or publication.
