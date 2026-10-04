"""Lettura del lockfile (`requirements/*.txt`): pin esatti e wheel da URL.

Formati supportati:
    name==version            pin esatto
    name @ https://.../x.whl wheel diretta (la versione attesa è ricavata dal
                             nome del file — es. nunchaku-1.2.1+cu13.0torch2.10-...whl)
Commenti (#), opzioni (-...) e righe vuote sono ignorati.
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
    """Estrae {distribuzione: versione attesa} da un singolo file del lock."""
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
    """Tutti i pin della cartella del lock (unione di requirements/*.txt)."""
    expected: dict[str, str] = {}
    for path in sorted(req_dir.glob("*.txt")):
        expected.update(read_pins_file(path))
    return expected
