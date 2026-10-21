"""OCI Functions entrypoint for the ZPR Visibility collector.

Runs the same `refresh` unit (collect -> drift -> Upload API -> metrics) the
controller VM cron runs, but serverless. Functions provide a **resource
principal**, so no API keys and no instance are required.

Config (set with `fn config function <app> zpr-visibility-refresh <KEY> <VAL>`):
  STATE_BUCKET    (required)  Object Storage bucket for drift state
  REGION          (optional)  defaults to the function's region
  LOG_GROUP_NAME  (optional)  defaults to "zpr-visibility-la"
  LOG_GROUP_COMPARTMENT_ID (optional) defaults to the tenancy
  FLOW_LOG_COMPARTMENT_ID / FLOW_LOG_GROUP_ID / FLOW_LOG_ID
                  (optional)  enable live VCN Flow Log correlation
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
    log_group_compartment_id = cfg.get("LOG_GROUP_COMPARTMENT_ID") or os.environ.get("LOG_GROUP_COMPARTMENT_ID", "")
    flow_compartment_id = cfg.get("FLOW_LOG_COMPARTMENT_ID") or os.environ.get("FLOW_LOG_COMPARTMENT_ID", "")
    flow_log_group_id = cfg.get("FLOW_LOG_GROUP_ID") or os.environ.get("FLOW_LOG_GROUP_ID", "")
    flow_log_id = cfg.get("FLOW_LOG_ID") or os.environ.get("FLOW_LOG_ID", "")
    flow_vcn_id = cfg.get("FLOW_VCN_ID") or os.environ.get("FLOW_VCN_ID", "")
    collection_scope = cfg.get("COLLECTION_COMPARTMENT_IDS") or os.environ.get("COLLECTION_COMPARTMENT_IDS", "")

    if not state_bucket:
        return response.Response(
            ctx, status_code=400,
            response_data=json.dumps({"error": "STATE_BUCKET config is required"}),
            headers={"Content-Type": "application/json"},
        )

    flow_flags = (flow_compartment_id, flow_log_group_id, flow_log_id, flow_vcn_id)
    if any(flow_flags) and (not flow_log_group_id or not flow_log_id):
        return response.Response(
            ctx, status_code=400,
            response_data=json.dumps({"error": "FLOW_LOG_GROUP_ID and FLOW_LOG_ID must be supplied together"}),
            headers={"Content-Type": "application/json"},
        )

    argv = ["--auth", "resource_principal", "--state-bucket", state_bucket,
            "--log-group-name", log_group, "--json"]
    if log_group_compartment_id:
        argv += ["--log-group-compartment-id", log_group_compartment_id]
    if collection_scope:
        try:
            scopes = json.loads(collection_scope)
            if (not isinstance(scopes, list) or not scopes
                    or any(not isinstance(cid, str) or not cid.strip() for cid in scopes)):
                raise ValueError("invalid scope")
        except (ValueError, TypeError):
            return response.Response(
                ctx, status_code=400,
                response_data=json.dumps({"error": "COLLECTION_COMPARTMENT_IDS must be a nonempty JSON array of compartment IDs"}),
                headers={"Content-Type": "application/json"},
            )
        for cid in scopes:
            argv += ["--collection-compartment-id", cid.strip()]
    if region:
        argv += ["--region", region]
    if flow_log_group_id and flow_log_id:
        if flow_compartment_id:
            argv += ["--flow-log-compartment-id", flow_compartment_id]
        argv += ["--flow-log-group-id", flow_log_group_id, "--flow-log-id", flow_log_id]
        if flow_vcn_id:
            argv += ["--flow-vcn-id", flow_vcn_id]

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
