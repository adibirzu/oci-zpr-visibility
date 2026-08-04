# Dashboard Screenshots

The "OCI ZPR Visibility" Management Dashboard suite (see
[the README](../README.md#what-the-dashboard-shows)) is built and imported by
`oci-zpr-visibility deploy-dashboard`. Capture screenshots from the OCI Console
(Log Analytics → Dashboards → OCI ZPR Visibility) after a data refresh (W1 in
`.planning/workflows.md`) and add them here:

- `executive-posture.png` — KPI tiles + findings sunburst
- `allow-block-traffic.png` — ACCEPT/REJECT bar + src→dst flow link
- `drift-governance.png` — policy drift + missing-policy findings

(Screenshots are not committed if they reveal real tenancy data; redact OCIDs/IPs.)
