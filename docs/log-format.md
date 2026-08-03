# Log Format — OCI ZPR Visibility JSON

The tool ingests **one JSON object per line** (JSONL) into the OCI Log Analytics
custom source **`OCI ZPR Visibility JSON`** via the Upload API. A custom JSON
parser maps each key to a Log Analytics field; the system **Time** field is taken
from `event_time` for every record type.

## How to view it

In **Log Analytics → Log Explorer**, run:

```
'Log Source' = 'OCI ZPR Visibility JSON' | timestats count as logrecords by 'Log Source' | sort -logrecords
```

Expand any row → **Original Log Content** shows the raw JSON; the field table
below it shows the parsed fields. See
`evidence/screenshots/03_log_explorer.png`.

## Record discriminator: `record_type`

Every record carries a `record_type`. There are eight, each a different lens on
ZPR. Common envelope fields are `schema_version`, opaque `run_id`, `record_type`,
`event_time` (→ **Time**), and `inventory_snapshot_time`. The run ID contains no
tenant, resource, or topology information and binds live validation to the exact
collector run that produced the evidence.

### 1. `zpr_policy_statement` — one row per parsed policy statement
| Field | Meaning |
|-------|---------|
| `policy_id`, `policy_name`, `policy_lifecycle_state` | the ZPR policy |
| `statement` | the natural-language statement, e.g. `in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints` |
| `statement_hash` | stable hash used for drift detection |
| `source_attribute`, `destination_attribute` | parsed security-attribute endpoints |
| `source_type`, `destination_type` | `attribute`, `cidr`, `ip`, `all_endpoints`, or `unknown` |
| `source_cidrs`, `destination_cidrs`, `source_ips`, `destination_ips` | parsed address endpoints used by correlation |
| `network_scope`, `target_type` | VCN scope and compatibility target type |
| `action`, `parser_confidence` | `allow`; parser confidence 0–1 |

### 2. `zpr_resource` — one row per protected (security-attributed) resource
| Field | Meaning |
|-------|---------|
| `resource_id`, `resource_name`, `resource_type` | the VCN / instance |
| `compartment_id`, `region`, `vcn_id`, `subnet_id`, `vnic_id`, `private_ip` | placement |
| `security_attributes` | e.g. `oracle-zpr.app=web` (enforce) |

### 3. `zpr_finding` — posture findings
| Field | Meaning |
|-------|---------|
| `severity` | CRITICAL / HIGH / MEDIUM / LOW |
| `finding_type` | `broad_cidr_exception`, `protected_resource_no_matching_policy`, `policy_references_unknown_attribute`, … |
| `policy_name`, `cidr`, `attribute_reference` | context |
| `resource_name`, `resource_type`, `security_attributes` | affected resource |
| `recommendation` | remediation guidance |

### 4. `zpr_enriched_flow` — VCN Flow Log correlated to ZPR intent
| Field | Meaning |
|-------|---------|
| `action` | `ACCEPT` / `REJECT` from the VCN Flow Log; not a dedicated ZPR verdict |
| `classification` | backwards-compatible internal correlation class |
| `review_classification` | customer-facing, evidence-safe triage class |
| `correlation_confidence`, `correlation_reason` | how strongly the inventory/policy model supports the inference |
| `zpr_attribution` | always `INFERRED_NOT_PROVIDER_VERDICT` for VCN Flow Log correlation |
| `source_ip`, `source_port`, `destination_ip`, `destination_port`, `protocol` | the flow tuple |
| `flow_id`, `bytes_out`, `packets`, `capture_status` | retained VCN Flow Log evidence |
| `source_resource_name`/`_id`, `destination_resource_name`/`_id` | resolved endpoints |
| `source_security_attributes`, `destination_security_attributes` | endpoint attributes |
| `zpr_destination` | destination is a ZPR-protected resource |
| `matched_expected_policy` | flow matches an intended policy relationship |

**`review_classification` values:**
- `policy_consistent_accept` — flow-log action is ACCEPT and the modeled policy relationship matches.
- `accepted_requires_policy_review` — ACCEPT to a protected destination without a complete modeled match.
- `rejected_protected_destination` — REJECT to a protected destination without a complete modeled match.
- `rejected_policy_expected_allow` — REJECT where the modeled relationship appears to allow.
- `needs_enrichment` — endpoint attributes or identity are incomplete.

These values are review queues, not proof that ZPR allowed or denied a packet.

### 5. `zpr_policy_drift` — policy statements changed across runs
| Field | Meaning |
|-------|---------|
| `change_type` | `ADDED`, `REMOVED`, or `MODIFIED` |
| `old_statement`, `new_statement` | before and after evidence |
| `old_hash`, `new_hash` | previous and current canonical hashes |

### 6. `zpr_coverage` — supported-resource collection coverage

One row per current OCI ZPR-supported resource type. `COLLECTED` means this
collector inspected that type; `NOT_COLLECTED` is an explicit product coverage
gap, never a claim that the tenant has zero resources of that type.

### 7. `zpr_collection_gap` — read/collection failures

Sanitized service, operation, resource type, and exception category. Messages,
OCIDs, names, and topology are intentionally excluded.

### 8. `zpr_run` — freshness and pipeline health

Carries collection/flow status and record, finding, drift, flow, and error
counts for one opaque run ID. A visible run record proves that exact run reached
Log Analytics inside the selected time window.

## Example record (a finding)

```json
{"attribute_reference":"app:web","finding_type":"policy_references_unknown_attribute",
 "policy_id":"<OCID>","policy_name":"zpr-visibility-demo",
 "recommendation":"Validate that the referenced security attribute namespace/key still exists and is spelled correctly.",
 "record_type":"zpr_finding","severity":"MEDIUM","event_time":"2026-06-05T10:45:02Z",
 "statement":"in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints"}
```
