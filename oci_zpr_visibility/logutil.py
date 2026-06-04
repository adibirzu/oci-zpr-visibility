"""Output + logging helpers: human text by default, machine JSON with --json."""
from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER_NAME = "oci_zpr_visibility"


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
