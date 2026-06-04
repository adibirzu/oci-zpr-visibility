"""OCI SDK client factory with lazy imports for local testability."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


class OciSdkUnavailable(RuntimeError):
    pass


# (connect, read) seconds. Read is generous: LA field-inventory + query calls
# can be slow, but a finite ceiling turns a hung call into a failure.
DEFAULT_TIMEOUT = (10, 180)

# HTTP statuses worth retrying with backoff (throttle + transient server faults).
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def should_retry(status_code: int) -> bool:
    """Whether an OCI HTTP status should be retried (throttle/5xx, not 4xx)."""
    return status_code in RETRYABLE_STATUSES


def default_retry_strategy(oci: Any) -> Any:
    """Exponential-backoff retry strategy over RETRYABLE_STATUSES."""
    return (
        oci.retry.RetryStrategyBuilder()
        .add_max_attempts(max_attempts=4)
        .add_total_elapsed_time(total_elapsed_time_seconds=300)
        .add_service_error_check(
            service_error_retry_config={429: [], 500: [], 502: [], 503: [], 504: []},
            service_error_retry_on_any_5xx=True,
        )
        .get_retry_strategy()
    )


def load_oci() -> Any:
    try:
        return importlib.import_module("oci")
    except ImportError as exc:
        raise OciSdkUnavailable("Install dependencies with `python -m pip install -e .` before using OCI commands.") from exc


@dataclass(frozen=True)
class OciSession:
    oci: Any
    config: dict[str, Any]
    signer: Any | None = None

    @property
    def tenancy_id(self) -> str:
        tenancy = self.config.get("tenancy")
        if not tenancy:
            raise ValueError("OCI tenancy OCID is missing from the active config/session.")
        return str(tenancy)

    @property
    def region(self) -> str | None:
        region = self.config.get("region")
        return str(region) if region else None


def build_session(auth: str, config_file: str | None, profile: str | None, region: str | None) -> OciSession:
    oci = load_oci()
    auth = auth.replace("-", "_")

    if auth == "instance_principal":
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        cfg: dict[str, Any] = {"region": region or signer.region, "tenancy": signer.tenancy_id}
        return OciSession(oci=oci, config=cfg, signer=signer)

    if auth == "resource_principal":
        signer = oci.auth.signers.get_resource_principals_signer()
        cfg = {"region": region or getattr(signer, "region", None), "tenancy": getattr(signer, "tenancy_id", None)}
        return OciSession(oci=oci, config=cfg, signer=signer)

    cfg = oci.config.from_file(file_location=config_file, profile_name=profile) if config_file else oci.config.from_file(profile_name=profile)
    if region:
        cfg = {**cfg, "region": region}
    oci.config.validate_config(cfg)
    return OciSession(oci=oci, config=cfg)


def client(session: OciSession, dotted_name: str) -> Any:
    module_name, class_name = dotted_name.rsplit(".", 1)
    module = importlib.import_module(f"oci.{module_name}")
    cls = getattr(module, class_name)
    kwargs: dict[str, Any] = {"timeout": DEFAULT_TIMEOUT, "retry_strategy": default_retry_strategy(session.oci)}
    if session.signer:
        kwargs["signer"] = session.signer
    return cls(session.config, **kwargs)
