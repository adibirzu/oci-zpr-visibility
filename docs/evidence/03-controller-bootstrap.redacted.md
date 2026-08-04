# Controller bootstrap — redacted outcome evidence

After `terraform apply` of orm/, the controller VM (instance principal, no API
keys) auto-ran provision-la + deploy-dashboard + refresh. Verified via live LA:

- Records ingested in the last 10 minutes: 3 record types (policy / finding /
  resource) — produced by the controller's `refresh` (no manual upload in >40m).
- Monitoring `zpr_visibility` heartbeat metric: 1 datapoint in the last 20m —
  published by the controller via instance principal.
- `terraform plan -destroy` is clean (full teardown available on demand).

Conclusion: one-click ORM apply creates the full lab + Log Analytics content +
dashboard + real data with no manual step and no errors.
