# OCI ZPR Visibility — Roadmap

Roadmap for the independent ZPR visibility accelerator: a validated collector,
native Log Analytics dashboards, self-contained Resource Manager appliance,
and a future read-only operator console.

Status legend: ✅ done · 🔜 next · 📋 planned · 💡 idea

## Where we are (baseline)

- ✅ Collector CLI (`enable-zpr`, `collect`, `findings`, `correlate`, `emit`, `demo`)
- ✅ Policy parser, flow correlation, finding generation (unit-tested)
- ✅ Terraform: ZPR config, Logging log group + custom log, Connector Hub (flow path)
- ✅ Log Analytics content provisioner (fields, JSON parser, source, log group)
- ✅ Operational scripts: `seed_demo.py`, `trigger_rules.py`, `provision_la.py`, `validate_dashboards.py`
- ✅ Dashboard query catalog, parser, and current-run validation gates
- ✅ Docs: architecture, runbook, validation, API/CLI reference, services map
- ✅ Public GitHub repository; candidate delivery remains branch/PR-reviewed
- ◑ Resource Manager package, operator-owned readiness/cleanup, and Marketplace
  image payload are locally validated; the latest provider plan is unapplied
- 📋 Marketplace image build/launch, publisher review, and Oracle acceptance
  remain outstanding

## Phase 1 — Hardening & DX (◑ in progress)

- ✅ **Dashboard enhancement** — seven focused native OCI LA dashboards with 43 widgets, flow trends, endpoint/protocol analysis, policy-drift history, conservative Flow Log evidence labels, collection health, and explicit resource-coverage gaps.

Goal: production-quality reliability and contributor onboarding.

1. ✅ **CLI consolidation** — `provision_la.py`, `validate_dashboards.py`,
   `seed_demo.py`, `trigger_rules.py` moved into the package and exposed as
   `oci-zpr-visibility provision-la | validate-dashboards | seed | trigger`;
   `scripts/*.py` are now thin shims. Subcommand routing is TDD-tested and the
   live e2e is bound to an opaque current run ID instead of historical rows.
2. ✅ **`--version` flag** (`oci-zpr-visibility --version`). 🔜 `--json` global flag + structured logging (replace `print`).
3. **CI**: GitHub Actions running `pytest` + `terraform validate` on push/PR. ✅ (this phase)
4. ✅ **Coverage gate** — pure-logic core ≥ 80% (86.19% on October 1, 2026), enforced in CI.
5. **Typed config** — frozen dataclass for run config; validate at startup.
6. **Retry/backoff policy** centralised for OCI calls; explicit timeouts.

## Phase 2 — Continuous operation (◑ in progress)

Goal: hands-off, scheduled detection refresh.

1. ◑ **Scheduled collector** — the Resource Manager controller uses a
   supervised 15-minute systemd timer and instance principal; provider
   ingestion/timer/restart acceptance is pending.
2. ✅ **State & drift** — persist snapshots and emit added, removed, and modified statement evidence; advance state only after successful upload.
3. **Idempotent re-provision** in the schedule (fields/parser/source are upserts).
4. **Alerting** — OCI Monitoring alarms on `zpr_finding` severity and
   evidence-safe flow-review classifications;
   route to Notifications (email/Slack/PagerDuty).
5. ✅ **Run health** — emit `zpr_run`, `zpr_coverage`, and sanitized `zpr_collection_gap` records; dashboard views + alarms on missing heartbeat/errors.

## Phase 3 — Coverage & correctness (◑ in progress)

1. ◑ **Real VCN Flow Logs path** — `correlate --flow-log-group-id` consumes real
   VCN Flow Logs from OCI Logging (code path done, unit-tested); enabling live
   traffic needs a VCN with ZPR-protected instances (`flow_log_targets`).
2. **Resource enrichment** — extend beyond compute instances (load balancers,
   DB systems, OKE) for `zpr_resource` coverage.
3. ◑ **Policy parser hardening** — structured documented syntax, namespace
   qualifiers, cross-VCN scopes, and regression cases are implemented; expand
   the grammar corpus as OCI syntax evolves.
4. **Finding catalogue** — expand detections (overly-permissive scopes, stale
   attribute references, cross-VCN exposure) with severities and remediations.

## Phase 4 — Multi-tenancy & scale (💡 idea)

1. **Profile/compartment matrix** — run across tenant-neutral configured profiles with
   per-profile config overlays (mirror the detections project's pattern).
2. **Central observability tenancy** — aggregate inventory from many tenancies
   into one Log Analytics namespace.
3. **Throughput** — batch upload, parallel resource search, pagination tuning.

## Phase 5 — Product surface (📋 planned)

1. **Dashboard design and data contract** — documented current pipeline,
   evidence limits, peer-product research, and next-version view proposal in
   [docs/dashboards-and-data-guide.md](docs/dashboards-and-data-guide.md).
2. **Tabbed read-only console** — private web surface with Overview, Topology,
   Traffic, Policies, Coverage, Findings, and Collection Health tabs; shared
   region/compartment/resource/time filters; linked charts, tables, and finding
   evidence drilldowns. Keep the native Log Analytics dashboards supported.
3. **Topology and investigation links** — show policy-intent and observed-flow
   edges as distinct layers; preserve source/destination VCN scopes; link to OCI
   ZPR Visualizer and Network Path Analyzer instead of claiming to replace them.
4. **Read API and query catalog** — versioned, scope-authorized read endpoints;
   one server-side query catalog shared by both dashboard surfaces; no arbitrary
   client-provided queries and no policy-mutation endpoints.
5. **Truthful states and accessibility** — explicit empty, stale, partial,
   permission-denied, and query-failure states; keyboard-operable tabs and
   drilldowns; render only metrics supported by collected OCI evidence.
6. **Export** — Sigma/Sentinel-style export of ZPR findings for cross-tool reuse.

Patterns researched from OCI ZPR Visualizer, OCI Network Path Analyzer, Google
Cloud Flow Analyzer, Azure Traffic Analytics, and AWS Network Firewall
monitoring are mapped to this project's scope and evidence in the dashboard
guide. These are product design references, not claims of feature parity.

## Current release gates (October 2, 2026)

- Latest `orm-stack.zip` SHA-256:
  `02eb0961100b976b89cb37c500ae53601598467a6fd1c955c7e1b0625f5c160e`.
- The active Resource Manager stack's last uploaded ZIP was
  `27bbf67600b763c7fe90444274fc7fb7f4bb9105f3de63ab0439097714eb5039`; its
  plan succeeded with 5 adds, 5 changes and 4 destroys, but is unapplied. The
  current local/GitHub ZIP differs and has not been uploaded or planned. Upload
  this exact artifact and create/review a fresh plan before any apply; see
  `docs/resource-manager-lifecycle-review.md`.
- Marketplace payload builds reproducibly, checksums/SBOM pass, and Packer
  template validation passes. No OCI image has been built or launched and no
  Marketplace listing has been submitted.
- Local unit/coverage, Terraform, artifact-parity and image-payload checks do
  not prove current Log Analytics data or application readiness.

## Cross-cutting

- **Security**: no secrets/OCIDs/IPs in repo (placeholder convention); least-privilege IAM; rotate keys.
- **Testing**: unit (offline) + integration (approved OCI target) + e2e (`validate_dashboards.py`); keep the live gate green.
- **Docs**: keep architecture/API-CLI/services/runbook in sync with code; update on every behavioural change.
