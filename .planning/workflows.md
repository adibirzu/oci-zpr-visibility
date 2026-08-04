# Workflows

Repeatable command sequences for this project. Each is runnable today (or after
the noted task lands). Keep the live gate (`validate-dashboards`) green.

## W1 — Live e2e refresh (staging tenancy)
Collect real ZPR data, ingest to LA, confirm dashboards.
```bash
.venv/bin/oci-zpr-visibility collect --profile <PROFILE> --region <REGION> --skip-resources \
  --snapshot out/zpr_snapshot.json --records out/zpr_records.jsonl
.venv/bin/oci-zpr-visibility trigger --out out/trigger_records.jsonl
cat out/zpr_records.jsonl out/trigger_records.jsonl > out/all_records.jsonl
.venv/bin/oci-zpr-visibility provision-la --profile <PROFILE> --region <REGION> --upload out/all_records.jsonl
.venv/bin/oci-zpr-visibility validate-dashboards --profile <PROFILE> --region <REGION> \
  --expected-run-id <RUN_ID_REPORTED_BY_COLLECT> --expected-record-count <UPLOADED_COUNT>   # expect 0 ZERO, 0 ERROR
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
