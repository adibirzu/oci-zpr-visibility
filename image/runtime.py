#!/opt/zpr-visibility/venv/bin/python
"""Delegate to the tested collector bootstrap/readiness implementation."""
import sys


def main():
    from oci_zpr_visibility.controller_runtime import main as controller_main
    return controller_main(sys.argv[1:])


if __name__ == "__main__":
    main()
