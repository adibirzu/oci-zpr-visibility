#!/usr/bin/env python3
"""Thin shim — implementation lives in oci_zpr_visibility.trigger.

Kept so existing docs/commands (scripts/trigger_rules.py ...) keep working; prefer
`oci-zpr-visibility trigger` going forward.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oci_zpr_visibility.trigger import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
