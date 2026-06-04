#!/usr/bin/env python3
"""Thin shim — implementation lives in oci_zpr_visibility.provision_la.

Kept so existing docs/commands (scripts/provision_la.py ...) keep working; prefer
`oci-zpr-visibility provision-la` going forward.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oci_zpr_visibility.provision_la import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
