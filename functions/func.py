"""OCI Functions entrypoint for the ZPR Visibility collector.

Runs the same `refresh` unit (collect -> drift -> Upload API -> metrics) the
controller VM cron runs, but serverless. Functions provide a **resource
principal**, so no API keys and no instance are required.

Config (set with `fn config function <app> zpr-visibility-refresh <KEY> <VAL>`):
  STATE_BUCKET    (required)  Object Storage bucket for drift state
  REGION          (optional)  defaults to the function's region
  LOG_GROUP_NAME  (optional)  defaults to "zpr-visibility-la"
"""
import io
import json
import logging
import os

from fdk import response

from oci_zpr_visibility import refresh


def handler(ctx, data: io.BytesIO = None):
    cfg = dict(ctx.Config())
    state_bucket = cfg.get("STATE_BUCKET") or os.environ.get("STATE_BUCKET", "")
    region = cfg.get("REGION") or os.environ.get("REGION", "")
    log_group = cfg.get("LOG_GROUP_NAME") or os.environ.get("LOG_GROUP_NAME", "zpr-visibility-la")

    if not state_bucket:
        return response.Response(
            ctx, status_code=400,
            response_data=json.dumps({"error": "STATE_BUCKET config is required"}),
            headers={"Content-Type": "application/json"},
        )

    argv = ["--auth", "resource_principal", "--state-bucket", state_bucket,
            "--log-group-name", log_group, "--json"]
    if region:
        argv += ["--region", region]

    try:
        rc = refresh.main(argv)
        body = {"status": "ok" if rc == 0 else "error", "provision_rc": rc}
        code = 200 if rc == 0 else 500
    except Exception as exc:  # noqa: BLE001 - surface the failure to the invoker
        logging.exception("zpr-visibility refresh failed")
        body, code = {"status": "error", "message": str(exc)[:300]}, 500

    return response.Response(
        ctx, status_code=code,
        response_data=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
