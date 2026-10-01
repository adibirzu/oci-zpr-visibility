#!/usr/bin/env python3
"""Read-only LA field/dependency inventory; never deletes or infers creators.

Private field definitions and identity matches are saved mode 0600 outside the
repository. Field metadata lacks creator identity; Audit evidence is required.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import oci

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oci_zpr_visibility.provision_la import FIELD_TOKENS, FIELD_DISPLAY_NAMES
from oci_zpr_visibility.logutil import describe_exception


def items(data):
    if isinstance(data, list):
        return data
    return getattr(data, "items", []) or []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--person", action="append", default=[], help="runtime-only identity name/email keywords (repeatable)")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not already exist")
    cfg = oci.config.from_file(profile_name=args.profile)
    cfg["region"] = args.region
    la = oci.log_analytics.LogAnalyticsClient(cfg)
    ns = oci.object_storage.ObjectStorageClient(cfg).get_namespace().data
    identity = oci.identity.IdentityClient(cfg)
    users = oci.pagination.list_call_get_all_results(identity.list_users, cfg["tenancy"]).data
    matches = {"operator": [], **{person: [] for person in args.person}}
    for user in users:
        text = " ".join(str(v or "") for v in (user.name, user.description, user.email)).lower()
        labels = []
        if user.id == cfg.get("user"):
            labels.append("operator")
        for person in args.person:
            if all(keyword in text for keyword in person.lower().split()):
                labels.append(person)
        for label in labels:
            matches[label].append({"id": user.id, "name": user.name})
    print("identity_matches", {key: len(value) for key, value in matches.items()}, flush=True)
    fields = oci.pagination.list_call_get_all_results(la.list_fields, namespace_name=ns, limit=2000).data
    custom = [field for field in fields if not field.is_system]
    protected = {token.lower() for token in FIELD_TOKENS} | {name.lower() for name in FIELD_DISPLAY_NAMES.values()}

    def check(field):
        row = {"field": oci.util.to_dict(field), "creator": "UNVERIFIED", "protected_by_project": field.display_name.lower() in protected}
        try:
            usage = la.get_field_usages(ns, field.name).data
            row["usage"] = oci.util.to_dict(usage)
            row["dependency_status"] = "REFERENCED" if usage.dependent_parsers or usage.dependent_sources else "NO_PARSER_SOURCE_REFERENCES"
        except Exception as exc:
            row["dependency_status"] = "UNAVAILABLE"
            row["error"] = describe_exception(exc)
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        pending = [executor.submit(check, field) for field in custom]
        for future in as_completed(pending):
            rows.append(future.result())
            if len(rows) % 100 == 0:
                print(f"field_usage_progress={len(rows)}/{len(custom)}", flush=True)
    report = {"retrieved_at": datetime.now(timezone.utc).isoformat(),
              "identity_matches": matches, "custom_field_count": len(custom),
              "creator_attribution": "requires successful creation Audit event; time_updated is not creation time",
              "deletion_ready_count": 0, "fields": sorted(rows, key=lambda row: row["field"]["name"])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(report, handle, indent=2)
    summary = {"custom_fields": len(custom),
               "referenced": sum(row["dependency_status"] == "REFERENCED" for row in rows),
               "no_parser_source_references": sum(row["dependency_status"] == "NO_PARSER_SOURCE_REFERENCES" for row in rows),
               "usage_unavailable": sum(row["dependency_status"] == "UNAVAILABLE" for row in rows),
               "deletion_ready": 0}
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
