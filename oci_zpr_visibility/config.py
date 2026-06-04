"""Typed, validated run configuration for OCI ZPR visibility commands."""
from __future__ import annotations

import argparse
from dataclasses import dataclass

AUTH_MODES = ("api_key", "instance_principal", "resource_principal")


@dataclass(frozen=True)
class RunConfig:
    """Immutable run configuration, validated at construction.

    Raises ValueError on invalid auth mode or empty profile so commands fail
    fast with a clear message instead of deep inside an OCI call.
    """

    auth: str
    config_file: str | None
    profile: str
    region: str | None

    def __post_init__(self) -> None:
        if self.auth not in AUTH_MODES:
            raise ValueError(f"invalid auth {self.auth!r}; expected one of {AUTH_MODES}")
        if not self.profile or not self.profile.strip():
            raise ValueError("profile must be a non-empty string")

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RunConfig":
        return cls(
            auth=getattr(args, "auth", "api_key"),
            config_file=getattr(args, "config_file", None),
            profile=getattr(args, "profile", "DEFAULT"),
            region=getattr(args, "region", None),
        )
