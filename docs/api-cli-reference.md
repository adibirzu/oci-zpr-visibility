# OCI ZPR Visibility — API & CLI Reference

Authoritative list of the OCI APIs/SDK operations, the `oci` CLI commands, and
the project's own CLI/scripts. Kept in sync with the code under
`oci_zpr_visibility/` and `scripts/`.

## 1. Application CLI (`oci-zpr-visibility`)

Console entry point `oci_zpr_visibility.cli:main`. Auth flags on cloud commands:
`--auth {api_key,instance_principal,resource_principal}`, `--config-file`,
`--profile`, `--region`.

| Command | Purpose | Cloud? | Key OCI calls |
|---------|---------|--------|---------------|
| `enable-zpr` | Enable ZPR in the tenancy root (supports `--dry-run`) | yes | `ZprClient.create_configuration` |
| `collect` | Collect ZPR inventory → snapshot + normalized records; optional `--emit-log-id` | yes | ZPR, Security Attributes, Resource Search, Core |
| `findings` | Generate findings from an existing snapshot | no | — (local) |
| `correlate` | Correlate JSONL VCN flow logs with a snapshot | no | — (local) |
| `emit` | Emit JSONL records to an OCI custom log | yes | `LoggingClient.put_logs` |
| `demo` | Run sample data through findings + correlation | no | — (local) |

### Consolidated operational subcommands

These live in the package (`oci_zpr_visibility/`) and are exposed both as CLI
subcommands and as thin `scripts/*.py` shims (legacy paths kept working).

| Subcommand | Shim | Purpose | Key OCI calls |
|------------|------|---------|---------------|
| `seed` | `scripts/seed_cap.py` | Create `app` security attribute + a real ZPR policy | `SecurityAttributeClient.create_security_attribute`, `ZprClient.create_zpr_policy` |
| `trigger` | `scripts/trigger_rules.py` | Generate flows exercising every detection classification | — (local) |
| `provision-la` | `scripts/provision_la.py` | Create LA fields/parser/source/log group; `--upload` ingests records | `LogAnalyticsClient.upsert_field/upsert_parser/upsert_source/create_log_analytics_log_group/upload_log_file` |
| `validate-dashboards` | `scripts/validate_dashboards.py` | Execute all dashboard queries; report HIT/MISS/ERROR | `LogAnalyticsClient.query` |

Subcommands route before argparse so flags pass through to each module's own
parser, e.g. `oci-zpr-visibility provision-la --profile cap --upload recs.jsonl`.

## 2. OCI SDK clients & operations used

Clients are built lazily in `oci_zpr_visibility/oci_clients.py` via
`client(session, "<module>.<Class>")`.

| Service | SDK client | Operations | Used by |
|---------|-----------|------------|---------|
| Zero Trust Packet Routing | `oci.zpr.ZprClient` | `create_configuration`, `get_configuration`, `list_zpr_policies`, `get_zpr_policy`, `create_zpr_policy` | collector, seed |
| Security Attributes | `oci.security_attribute.SecurityAttributeClient` | `list_security_attribute_namespaces`, `list_security_attributes`, `create_security_attribute` | collector, seed |
| Resource Search | `oci.resource_search.ResourceSearchClient` | `search_resources` (StructuredSearchDetails) | collector |
| Core — Compute | `oci.core.ComputeClient` | `list_vnic_attachments` | collector (VNIC enrichment) |
| Core — Network | `oci.core.VirtualNetworkClient` | `get_vnic`, `list_private_ips` | collector (IP enrichment) |
| Logging Ingestion | `oci.loggingingestion.LoggingClient` | `put_logs` (PutLogsDetails / LogEntryBatch) | `emit` |
| Log Analytics | `oci.log_analytics.LogAnalyticsClient` | `upsert_field`, `upsert_parser`, `upsert_source`, `get_parser`, `get_source`, `list_sources`, `create_log_analytics_log_group`, `list_log_analytics_log_groups`, `upload_log_file`, `query`, `parse_query` | `provision_la`, `validate_dashboards` |
| Object Storage | `oci.object_storage.ObjectStorageClient` | `get_namespace` (resolve LA namespace) | `provision_la`, `validate_dashboards` |

### Auth modes (`oci_clients.build_session`)

- `api_key` — `oci.config.from_file(profile_name=...)` + `validate_config`.
- `instance_principal` — `InstancePrincipalsSecurityTokenSigner`.
- `resource_principal` — `get_resource_principals_signer`.

## 3. `oci` CLI commands referenced (runbook / scripts)

| Command | Purpose |
|---------|---------|
| `oci iam tenancy get` | Pre-flight: confirm tenancy identity before any mutation |
| `oci os ns get` | Resolve the Object Storage / Log Analytics namespace |
| `oci logging-search search-logs` | Verify records landed in OCI Logging (GSL) |
| `oci log-analytics query parse` | Validate a Logan QL query's syntax + fields (no execution) |
| `oci log-analytics namespace list` | Confirm LA is onboarded |
| `oci log-analytics log-group list` | List LA log groups |

## 4. Terraform (provider `oracle/oci`)

| Resource | Purpose |
|----------|---------|
| `oci_zpr_configuration` | Enable ZPR in the root compartment (`prevent_destroy`) |
| `oci_logging_log_group` | Central Logging group for ZPR visibility |
| `oci_logging_log` (SERVICE) | VCN Flow Logs per `flow_log_targets` |
| `oci_logging_log` (CUSTOM) | `zpr-inventory` custom log for collector output |
| `oci_sch_service_connector` | Connector Hub: flow logs → LA (built-in source) |

Outputs: `logging_log_group_ocid`, `flow_log_ocids`,
`zpr_inventory_custom_log_ocid`, connector OCIDs.

> The ZPR **inventory** path ingests via the LA **Upload API** to the custom
> `OCI ZPR Visibility JSON` source, not Connector Hub — see
> [validation.md](validation.md) and [architecture.md](architecture.md).

## 5. Log Analytics content (provisioned)

- 40 custom fields (display name == dashboard query token; existing fields reused).
- JSON parser `oci_zpr_visibility_json_parser` (`is_single_line_content=False` +
  `header_content="$:0"`).
- Source `OCI ZPR Visibility JSON` (`type_name="os_file"`).
- Log group `zpr-visibility-la`.
- Dashboard catalog: `log_analytics/dashboards/oci_zpr_visibility_dashboard.json`
  (5 tabs / 14 widgets).
