#!/usr/bin/env python3
"""Thin shim for the tenant-neutral ZPR demonstration seed command."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oci_zpr_visibility.seed import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
