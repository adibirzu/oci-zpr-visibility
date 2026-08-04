# Workflows — archived pointer

The command sequences that used to live here were copies of the operator
documentation and kept drifting from the CLI. They are owned elsewhere now; do
not re-add copies here.

| Workflow | Owner |
|----------|-------|
| Onboard a tenancy (`enable-zpr` → `provision-la` → first `refresh`) and schedule continuous collection | [docs/discovery.md](../docs/discovery.md) |
| Live e2e refresh, log-collection checks, and the `validate-dashboards` gate | [docs/runbook.md](../docs/runbook.md) |
| Dashboard build + import (`deploy-dashboard`) | [docs/runbook.md](../docs/runbook.md) — "Deploy the dashboard" |
| Release gate (tests, coverage threshold, `terraform fmt`/`validate`) | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) |
| Current live acceptance status | [docs/validation.md](../docs/validation.md) |
