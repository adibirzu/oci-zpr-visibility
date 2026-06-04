# Workflows

Repeatable command sequences for this project. Each is runnable today (or after
the noted task lands). Keep the live gate (`validate-dashboards`) green.

## W1 — Live e2e refresh (cap)
Collect real ZPR data, ingest to LA, confirm dashboards.
```bash
.venv/bin/oci-zpr-visibility collect --profile cap --region eu-frankfurt-1 --skip-resources \
  --snapshot out/cap/zpr_snapshot.json --records out/cap/zpr_records.jsonl
.venv/bin/oci-zpr-visibility trigger --out out/cap/trigger_records.jsonl
cat out/cap/zpr_records.jsonl out/cap/trigger_records.jsonl > out/cap/all_records.jsonl
.venv/bin/oci-zpr-visibility provision-la --profile cap --region eu-frankfurt-1 --upload out/cap/all_records.jsonl
.venv/bin/oci-zpr-visibility validate-dashboards --profile cap --region eu-frankfurt-1   # expect all HIT
```

## W2 — Release gate (pre-push)
```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest tests/ -q --cov=oci_zpr_visibility.jsonutil \
  --cov=oci_zpr_visibility.security_attributes --cov=oci_zpr_visibility.policy_parser \
  --cov=oci_zpr_visibility.correlate --cov=oci_zpr_visibility.findings   # >=80%
terraform -chdir=terraform fmt -check && terraform -chdir=terraform validate
git push   # ECC pre-push hook re-runs pytest; GitHub CI runs both jobs
```

## W3 — Seed a fresh tenancy (bootstrap)
```bash
.venv/bin/oci-zpr-visibility enable-zpr --profile <P> --region <R>
.venv/bin/oci-zpr-visibility seed       --profile <P> --region <R>     # app attr + ZPR policy
terraform -chdir=terraform apply                                        # logging layer
.venv/bin/oci-zpr-visibility provision-la --profile <P> --region <R>   # LA fields/parser/source/log group
# then W1 to populate + validate
```

## W4 — Dashboard deploy (after deploy-dashboard task lands)
```bash
.venv/bin/oci-zpr-visibility deploy-dashboard --profile <P> --region <R> --dry-run
.venv/bin/oci-zpr-visibility deploy-dashboard --profile <P> --region <R>
.venv/bin/oci-zpr-visibility validate-dashboards --profile <P> --region <R>
```

## CI workflow (already live)
`.github/workflows/ci.yml` — Python tests + coverage gate + terraform fmt/validate on push/PR.
