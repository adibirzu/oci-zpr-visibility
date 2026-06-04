#!/usr/bin/env python3
"""Thin shim — implementation lives in oci_zpr_visibility.seed.

Kept so existing docs/commands (scripts/seed_cap.py ...) keep working; prefer
`oci-zpr-visibility seed` going forward.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oci_zpr_visibility.seed import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
