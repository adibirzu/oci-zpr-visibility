#!/opt/zpr-visibility/venv/bin/python
"""Delegate to the tested collector bootstrap/readiness implementation."""
import sys


def main():
    try:
        import os
        os.environ.setdefault(
            "OCI_ZPR_DASHBOARD_PATH",
            "/opt/zpr-visibility/log_analytics/dashboards/oci_zpr_visibility_dashboard.json",
        )
        from oci_zpr_visibility.controller_runtime import main as controller_main
        return controller_main(sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - sanitize image service tracebacks
        from oci_zpr_visibility.logutil import describe_exception
        print(f"controller failed: {describe_exception(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
