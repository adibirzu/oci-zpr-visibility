import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "extract_lifecycle_config", ROOT / "scripts/extract_lifecycle_config.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def config():
    return {key: key for key in module.REQUIRED}


def test_extracts_only_sensitive_complete_output(tmp_path):
    state = tmp_path / "terraform.tfstate"
    state.write_text(json.dumps({"outputs": {"lifecycle_config": {
        "sensitive": True, "value": json.dumps(config())}}}))
    assert module.extract(state) == config()


def test_rejects_non_sensitive_or_incomplete_output(tmp_path):
    state = tmp_path / "terraform.tfstate"
    state.write_text(json.dumps({"outputs": {"lifecycle_config": {
        "sensitive": False, "value": config()}}}))
    with pytest.raises(ValueError, match="sensitive"):
        module.extract(state)
    state.write_text(json.dumps({"outputs": {"lifecycle_config": {
        "sensitive": True, "value": {"region": "x"}}}}))
    with pytest.raises(ValueError, match="incomplete"):
        module.extract(state)


def test_private_output_is_mode_0600_and_never_overwrites(tmp_path):
    output = tmp_path / "private" / "lifecycle.json"
    module.write_private(config(), output)
    assert os.stat(output).st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="overwrite"):
        module.write_private(config(), output)
