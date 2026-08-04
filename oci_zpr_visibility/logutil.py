"""Output + logging helpers: human text by default, machine JSON with --json."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

_LOGGER_NAME = "oci_zpr_visibility"

# Service codes and operation names are fixed API vocabulary; anything outside
# this shape could carry tenant detail and is dropped rather than printed.
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def describe_exception(exc: BaseException) -> str:
    """Return a sanitized, non-identifying description of a failure.

    Exposes only the exception class plus the OCI service status, code, and
    operation name. Raw service messages carry OCIDs, resource names, request
    identifiers, and addresses, so they are never included.
    """
    parts = [exc.__class__.__name__]
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        parts.append(f"status={status}")
    for label, attribute in (("code", "code"), ("operation", "operation_name")):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
            parts.append(f"{label}={value}")
    return " ".join(parts)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure package logging (diagnostics go to stderr via logging)."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger(_LOGGER_NAME)


def emit(payload: dict[str, Any], human: str, as_json: bool = False) -> None:
    """Print a command result: JSON payload to stdout if as_json, else human text."""
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(human)
