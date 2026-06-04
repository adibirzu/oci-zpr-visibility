# OCI ZPR Visibility — Service Relationships

How the OCI services and project components relate. Complements
[architecture.md](architecture.md) (data flow) and
[api-cli-reference.md](api-cli-reference.md) (operations).

## Service dependency graph

```
                         ┌─────────────────────────┐
                         │   oci-zpr-visibility     │  (Python collector + scripts)
                         │   collector / provisioner│
                         └────────────┬─────────────┘
            read ┌────────────────────┼───────────────────────┐ write
                 ▼                    ▼                         ▼
   ┌──────────────────┐   ┌────────────────────┐   ┌────────────────────────┐
   │ Zero Trust Packet│   │ Security Attributes │   │ Resource Search + Core │
   │ Routing (ZPR)    │   │ (namespaces, attrs) │   │ (instances, VNIC, IP)  │
   │ config + policies│   │                     │   │                        │
   └──────────────────┘   └────────────────────┘   └────────────────────────┘
                 │ correlate (IP↔resource, attr↔policy)
                 ▼
        ┌────────────────────┐         ┌────────────────────────────┐
        │ normalized records │────────▶│ OCI Logging (custom log)   │  via emit (put_logs)
        │ (4 record types)   │         │ zpr-inventory              │
        └─────────┬──────────┘         └────────────────────────────┘
                  │ Upload API (upload_log_file)
                  ▼
        ┌──────────────────────────────────────────────────────────┐
        │ OCI Log Analytics                                          │
        │  • fields + JSON parser + source (OCI ZPR Visibility JSON) │
        │  • log group (zpr-visibility-la)                           │
        │  • dashboard (5 tabs / 14 widgets)                         │
        └──────────────────────────────────────────────────────────┘
                  ▲
                  │ Connector Hub (built-in source)
        ┌────────────────────────────┐
        │ OCI VCN Flow Logs (service)│  ACCEPT/REJECT network decisions
        └────────────────────────────┘
```

## Relationship table

| From | To | Relationship | Mechanism |
|------|----|--------------|-----------|
| Collector | ZPR | reads config + policies | `ZprClient` (SDK) |
| Collector | Security Attributes | reads namespaces + attributes | `SecurityAttributeClient` |
| Collector | Resource Search + Core | finds attributed resources, enriches VNIC/IP | `ResourceSearchClient`, `ComputeClient`, `VirtualNetworkClient` |
| Collector | correlation engine | joins flows↔resources↔policies | local (`correlate.py`, `findings.py`) |
| Collector | OCI Logging | emits records to custom log | `LoggingClient.put_logs` |
| Provisioner | Log Analytics | creates fields/parser/source/log group, uploads records | `LogAnalyticsClient` |
| VCN Flow Logs | OCI Logging | service logs | Logging service |
| OCI Logging (flow) | Log Analytics | forwards flow logs | Connector Hub (built-in source) |
| OCI Logging (inventory) | Log Analytics | **not used** — inventory ingests via Upload API | (see architecture note) |
| Dashboards | Log Analytics | query the custom source | LA query API |

## Why ZPR needs explicit correlation

VCN Flow Logs record ACCEPT/REJECT with src/dst address, protocol, VNIC/subnet/
compartment OCIDs — but **no ZPR deny-reason field**. So attribution to ZPR
policy intent is computed by the collector: map flow IPs → resources (via VNIC/
private IP), resources → security attributes, and attributes → matching policy
statements. The result is the `zpr_enriched_flow` classification
(`expected_accepted`, `unexpected_accepted`, `expected_blocked`,
`suspected_misconfiguration`, `needs_enrichment`).

## Identity boundaries

- Collector principal: read on ZPR, Security Attributes, Resource Search, Core;
  write (`use log-content`) on the custom log; LA content management for the
  provisioner. See [runbook.md](runbook.md) for least-privilege statements.
- All work is scoped to the configured profile/compartment; pre-flight tenancy
  checks are mandatory before any mutation (see global tenancy rules).
