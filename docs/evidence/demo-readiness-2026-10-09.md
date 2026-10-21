# ZPR demo readiness — 2026-10-09

Provider observations: all nine monitored Compute instances RUNNING; both Autonomous Databases AVAILABLE. OKE pool and its two nodes ACTIVE; Kubernetes Ready is not verified.

Latest manual snapshot: 18:42:08 UTC. 581 indexed records, 34 inventory records, 509 real flow observations (125 ACCEPT, 384 REJECT), zero collection gaps. Validation is scoped to the exact Log Analytics group and checks the exact run/count. Eight enhanced dashboards contain 49 widgets: 44 DATA, five ZERO_ALLOWED, no errors or unavailable results.

Data changes: omitted inappropriate native table host columns; exposed policy list fields; populated VM VNIC placement, OKE node-pool VCN and ADB subnet-derived VCN; enforced coverage-aware family validation. Private screenshot cells are DOM masks, not synthesized source values.

Local gates: 182 tests passed; core coverage 86.04%; Terraform format and validate passed. Bootstrap dependencies are pinned with wheel hashes, and the archive digest is checked before extraction. Collector wheel installation performs no dependency resolution. Bootstrap still needs signed OS repositories and hashed PyPI downloads; this is not offline bootstrap or constrained egress.

Provider saved PLAN succeeded: six add, three change, four destroy. Replacements: controller, web VM, db VM and package object. Existing service gateway and endpoint routes are retained. No APPLY performed. Independent security/release review remains a hold; review capacity/isolation is not established. HTTP, SQL, Kubernetes Ready, instance-principal execution and scheduled refresh acceptance remain unverified. Existing-VCN mode is locally validated, not live end-to-end accepted.

Eight owned dashboards were updated in place. Export-compatible backups and replacement/recovery payloads are prepared; delete/recreate has not run. Exact destructive preview approval is required by the OCI skill. Foreign dashboards and legacy root dashboards are excluded. Replacements change dashboard URLs; partial failures are not atomic and require receipt inspection.

## Approved replacement completed

The user supplied the exact preview token. All eight owned dashboards were deleted and recreated; provider readback verifies 49 stored queries match and all eight old dashboard IDs return 404. Three imports succeeded before the saved-search quota blocked the fourth; the remaining five reused their existing searches. No unrelated resources were deleted or quota increase requested.

Compute placement now resolves VCN from the actual VNIC subnet. New collection at 19:17 UTC: 646 records, 574 real flows (127 ACCEPT, 447 REJECT), 34 inventory rows, zero collection gaps. All nine VM inventory rows have VCN, subnet and private IP. Latest widget validation is rerun separately. The ORM package/plan is regenerated to include this fix; no apply is authorized or performed.

User now allows private IPs and shortened OCIDs in screenshots. Public IPs and FQDNs remain hidden. This does not authorize publication.

Final follow-up checks: 49 widgets pass (44 DATA, five ZERO_ALLOWED), exact latest run contains all 646 indexed records. Latest package-bound provider PLAN SUCCEEDED at 19:20:15 UTC: six add, three change, four destroy. No apply performed. 182 local tests pass. Refreshed native images display private IPs and shortened OCIDs under the user's authorization.
