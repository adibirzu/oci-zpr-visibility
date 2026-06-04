# OCI ZPR Visibility — Roadmap

Long-term plan to evolve the project from a validated CLI + Terraform + Log
Analytics pipeline into a fully operated, multi-tenancy detection product.

Status legend: ✅ done · 🔜 next · 📋 planned · 💡 idea

## Where we are (baseline)

- ✅ Collector CLI (`enable-zpr`, `collect`, `findings`, `correlate`, `emit`, `demo`)
- ✅ Policy parser, flow correlation, finding generation (unit-tested)
- ✅ Terraform: ZPR config, Logging log group + custom log, Connector Hub (flow path)
- ✅ Log Analytics content provisioner (fields, JSON parser, source, log group)
- ✅ Operational scripts: `seed_cap.py`, `trigger_rules.py`, `provision_la.py`, `validate_dashboards.py`
- ✅ End-to-end validated in cap: 14/14 dashboard widgets HIT
- ✅ Docs: architecture, runbook, validation, API/CLI reference, services map
- ✅ Private GitHub repo + pre-push pytest gate

## Phase 1 — Hardening & DX (🔜 next)

- ✅ **Dashboard enhancement** — native OCI LA dashboard: 21 widgets (KPI tiles, severity sunburst, flow link), color semantics, drill-downs, and `deploy-dashboard` one-command import. Live 21/21 HIT.

Goal: production-quality reliability and contributor onboarding.

1. ✅ **CLI consolidation** — `provision_la.py`, `validate_dashboards.py`,
   `seed_cap.py`, `trigger_rules.py` moved into the package and exposed as
   `oci-zpr-visibility provision-la | validate-dashboards | seed | trigger`;
   `scripts/*.py` are now thin shims. Subcommand routing is TDD-tested and the
   live e2e (14/14) was re-confirmed through the new subcommand.
2. ✅ **`--version` flag** (`oci-zpr-visibility --version`). 🔜 `--json` global flag + structured logging (replace `print`).
3. **CI**: GitHub Actions running `pytest` + `terraform validate` on push/PR. ✅ (this phase)
4. ✅ **Coverage gate** — pure-logic core ≥ 80% (now 90%), enforced in CI.
5. **Typed config** — frozen dataclass for run config; validate at startup.
6. **Retry/backoff policy** centralised for OCI calls; explicit timeouts.

## Phase 2 — Continuous operation (📋 planned)

Goal: hands-off, scheduled detection refresh.

1. **Scheduled collector** — OCI Functions or OKE CronJob running
   `collect` + LA `--upload` every 15 min (live) / daily (audit), using
   instance/resource principals (no API keys).
2. **State & drift** — persist snapshots (Object Storage) so `statement_hash`
   drift detection works across runs without manual seeding.
3. **Idempotent re-provision** in the schedule (fields/parser/source are upserts).
4. **Alerting** — OCI Monitoring alarms on `zpr_finding` severity and
   `unexpected_accepted` / `suspected_misconfiguration` flow classifications;
   route to Notifications (email/Slack/PagerDuty).
5. **Run health** — emit a `zpr_run` heartbeat record; dashboard widget + alarm
   on missing heartbeat.

## Phase 3 — Coverage & correctness (📋 planned)

1. ◑ **Real VCN Flow Logs path** — `correlate --flow-log-group-id` consumes real
   VCN Flow Logs from OCI Logging (code path done, unit-tested); enabling live
   traffic needs a VCN with ZPR-protected instances (`flow_log_targets`).
2. **Resource enrichment** — extend beyond compute instances (load balancers,
   DB systems, OKE) for `zpr_resource` coverage.
3. **Policy parser hardening** — track ZPR grammar changes; raise
   `parser_confidence` coverage; add a grammar-regression corpus.
4. **Finding catalogue** — expand detections (overly-permissive scopes, stale
   attribute references, cross-VCN exposure) with severities and remediations.

## Phase 4 — Multi-tenancy & scale (💡 idea)

1. **Profile/compartment matrix** — run across DEFAULT/cap/emdemo with
   per-profile config overlays (mirror the detections project's pattern).
2. **Central observability tenancy** — aggregate inventory from many tenancies
   into one Log Analytics namespace.
3. **Throughput** — batch upload, parallel resource search, pagination tuning.

## Phase 5 — Product surface (💡 idea)

1. **Web dashboard** — read-only Next.js surface over the LA query API (reuse
   the `oci-log-analytics-detections` Forge webapp pattern), no query logic
   duplicated client-side.
2. **API** — thin read API exposing findings/posture for SIEM/SOAR integration.
3. **Export** — Sigma/Sentinel-style export of ZPR findings for cross-tool reuse.

## Cross-cutting

- **Security**: no secrets/OCIDs/IPs in repo (placeholder convention); least-privilege IAM; rotate keys.
- **Testing**: unit (offline) + integration (cap) + e2e (`validate_dashboards.py`); keep the live gate green.
- **Docs**: keep architecture/API-CLI/services/runbook in sync with code; update on every behavioural change.
