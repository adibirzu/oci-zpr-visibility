# oci-zpr-visibility agent guide
This Python package discovers OCI ZPR state, correlates VCN Flow Logs, and supports Log Analytics reporting and Terraform deployments.

## Commands
- Install: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` (README).
- Test: `make test` (`python -m unittest discover -s tests`); CI also runs `pytest tests/ -q`.
- Lint: no lint command is defined in the Makefile, pyproject.toml, or CI workflows.
- Run the local demo: `python -m oci_zpr_visibility.cli demo --output-dir out/demo`.

## Layout
- `oci_zpr_visibility/` -> Python package and CLI.
- `tests/` -> unittest and pytest tests.
- `scripts/` -> artifact builds, validation, provisioning, and dashboard helpers.
- `terraform/`, `terraform/zpr-demo/` -> standalone Terraform deployments.
- `orm/` -> Oracle Resource Manager stack and controller templates.
- `image/`, `deploy/` -> image build and Kubernetes deployment assets.
- `log_analytics/`, `examples/` -> dashboard/source definitions and sample inputs.
- `docs/` -> architecture, operator, deployment, and validation documentation.

## Boundaries
- Use an explicitly selected OCI profile and region for CLI operations; replace documented placeholders with the authorized target values.
- `terraform/terraform.tfvars`, Terraform state, raw screenshots, and local evidence logs are ignored; keep secrets, real OCIDs, and IPs out of commits.
- `orm-stack.zip` is intentionally tracked and rebuilt by `bash scripts/build_orm_zip.sh`.
- ZPR is tenancy-level; the Resource Manager stack assumes ZPR is already active.

## On error
Search KB.md (and ~/dev/OCI-DEMO/KB.md for OCI issues) before debugging; add an entry after a new fix. Do not read KB.md at session start.

## Done
- Run `make test` to verify a change.

<!-- BEGIN oci4cca-ecosystem-matrix -->
Shared OCI4CCA ownership/interconnect contract: [docs/OCI4CCA_ECOSYSTEM.md](docs/OCI4CCA_ECOSYSTEM.md), generated from OCI-DEMO `config/oci4cca_ecosystem.json`. Read it only for cross-project work.
<!-- END oci4cca-ecosystem-matrix -->
