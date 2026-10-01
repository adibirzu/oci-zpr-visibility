#!/usr/bin/env python3
"""Extract the sensitive operator lifecycle output from a private RM state file."""
import argparse
import json
import os
from pathlib import Path
import tempfile


REQUIRED = {
    "namespace", "state_bucket", "installation", "region", "compartment",
    "instance", "attribute_namespace", "attribute_name", "attribute_description",
}


def extract(state_path: Path) -> dict:
    if state_path.is_symlink() or not state_path.is_file():
        raise ValueError("state input must be a regular non-symlink file")
    state = json.loads(state_path.read_text())
    output = state.get("outputs", {}).get("lifecycle_config")
    if not isinstance(output, dict) or output.get("sensitive") is not True:
        raise ValueError("state does not contain a sensitive lifecycle_config output")
    config = output.get("value")
    if isinstance(config, str):
        config = json.loads(config)
    if not isinstance(config, dict) or set(config) != REQUIRED or any(
        not isinstance(value, str) or not value for value in config.values()
    ):
        raise ValueError("lifecycle_config output is incomplete")
    return config


def write_private(config: dict, output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite lifecycle configuration")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".zpr-lifecycle-", dir=output.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(config, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_private(extract(args.state), args.output)
    print("Private lifecycle configuration written with mode 0600")


if __name__ == "__main__":
    main()
