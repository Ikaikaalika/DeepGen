from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class UpdateInfo:
    available: bool
    current_version: str
    latest_version: str
    download_url: str
    notes: str


def _normalize(version: str) -> tuple[int, int, int]:
    core = version.strip().split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    nums: list[int] = []
    for part in parts[:3]:
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def check_for_updates(current_version: str, feed_url: str, timeout_seconds: float = 4.0) -> UpdateInfo:
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(feed_url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        return UpdateInfo(
            available=False,
            current_version=current_version,
            latest_version=current_version,
            download_url="",
            notes=f"Update check failed: {exc}",
        )

    latest = data.get("latest") if isinstance(data, dict) else {}
    latest_version = str(latest.get("version", current_version)) if isinstance(latest, dict) else current_version
    download_url = str(latest.get("download_url", "")) if isinstance(latest, dict) else ""
    notes = str(latest.get("notes", "")) if isinstance(latest, dict) else ""

    available = _normalize(latest_version) > _normalize(current_version)
    return UpdateInfo(
        available=available,
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        notes=notes,
    )
