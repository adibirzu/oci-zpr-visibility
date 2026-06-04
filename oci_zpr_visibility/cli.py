"""Command-line interface for OCI ZPR visibility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .collector import ZprCollector
from .correlate import correlate_flow_records
from .findings import generate_findings
from .jsonutil import read_json, read_jsonl, write_json, write_jsonl
from .logging_ingestion import emit_records
from .oci_clients import build_session
from .policy_parser import policy_statement_records


def _session(args: argparse.Namespace) -> Any:
    return build_session(args.auth, args.config_file, args.profile, args.region)


def cmd_enable_zpr(args: argparse.Namespace) -> int:
    result = ZprCollector(_session(args)).enable_zpr(dry_run=args.dry_run)
    write_json(args.output, result)
    print(f"Wrote ZPR enablement response to {args.output}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    collector = ZprCollector(_session(args))
    snapshot = collector.collect(include_resources=not args.skip_resources, resource_query=args.resource_query)
    records = collector.records_for_snapshot(snapshot)
    findings = generate_findings(snapshot, [r for r in records if r.get("record_type") == "zpr_policy_statement"])
    all_records = [*records, *findings]

    write_json(args.snapshot, snapshot)
    write_jsonl(args.records, all_records)
    if args.emit_log_id:
        emitted = emit_records(_session(args), args.emit_log_id, all_records, args.batch_size)
        print(f"Emitted {emitted} records to OCI Logging log {args.emit_log_id}")
    print(f"Wrote snapshot to {args.snapshot}")
    print(f"Wrote {len(all_records)} normalized records to {args.records}")
    return 0


def cmd_findings(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    policy_records: list[dict[str, Any]] = []
    for policy in snapshot.get("zpr_policies", []):
        policy_records.extend(policy_statement_records(policy, snapshot.get("snapshot_time", "")))
    findings = generate_findings(snapshot, policy_records)
    write_jsonl(args.output, findings)
    print(f"Wrote {len(findings)} findings to {args.output}")
    return 0


def cmd_correlate(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    policy_records: list[dict[str, Any]] = []
    for policy in snapshot.get("zpr_policies", []):
        policy_records.extend(policy_statement_records(policy, snapshot.get("snapshot_time", "")))
    flows = read_jsonl(args.flows)
    enriched = correlate_flow_records(flows, snapshot, policy_records)
    write_jsonl(args.output, enriched)
    print(f"Wrote {len(enriched)} enriched flow records to {args.output}")
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    records = read_jsonl(args.records)
    emitted = emit_records(_session(args), args.log_id, records, args.batch_size)
    print(f"Emitted {emitted} records to OCI Logging log {args.log_id}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    root = Path(args.output_dir)
    snapshot = read_json(Path("examples/sample_snapshot.json"))
    flows = read_jsonl(Path("examples/sample_flow_logs.jsonl"))
    policy_records: list[dict[str, Any]] = []
    for policy in snapshot.get("zpr_policies", []):
        policy_records.extend(policy_statement_records(policy, snapshot.get("snapshot_time", "")))
    findings = generate_findings(snapshot, policy_records)
    enriched = correlate_flow_records(flows, snapshot, policy_records)
    write_json(root / "snapshot.json", snapshot)
    write_jsonl(root / "records.jsonl", [*policy_records, *findings])
    write_jsonl(root / "enriched_flows.jsonl", enriched)
    print(f"Wrote demo outputs under {root}")
    return 0


def add_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    parser.add_argument("--config-file", default=None)
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--region", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oci-zpr-visibility")
    parser.add_argument("--version", action="version", version=f"oci-zpr-visibility {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    enable = sub.add_parser("enable-zpr", help="Enable ZPR in the tenancy root compartment.")
    add_auth_args(enable)
    enable.add_argument("--dry-run", action="store_true")
    enable.add_argument("--output", default="out/zpr_enable_response.json")
    enable.set_defaults(func=cmd_enable_zpr)

    collect = sub.add_parser("collect", help="Collect ZPR inventory and write normalized records.")
    add_auth_args(collect)
    collect.add_argument("--snapshot", default="out/zpr_snapshot.json")
    collect.add_argument("--records", default="out/zpr_records.jsonl")
    collect.add_argument("--resource-query", default=None)
    collect.add_argument("--skip-resources", action="store_true")
    collect.add_argument("--emit-log-id", default=None)
    collect.add_argument("--batch-size", type=int, default=100)
    collect.set_defaults(func=cmd_collect)

    findings = sub.add_parser("findings", help="Generate findings from an existing snapshot.")
    findings.add_argument("--snapshot", required=True)
    findings.add_argument("--output", default="out/zpr_findings.jsonl")
    findings.set_defaults(func=cmd_findings)

    correlate = sub.add_parser("correlate", help="Correlate JSONL VCN flow logs with a ZPR snapshot.")
    correlate.add_argument("--snapshot", required=True)
    correlate.add_argument("--flows", required=True)
    correlate.add_argument("--output", default="out/zpr_enriched_flows.jsonl")
    correlate.set_defaults(func=cmd_correlate)

    emit = sub.add_parser("emit", help="Emit normalized JSONL records to an OCI custom log.")
    add_auth_args(emit)
    emit.add_argument("--records", required=True)
    emit.add_argument("--log-id", required=True)
    emit.add_argument("--batch-size", type=int, default=100)
    emit.set_defaults(func=cmd_emit)

    demo = sub.add_parser("demo", help="Run local sample data through findings and correlation.")
    demo.add_argument("--output-dir", default="out/demo")
    demo.set_defaults(func=cmd_demo)

    # Consolidated operational subcommands are listed here for `--help`, but are
    # routed in main() before argparse so their flags pass through verbatim to the
    # delegated module's own argparse (the single source of truth). See _delegate.
    for name, _module_name, helptext in _DELEGATED_SUBCOMMANDS:
        sub.add_parser(name, help=helptext, add_help=False)

    return parser


# (subcommand, package module under oci_zpr_visibility, help text)
_DELEGATED_SUBCOMMANDS = [
    ("provision-la", "provision_la", "Provision LA fields/parser/source/log group; --upload to ingest records."),
    ("validate-dashboards", "validate_dashboards", "Execute dashboard queries against live LA (HIT/MISS/ERROR)."),
    ("seed", "seed", "Create the 'app' security attribute and a real ZPR policy."),
    ("trigger", "trigger", "Generate flows exercising every detection classification."),
]
_DELEGATED_MODULES = {name: module for name, module, _help in _DELEGATED_SUBCOMMANDS}


def _delegate(subcommand: str, argv: list[str]) -> int:
    """Forward remaining args to the delegated package module's main()."""
    import importlib

    module = importlib.import_module(f"oci_zpr_visibility.{_DELEGATED_MODULES[subcommand]}")
    return int(module.main(argv))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Route consolidated subcommands before argparse so their flags pass through.
    if argv and argv[0] in _DELEGATED_MODULES:
        return _delegate(argv[0], argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
