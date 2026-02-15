from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


DEFAULT_VERSION = "0.1.0"


def get_app_version() -> str:
    try:
        return version("deepgen")
    except PackageNotFoundError:
        return DEFAULT_VERSION
