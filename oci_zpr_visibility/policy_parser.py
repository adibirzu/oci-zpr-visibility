"""Best-effort parser for OCI ZPR policy statements.

The parser keeps the raw statement and emits parser confidence. ZPR policy
syntax can evolve, so unparsed fields should be handled as unknown instead of
discarding the statement.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from typing import Any


ATTRIBUTE_RE = re.compile(r"\b([A-Za-z][\w-]*(?:[.:][A-Za-z][\w-]*){1,2})\b")
CIDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RELATION_RE = re.compile(
    r"(?:^|\bin\s+(?P<scope>.+?)\s+)?allow\s+(?P<source>.+?)\s+"
    r"(?:endpoints?\s+)?to\s+connect\s+to\s+(?P<destination>.+?)"
    r"(?:\s+endpoints?)?(?:$|\s+where\s+|\s+using\s+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedStatement:
    raw_statement: str
    statement_hash: str
    action: str
    source_attribute: str | None
    destination_attribute: str | None
    network_scope: str | None
    target_type: str
    cidrs: tuple[str, ...]
    ips: tuple[str, ...]
    attribute_references: tuple[str, ...]
    parser_confidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement": self.raw_statement,
            "statement_hash": self.statement_hash,
            "action": self.action,
            "source_attribute": self.source_attribute,
            "destination_attribute": self.destination_attribute,
            "network_scope": self.network_scope,
            "target_type": self.target_type,
            "cidrs": list(self.cidrs),
            "ips": list(self.ips),
            "attribute_references": list(self.attribute_references),
            "parser_confidence": self.parser_confidence,
        }


def _valid_cidrs(statement: str) -> tuple[str, ...]:
    valid: list[str] = []
    for candidate in CIDR_RE.findall(statement):
        try:
            valid.append(str(ipaddress.ip_network(candidate, strict=False)))
        except ValueError:
            continue
    return tuple(dict.fromkeys(valid))


def _valid_ips(statement: str, cidrs: tuple[str, ...]) -> tuple[str, ...]:
    cidr_hosts = {cidr.split("/", 1)[0] for cidr in cidrs}
    valid: list[str] = []
    for candidate in IP_RE.findall(statement):
        if candidate in cidr_hosts:
            continue
        try:
            valid.append(str(ipaddress.ip_address(candidate)))
        except ValueError:
            continue
    return tuple(dict.fromkeys(valid))


def _attributes(text: str) -> list[str]:
    values: list[str] = []
    for match in ATTRIBUTE_RE.findall(text):
        lowered = match.lower()
        if lowered.startswith(("http:", "https:")):
            continue
        values.append(match)
    return list(dict.fromkeys(values))


def parse_statement(statement: str) -> ParsedStatement:
    raw = " ".join(statement.strip().split())
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    cidrs = _valid_cidrs(raw)
    ips = _valid_ips(raw, cidrs)
    references = tuple(_attributes(raw))

    relation = RELATION_RE.search(raw)
    source_attribute: str | None = None
    destination_attribute: str | None = None
    network_scope: str | None = None
    confidence = "low"

    if relation:
        network_scope = relation.group("scope")
        source_refs = _attributes(relation.group("source"))
        destination_refs = _attributes(relation.group("destination"))
        source_attribute = source_refs[0] if source_refs else None
        destination_attribute = destination_refs[0] if destination_refs else None
        if source_attribute and (destination_attribute or cidrs or ips):
            confidence = "high"
        else:
            confidence = "medium"

    target_type = "attribute"
    if cidrs:
        target_type = "cidr"
    elif ips:
        target_type = "ip"
    elif not destination_attribute:
        target_type = "unknown"

    return ParsedStatement(
        raw_statement=raw,
        statement_hash=digest,
        action="allow" if " allow " in f" {raw.lower()} " else "unknown",
        source_attribute=source_attribute,
        destination_attribute=destination_attribute,
        network_scope=network_scope,
        target_type=target_type,
        cidrs=cidrs,
        ips=ips,
        attribute_references=references,
        parser_confidence=confidence,
    )


def statements_from_policy(policy: dict[str, Any]) -> list[str]:
    for key in ("statements", "policy_statements"):
        value = policy.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    statement = policy.get("statement")
    if statement:
        return [str(statement)]
    return []


def policy_statement_records(policy: dict[str, Any], snapshot_time: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for statement in statements_from_policy(policy):
        parsed = parse_statement(statement).as_dict()
        records.append(
            {
                "record_type": "zpr_policy_statement",
                "snapshot_time": snapshot_time,
                "policy_id": policy.get("id"),
                "policy_name": policy.get("name") or policy.get("display_name"),
                "policy_lifecycle_state": policy.get("lifecycle_state") or policy.get("state"),
                **parsed,
            }
        )
    return records
