# Log Format — OCI ZPR Visibility JSON

The tool ingests **one JSON object per line** (JSONL) into the OCI Log Analytics
custom source **`OCI ZPR Visibility JSON`** via the Upload API. A custom JSON
parser maps each key to a Log Analytics field; the system **Time** field is taken
from `snapshot_time`.

## How to view it

In **Log Analytics → Log Explorer**, run:

```
'Log Source' = 'OCI ZPR Visibility JSON' | timestats count as logrecords by 'Log Source' | sort -logrecords
```

Expand any row → **Original Log Content** shows the raw JSON; the field table
below it shows the parsed fields. See
`evidence/screenshots/03_log_explorer.png`.

## Record discriminator: `record_type`

Every record carries a `record_type`. There are five, each a different lens on
ZPR. Common envelope fields: `record_type`, `snapshot_time` (→ **Time**).

### 1. `zpr_policy_statement` — one row per parsed policy statement
| Field | Meaning |
|-------|---------|
| `policy_id`, `policy_name`, `policy_lifecycle_state` | the ZPR policy |
| `statement` | the natural-language statement, e.g. `in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints` |
| `statement_hash` | stable hash used for drift detection |
| `source_attribute`, `destination_attribute` | e.g. `app:web` → `app:db` |
| `network_scope`, `target_type` | VCN scope; `attribute` vs `cidr` target |
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
| `action` | `accept` / `reject` (the network decision) |
| `classification` | ZPR interpretation (see below) |
| `source_ip`, `destination_ip`, `destination_port`, `protocol` | the 5-tuple |
| `source_resource_name`/`_id`, `destination_resource_name`/`_id` | resolved endpoints |
| `source_security_attributes`, `destination_security_attributes` | endpoint attributes |
| `zpr_destination` | destination is a ZPR-protected resource |
| `matched_expected_policy` | flow matches an intended policy relationship |

**`classification` values:**
- `expected_accepted` — allowed and matches an intended policy. ✅
- `unexpected_accepted` — allowed but **not** matched by an expected relationship → over-permissive path. ⚠️
- `expected_blocked` — rejected and intended to be blocked. ✅
- `suspected_misconfiguration` — rejected to a protected destination policy seems meant to allow. ⚠️
- `needs_enrichment` — endpoint attributes/identity not fully resolved.

### 5. `zpr_policy_drift` — statement hash changed across runs
| Field | Meaning |
|-------|---------|
| `policy_id`, `statement` | which statement changed |
| `old_hash`, `new_hash` | previous vs current `statement_hash` |

## Example record (a finding)

```json
{"attribute_reference":"app:web","finding_type":"policy_references_unknown_attribute",
 "policy_id":"<OCID>","policy_name":"zpr-visibility-demo",
 "recommendation":"Validate that the referenced security attribute namespace/key still exists and is spelled correctly.",
 "record_type":"zpr_finding","severity":"MEDIUM","snapshot_time":"2026-06-05T10:45:02Z",
 "statement":"in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints"}
```
