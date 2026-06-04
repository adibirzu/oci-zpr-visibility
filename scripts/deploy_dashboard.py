#!/usr/bin/env python3
"""Thin shim — implementation lives in oci_zpr_visibility.deploy_dashboard.

Prefer `oci-zpr-visibility deploy-dashboard` going forward.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oci_zpr_visibility.deploy_dashboard import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
