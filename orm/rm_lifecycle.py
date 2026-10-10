#!/usr/bin/env python3
"""Resource Manager hook using platform OCI CLI, not an external skill.

Inputs come exclusively from Terraform self.input. Captured provider payloads
are never printed. Destroy fails closed if guest cleanup or ownership fails.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time


class Lifecycle:
    def __init__(self, cfg, *, auth="config", profile="DEFAULT"):
        self.cfg = cfg
        self.auth = auth
        self.profile = profile

    def cli(self, *args, raw=False):
        command = ["oci"]
        if self.auth == "config":
            command += ["--profile", self.profile]
        else:
            command += ["--auth", self.auth]
        result = subprocess.run([*command, "--region", self.cfg["region"], *args,
            "--output", "json"], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("OCI lifecycle operation failed; inspect private job diagnostics")
        return result.stdout if raw else json.loads(result.stdout)

    def verify(self):
        cfg = self.cfg
        bucket = self.cli("os", "bucket", "get", "--namespace-name", cfg["namespace"],
                          "--bucket-name", cfg["state_bucket"])["data"]
        if bucket["compartment-id"] != cfg["compartment"] or bucket.get("freeform-tags", {}).get("zpr-installation") != cfg["installation"]:
            raise ValueError("lifecycle bucket ownership mismatch")
        instance = self.cli("compute", "instance", "get", "--instance-id", cfg["instance"])["data"]
        if instance["compartment-id"] != cfg["compartment"] or instance.get("freeform-tags", {}).get("zpr-installation") != cfg["installation"]:
            raise ValueError("lifecycle controller ownership mismatch")

    def guest(self, operation):
        if operation not in {"status", "cleanup"}:
            raise ValueError("unsupported guest operation")
        cfg = self.cfg
        with tempfile.TemporaryDirectory(prefix="zpr-rm-command-") as temporary:
            target, content = Path(temporary) / "target.json", Path(temporary) / "content.json"
            target.write_text(json.dumps({"instanceId": cfg["instance"]}))
            content.write_text(json.dumps({"source": {"sourceType": "TEXT",
                "text": f"sudo /usr/local/sbin/zpr-{operation}"}, "output": {"outputType": "TEXT"}}))
            target.chmod(0o600)
            content.chmod(0o600)
            response = self.cli("instance-agent", "command", "create", "--compartment-id", cfg["compartment"],
                "--target", f"file://{target}", "--content", f"file://{content}",
                "--timeout-in-seconds", "600", "--display-name", f"zpr-rm-{operation}")
        command = response["data"]["id"]
        deadline = time.monotonic() + 650
        while time.monotonic() < deadline:
            result = self.cli("instance-agent", "command-execution", "get", "--instance-id", cfg["instance"],
                              "--command-id", command)["data"]
            state = result["lifecycle-state"]
            if state == "SUCCEEDED":
                if result["content"]["exit-code"] != 0:
                    raise RuntimeError("guest lifecycle command failed")
                return json.loads(result["content"]["text"])
            if state in {"FAILED", "TIMED_OUT", "CANCELED"}:
                raise RuntimeError("guest lifecycle command did not succeed")
            time.sleep(10)
        raise RuntimeError("guest lifecycle command timeout")

    def wait(self):
        self.verify()
        deadline = time.monotonic() + 2700
        while time.monotonic() < deadline:
            try:
                if self.guest("status").get("ready"):
                    print("Controller bootstrap, current-run indexing and query gate passed")
                    return
            except RuntimeError:
                pass
            time.sleep(30)
        raise RuntimeError("controller readiness timeout; stack apply must not report success")

    def destroy(self):
        self.verify()
        cfg = self.cfg
        objects = self.cli("os", "object", "list", "--namespace-name", cfg["namespace"],
            "--bucket-name", cfg["state_bucket"], "--all")["data"]
        if isinstance(objects, dict):
            objects = objects["objects"]
        names = {item["name"] for item in objects}
        allowed = {"zpr-visibility/ownership.json", "zpr-visibility/previous_records.jsonl"}
        if names - allowed:
            raise ValueError("state bucket contains unowned objects; export and review before destroy")
        self.verify_attribute()
        if "zpr-visibility/ownership.json" in names:
            self.guest("cleanup")
            journal = json.loads(self.cli("os", "object", "get", "--namespace-name", cfg["namespace"],
                "--bucket-name", cfg["state_bucket"], "--name", "zpr-visibility/ownership.json", "--file", "-", raw=True))
            target = journal["target"]
            if target["installation"] != cfg["installation"] or target["compartment"] != cfg["compartment"] or target["region"] != cfg["region"] or not journal.get("cleanup_complete"):
                raise ValueError("owned-content cleanup not confirmed")
        elif names:
            raise ValueError("state exists without ownership journal; explicit migration required")
        # The approved stack destroy explicitly purges only its dedicated state.
        for name in sorted(names):
            self.cli("os", "object", "delete", "--namespace-name", cfg["namespace"],
                "--bucket-name", cfg["state_bucket"], "--name", name, "--force")
        self.cli("security-attribute", "security-attribute", "update",
            "--security-attribute-namespace-id", cfg["attribute_namespace"],
            "--security-attribute-name", cfg["attribute_name"], "--is-retired", "true", "--force")
        print("Owned content cleaned, owned state purged, lab attribute retired; Terraform may destroy infrastructure")

    def verify_attribute(self):
        cfg = self.cfg
        attribute = self.cli("security-attribute", "security-attribute", "get",
            "--security-attribute-namespace-id", cfg["attribute_namespace"],
            "--security-attribute-name", cfg["attribute_name"])["data"]
        if attribute["description"] != cfg["attribute_description"]:
            raise ValueError("lab attribute ownership mismatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["wait", "destroy"])
    parser.add_argument("--config", required=True, help="Private lifecycle_config Terraform output JSON")
    parser.add_argument("--auth", choices=["config", "resource_principal", "instance_principal"], default="config")
    parser.add_argument("--profile", default="DEFAULT")
    args = parser.parse_args()
    runner = Lifecycle(json.loads(Path(args.config).read_text()), auth=args.auth, profile=args.profile)
    getattr(runner, args.action)()


if __name__ == "__main__":
    main()
