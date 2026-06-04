#!/usr/bin/env python3
"""Provision OCI Log Analytics content for ZPR visibility.

Idempotently creates:
  * custom fields (display name == the bare token used in dashboard queries)
  * a JSON parser mapping each record JSON key to its field
  * a source named "OCI ZPR Visibility JSON" (matches the dashboard 'Log Source')
  * a Log Analytics log group (target for ingestion / Connector Hub)

Usage:
  .venv/bin/python scripts/provision_la.py --profile cap --region eu-frankfurt-1 \
      --log-group-name zpr-visibility-la

OCI Log Analytics modeling notes (reverse-engineered from built-in parsers):
  * upsert_field with no `name` CREATES and auto-generates an internal name
    (udfsNN). Passing `name` means UPDATE and fails with "Field not found".
  * Queries reference a custom field by its display name, not the udfs name.
  * A JSON parser field map sets structured_column_info = "$.<jsonKey>" and
    points `field` at the LA field by its internal name.
"""

from __future__ import annotations

import argparse
import sys

import oci

SOURCE_DISPLAY_NAME = "OCI ZPR Visibility JSON"
SOURCE_NAME = "oci_zpr_visibility_json"
PARSER_DISPLAY_NAME = "OCI ZPR Visibility JSON Parser"
PARSER_NAME = "oci_zpr_visibility_json_parser"

# JSON key -> display name (display name is what dashboard queries reference).
# Display name is kept identical to the JSON key so queries use bare tokens.
FIELD_TOKENS = [
    "record_type", "policy_id", "policy_name", "policy_lifecycle_state",
    "statement", "statement_hash", "action", "source_attribute",
    "destination_attribute", "network_scope", "target_type", "parser_confidence",
    "resource_id", "resource_name", "resource_type", "compartment_id", "region",
    "vcn_id", "subnet_id", "vnic_id", "private_ip", "security_attributes",
    "severity", "finding_type", "cidr", "recommendation", "attribute_reference",
    "classification", "source_ip", "destination_ip", "destination_port",
    "protocol", "source_resource_id", "source_resource_name",
    "destination_resource_id", "destination_resource_name",
    "source_security_attributes", "destination_security_attributes",
    "zpr_destination", "matched_expected_policy",
]

SAMPLE_CONTENT = (
    '{"record_type":"zpr_finding","snapshot_time":"2026-06-03T10:00:00Z",'
    '"severity":"CRITICAL","finding_type":"broad_cidr_exception",'
    '"policy_name":"web-db","cidr":"0.0.0.0/0"}'
)


def _client(profile: str, region: str):
    cfg = oci.config.from_file(profile_name=profile)
    cfg["region"] = region
    oci.config.validate_config(cfg)
    la = oci.log_analytics.LogAnalyticsClient(cfg)
    ns = oci.object_storage.ObjectStorageClient(cfg).get_namespace().data
    return la, ns, cfg


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
        print(f"  field created: {token} -> {created.name}")
    print(f"fields ready: {len(mapping)} (created {created_n}, reused {reused_n})")
    return mapping


def ensure_parser(la, ns, field_map: dict[str, str]) -> str:
    m = oci.log_analytics.models
    maps = []
    seq = 1
    # timestamp: snapshot_time -> system Time field
    maps.append(
        m.LogAnalyticsParserField(
            field=m.LogAnalyticsField(name="time"),
            parser_field_name="time", storage_field_name="time",
            parser_field_sequence=seq, structured_column_info="$.snapshot_time",
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
    details = m.UpsertLogAnalyticsParserDetails(
        name=PARSER_NAME, display_name=PARSER_DISPLAY_NAME,
        description="Parses OCI ZPR visibility JSON records.",
        type="JSON", is_single_line_content=True,
        content=SAMPLE_CONTENT, example_content=SAMPLE_CONTENT,
        field_maps=maps,
    )
    la.upsert_parser(namespace_name=ns, upsert_log_analytics_parser_details=details)
    print(f"parser ready: {PARSER_NAME} ({len(maps)} field maps)")
    return PARSER_NAME


def ensure_source(la, ns, parser_name: str) -> str:
    m = oci.log_analytics.models
    details = m.UpsertLogAnalyticsSourceDetails(
        name=SOURCE_NAME, display_name=SOURCE_DISPLAY_NAME,
        description="OCI ZPR policy, resource, finding, and enriched flow records.",
        type_name="LOG_FILE",
        parsers=[m.LogAnalyticsParser(name=parser_name, display_name=PARSER_DISPLAY_NAME, type="JSON")],
        entity_types=[],
    )
    la.upsert_source(namespace_name=ns, upsert_log_analytics_source_details=details, create_like_source_id=0)
    print(f"source ready: {SOURCE_DISPLAY_NAME}")
    return SOURCE_DISPLAY_NAME


def ensure_log_group(la, ns, cfg, name: str) -> str:
    m = oci.log_analytics.models
    for lg in oci.pagination.list_call_get_all_results(
        la.list_log_analytics_log_groups, namespace_name=ns,
        compartment_id=cfg["tenancy"], limit=200
    ).data:
        if lg.display_name == name:
            print(f"log group exists: {name} -> {lg.id}")
            return lg.id
    created = la.create_log_analytics_log_group(
        namespace_name=ns,
        create_log_analytics_log_group_details=m.CreateLogAnalyticsLogGroupDetails(
            compartment_id=cfg["tenancy"], display_name=name,
            description="ZPR visibility ingestion target",
        ),
    ).data
    print(f"log group created: {name} -> {created.id}")
    return created.id


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="cap")
    p.add_argument("--region", default="eu-frankfurt-1")
    p.add_argument("--log-group-name", default="zpr-visibility-la")
    args = p.parse_args(argv)

    la, ns, cfg = _client(args.profile, args.region)
    print(f"namespace: {ns}")
    field_map = ensure_fields(la, ns)
    lg_id = ensure_log_group(la, ns, cfg, args.log_group_name)

    # NOTE: custom JSON parser creation currently returns a deterministic
    # HTTP 500 in some tenancies/regions (the auto-generated custom fields
    # lack facet/table-eligibility flags that are not settable via upsert_field).
    # Fields + log group + dashboard-query validation work regardless; the
    # parser/source can be created in the OCI Console as a fallback.
    parser_name = source_name = None
    try:
        parser_name = ensure_parser(la, ns, field_map)
        source_name = ensure_source(la, ns, parser_name)
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"WARN: parser/source creation failed: {getattr(exc, 'message', exc)}")
        print("      Fields + log group are ready; create the JSON parser+source "
              "in the OCI Console, then enable the Connector Hub connector.")

    print("\nProvisioned:")
    print(f"  fields     = {len(field_map)} ready")
    print(f"  log_group  = {lg_id}")
    print(f"  parser     = {parser_name or 'PENDING (see WARN)'}")
    print(f"  source     = {source_name or 'PENDING (see WARN)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
