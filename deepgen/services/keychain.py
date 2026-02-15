from __future__ import annotations

import os
import platform
import shutil
import subprocess

SERVICE_PREFIX = "com.deepgen.provider"
_MEMORY_STORE: dict[tuple[str, str], str] = {}


def _backend_mode() -> str:
    mode = os.getenv("DEEPGEN_KEYCHAIN_BACKEND", "auto").strip().lower()
    if mode in {"auto", "security", "memory", "disabled"}:
        return mode
    return "auto"


def _security_available() -> bool:
    return platform.system() == "Darwin" and shutil.which("security") is not None


def backend_name() -> str:
    mode = _backend_mode()
    if mode == "memory":
        return "memory"
    if mode == "disabled":
        return "disabled"
    if mode == "security":
        return "security"
    return "security" if _security_available() else "disabled"


def is_available() -> bool:
    active = backend_name()
    return active in {"memory", "security"}


def _service_name(provider: str) -> str:
    return f"{SERVICE_PREFIX}.{provider.lower()}"


def get_secret(provider: str, field: str) -> str | None:
    active = backend_name()
    key = (provider.lower(), field)

    if active == "memory":
        return _MEMORY_STORE.get(key)
    if active != "security":
        return None

    cmd = [
        "security",
        "find-generic-password",
        "-s",
        _service_name(provider),
        "-a",
        field,
        "-w",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def set_secret(provider: str, field: str, value: str) -> bool:
    active = backend_name()
    key = (provider.lower(), field)

    if active == "memory":
        _MEMORY_STORE[key] = value
        return True
    if active != "security":
        return False

    cmd = [
        "security",
        "add-generic-password",
        "-U",
        "-s",
        _service_name(provider),
        "-a",
        field,
        "-w",
        value,
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc.returncode == 0


def delete_secret(provider: str, field: str) -> bool:
    active = backend_name()
    key = (provider.lower(), field)

    if active == "memory":
        _MEMORY_STORE.pop(key, None)
        return True
    if active != "security":
        return False

    cmd = [
        "security",
        "delete-generic-password",
        "-s",
        _service_name(provider),
        "-a",
        field,
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc.returncode == 0


def clear_memory_store_for_tests() -> None:
    _MEMORY_STORE.clear()
