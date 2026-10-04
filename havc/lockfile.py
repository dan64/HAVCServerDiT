"""Lockfile reading (`requirements/*.txt`): exact pins and URL wheels.

Supported formats:
    name==version            exact pin
    name @ https://.../x.whl direct wheel (the expected version is derived
                             from the file name — e.g. nunchaku-1.2.1+cu13.0torch2.10-...whl)
Comments (#), options (-...) and blank lines are ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([^;\s]+)")
URL_RE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*@\s*(\S+)")


def _wheel_version_from_url(url: str) -> str | None:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".whl"):
        parts = name[:-4].split("-")
        if len(parts) >= 2:
            return parts[1]
    return None


def read_pins_file(path: Path) -> dict[str, str]:
    """Extract {distribution: expected version} from a single lock file."""
    expected: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = PIN_RE.match(line)
        if match:
            expected[match.group(1)] = match.group(2)
            continue
        match = URL_RE.match(line)
        if match:
            version = _wheel_version_from_url(match.group(2))
            if version:
                expected[match.group(1)] = version
    return expected


def read_lock(req_dir: Path) -> dict[str, str]:
    """All pins from the lock folder (union of requirements/*.txt)."""
    expected: dict[str, str] = {}
    for path in sorted(req_dir.glob("*.txt")):
        expected.update(read_pins_file(path))
    return expected
