#!/usr/bin/env python3
"""Provision OCI Log Analytics content for ZPR visibility.

Idempotently creates:
  * custom fields (display name == the bare token used in dashboard queries)
  * a JSON parser mapping each record JSON key to its field
  * a source named "OCI ZPR Visibility JSON" (matches the dashboard 'Log Source')
  * a Log Analytics log group (target for ingestion / Connector Hub)

Usage:
  .venv/bin/python scripts/provision_la.py --profile <PROFILE> --region <REGION> \
      --log-group-name zpr-visibility-la

With --upload <file.jsonl>, also ingests records into LA via the Upload API
under the source (the fast path used for end-to-end validation; Connector Hub
is the continuous production path).

OCI Log Analytics modeling notes (verified in a live tenant):
  * upsert_field with no `name` CREATES and auto-generates an internal name
    (udfsNN). Passing `name` means UPDATE and fails with "Field not found".
  * Reuse an existing field (system or custom) by case-insensitive display name
    before creating a new one (LA display names are case-insensitive-unique).
  * Queries reference a custom field by its display name, not the udfs name.
  * A JSON parser REQUIRES is_single_line_content=False WITH header_content="$:0"
    plus language/encoding/is_default; single_line=True returns HTTP 500.
    Field maps set structured_column_info="$.<jsonKey>" and point `field` at the
    LA field by internal name.
  * The source uses type_name="os_file"; find an existing source by display name
    before upserting (OCI sets the source iname to the display name).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import oci

from .oci_clients import build_session, client

SOURCE_DISPLAY_NAME = "OCI ZPR Visibility JSON"
SOURCE_NAME = "oci_zpr_visibility_json"
PARSER_DISPLAY_NAME = "OCI ZPR Visibility JSON Parser"
PARSER_NAME = "oci_zpr_visibility_json_parser"
_QUIET = False


def _say(message: str = "") -> None:
    if not _QUIET:
        print(message)

# JSON key -> display name (display name is what dashboard queries reference).
# Display name is kept identical to the JSON key so queries use bare tokens.
FIELD_TOKENS = [
    "schema_version", "run_id", "event_time", "inventory_snapshot_time",
    "record_type", "policy_id", "policy_name", "policy_lifecycle_state",
    "statement", "statement_hash", "statement_index", "action", "source_attribute",
    "destination_attribute", "network_scope", "target_type", "parser_confidence",
    "resource_id", "resource_name", "resource_type", "compartment_id", "region",
    "vcn_id", "subnet_id", "vnic_id", "private_ip", "security_attributes",
    "severity", "finding_type", "cidr", "recommendation", "attribute_reference",
    "classification", "source_ip", "destination_ip", "destination_port",
    "review_classification", "evidence_source", "zpr_attribution",
    "correlation_confidence", "correlation_reason", "matched_policy_id",
    "matched_policy_name", "has_unmodeled_policy_filters",
    "source_type", "destination_type", "source_cidrs", "destination_cidrs",
    "source_ips", "destination_ips",
    "source_port", "protocol", "flow_id", "bytes_out", "packets",
    "capture_status", "capture_start_time", "capture_end_time",
    "source_resource_id", "source_resource_name",
    "destination_resource_id", "destination_resource_name",
    "source_security_attributes", "destination_security_attributes",
    "zpr_destination", "matched_expected_policy",
    # zpr_policy_drift records (statement_hash change across runs)
    "change_type", "old_statement", "new_statement", "old_hash", "new_hash",
    # zpr_run / zpr_coverage / zpr_collection_gap records
    "collection_status", "flow_collection_status", "record_count",
    "finding_count", "drift_count", "flow_count", "collection_error_count",
    "coverage_status", "eligible_count", "protected_count",
    "collection_service", "collection_operation", "error_category", "occurrence_count",
]

SAMPLE_CONTENT = (
    '{"record_type":"zpr_finding","event_time":"2026-06-03T10:00:00Z",'
    '"severity":"CRITICAL","finding_type":"broad_cidr_exception",'
    '"policy_name":"web-db","cidr":"0.0.0.0/0"}'
)


def _client(auth: str, config_file: str | None, profile: str, region: str):
    """Build (session, LA client, namespace) supporting api_key / instance / resource principal."""
    session = build_session(auth, config_file, profile, region)
    la = client(session, "log_analytics.LogAnalyticsClient")
    ns = client(session, "object_storage.ObjectStorageClient").get_namespace().data
    return session, la, ns


def ensure_fields(la, ns) -> dict[str, str]:
    """Return {token: internal_name} for every token.

    Reuse any existing field whose display name matches case-insensitively
    (LA display names are case-insensitive-unique, so a token like "action"
    collides with the system field "Action"); create the rest as custom.
    Dashboard queries resolve field references case-insensitively, so reusing
    the system field is correct.
    """
    m = oci.log_analytics.models
    by_lower = {
        f.display_name.lower(): f.name
        for f in oci.pagination.list_call_get_all_results(
            la.list_fields, namespace_name=ns, limit=2000
        ).data
    }
    mapping: dict[str, str] = {}
    created_n = reused_n = 0
    for token in FIELD_TOKENS:
        key = token.lower()
        if key in by_lower:
            mapping[token] = by_lower[key]
            reused_n += 1
            continue
        details = m.UpsertLogAnalyticsFieldDetails(
            display_name=token, data_type="STRING",
            description=f"OCI ZPR visibility field: {token}",
        )
        created = la.upsert_field(namespace_name=ns, upsert_log_analytics_field_details=details).data
        mapping[token] = created.name
        by_lower[key] = created.name
        created_n += 1
        _say(f"  field created: {token} -> {created.name}")
    _say(f"fields ready: {len(mapping)} (created {created_n}, reused {reused_n})")
    return mapping


def ensure_parser(la, ns, field_map: dict[str, str]) -> str:
    m = oci.log_analytics.models
    maps = []
    seq = 1
    # timestamp: event_time -> system Time field for inventory, flow, drift,
    # health, and coverage records alike.
    maps.append(
        m.LogAnalyticsParserField(
            field=m.LogAnalyticsField(name="time"),
            parser_field_name="time", storage_field_name="time",
            parser_field_sequence=seq, structured_column_info="$.event_time",
        )
    )
    seq += 1
    for token, internal in field_map.items():
        maps.append(
            m.LogAnalyticsParserField(
                field=m.LogAnalyticsField(name=internal),
                parser_field_name=internal, storage_field_name=internal,
                parser_field_sequence=seq, structured_column_info=f"$.{token}",
            )
        )
        seq += 1
    # JSON parser config that OCI LA accepts: is_single_line_content=False WITH
    # header_content="$:0" (single_line=True returns HTTP 500). language/encoding/
    # is_default are required for a clean upsert. Field maps reference the field by
    # internal name only.
    details = m.UpsertLogAnalyticsParserDetails(
        name=PARSER_NAME, display_name=PARSER_DISPLAY_NAME,
        description="Parses OCI ZPR visibility JSON records.",
        type="JSON", language="en_US", encoding="UTF-8", is_default=True,
        is_single_line_content=False, is_system=False, header_content="$:0",
        content=SAMPLE_CONTENT, example_content=SAMPLE_CONTENT,
        field_maps=maps,
    )
    etag = None
    try:
        etag = la.get_parser(namespace_name=ns, parser_name=PARSER_NAME).headers.get("etag")
    except oci.exceptions.ServiceError:
        pass
    kwargs = {"if_match": etag} if etag else {}
    la.upsert_parser(namespace_name=ns, upsert_log_analytics_parser_details=details, **kwargs)
    _say(f"parser ready: {PARSER_NAME} ({len(maps)} field maps)")
    return PARSER_NAME


def _find_source(la, ns, tenancy_id):
    """Return an existing source matching our display/internal name, else None."""
    page = None
    while True:
        kwargs = {"limit": 1000, "is_system": "ALL"}
        if page:
            kwargs["page"] = page
        resp = la.list_sources(namespace_name=ns, compartment_id=tenancy_id, **kwargs)
        for src in resp.data.items:
            if src.name in (SOURCE_NAME, SOURCE_DISPLAY_NAME) or src.display_name == SOURCE_DISPLAY_NAME:
                return src
        page = resp.headers.get("opc-next-page")
        if not page:
            return None


def ensure_source(la, ns, tenancy_id, parser_name: str) -> str:
    m = oci.log_analytics.models
    existing = _find_source(la, ns, tenancy_id)
    internal_name = existing.name if existing else SOURCE_NAME
    display_name = existing.display_name if existing else SOURCE_DISPLAY_NAME
    details = m.UpsertLogAnalyticsSourceDetails(
        name=internal_name, display_name=display_name,
        description="OCI ZPR policy, resource, finding, and enriched flow records.",
        type_name="os_file", is_for_cloud=False, is_system=False,
        parsers=[m.LogAnalyticsParser(name=parser_name, display_name=PARSER_DISPLAY_NAME,
                                      type="JSON", is_default=True)],
        entity_types=[m.LogAnalyticsSourceEntityType(
            entity_type="oci_generic_resource")],
    )
    etag = None
    if existing:
        try:
            etag = la.get_source(namespace_name=ns, source_name=internal_name,
                                 compartment_id=tenancy_id).headers.get("etag")
        except oci.exceptions.ServiceError:
            pass
    kwargs = {"if_match": etag} if etag else {}
    la.upsert_source(namespace_name=ns, upsert_log_analytics_source_details=details, **kwargs)
    _say(f"source {'updated' if existing else 'ready'}: {display_name}")
    return display_name


def ensure_log_group(la, ns, tenancy_id, name: str) -> str:
    m = oci.log_analytics.models
    for lg in oci.pagination.list_call_get_all_results(
        la.list_log_analytics_log_groups, namespace_name=ns,
        compartment_id=tenancy_id, limit=200
    ).data:
        if lg.display_name == name:
            _say(f"log group exists: {name}")
            return lg.id
    created = la.create_log_analytics_log_group(
        namespace_name=ns,
        create_log_analytics_log_group_details=m.CreateLogAnalyticsLogGroupDetails(
            compartment_id=tenancy_id, display_name=name,
            description="ZPR visibility ingestion target",
        ),
    ).data
    _say(f"log group created: {name}")
    return created.id


def upload_records(la, ns, log_group_id: str, records_path: str) -> int:
    """Ingest a JSONL records file into LA via the Upload API under the source."""
    import io
    body = io.BytesIO(Path(records_path).read_bytes())
    name = Path(records_path).name
    resp = la.upload_log_file(
        namespace_name=ns,
        upload_name=f"zpr-visibility-{name}",
        log_source_name=SOURCE_DISPLAY_NAME,
        filename=name,
        opc_meta_loggrpid=log_group_id,
        upload_log_file_body=body,
        content_type="application/octet-stream",
        char_encoding="UTF-8",
    )
    _say(f"uploaded sanitized evidence -> status {resp.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    global _QUIET
    p = argparse.ArgumentParser()
    p.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    p.add_argument("--config-file", default=None)
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", default=None)
    p.add_argument("--log-group-name", default="zpr-visibility-la")
    p.add_argument("--upload", help="JSONL records file to ingest into LA after provisioning")
    p.add_argument("--quiet", action="store_true", help="suppress identifiers and provisioning details")
    args = p.parse_args(argv)
    _QUIET = args.quiet

    session, la, ns = _client(args.auth, args.config_file, args.profile, args.region)
    tenancy_id = session.tenancy_id
    _say("Log Analytics namespace resolved")
    field_map = ensure_fields(la, ns)
    lg_id = ensure_log_group(la, ns, tenancy_id, args.log_group_name)
    parser_name = ensure_parser(la, ns, field_map)
    source_name = ensure_source(la, ns, tenancy_id, parser_name)

    _say("\nProvisioned:")
    _say(f"  fields     = {len(field_map)} ready")
    _say("  log_group  = ready")
    _say("  parser     = ready")
    _say("  source     = ready")

    if args.upload:
        _say()
        upload_records(la, ns, lg_id, args.upload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
