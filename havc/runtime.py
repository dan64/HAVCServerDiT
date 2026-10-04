"""Python runtime provisioning for the installation.

The runtime is a **python-build-standalone** build (Astral — the same Pythons
used by `uv`), pinned by version and sha256, extracted into
`<install-dir>\\runtime\\python`. The venv is created from there.

Choice and verification (2026-10-04): the official python.org embed is
unsuitable — no tkinter (needed by the GUI), no venv, no ensurepip. The
`install_only_stripped` python-build-standalone build includes everything
(tkinter 8.6, venv, ensurepip, pip) and extracts without an installer or a
registry. See installer/PHASE0_SPEC.md §4-bis.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Pinned runtime. `url` points to *our* mirror (release `runtime-312`,
# published on 2026-10-04, asset unchanged); `mirror_of` is the upstream URL.
# The sha256 was verified against the official GitHub `digest` of both
# assets and with an end-to-end download from the mirror (2026-10-04).
# ---------------------------------------------------------------------------
RUNTIME = {
    "name": "cpython-3.12.15+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "url": "https://github.com/dan64/HAVCServerDiT/releases/download/runtime-312/cpython-3.12.15+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "mirror_of": "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "sha256": "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402",
    "python": "3.12.15",
    "size": 22011023,
}


def runtime_python(install_dir: Path) -> Path:
    """Path of the interpreter inside the provisioned runtime."""
    if os.name == "nt":
        return install_dir / "runtime" / "python" / "python.exe"
    return install_dir / "runtime" / "python" / "bin" / "python3"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_version(python_exe: Path) -> str | None:
    """Interpreter version, or None if missing/not executable."""
    if not python_exe.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(python_exe), "-c", "import sys;print(sys.version.split()[0])"],
            capture_output=True, text=True, timeout=60,
        )
    except OSError:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def download_archive(url: str, dest: Path, progress=None) -> None:
    """Download `url` into `dest` atomically (`.part` file + rename)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            step = max(total // 10, 1) if total else 0
            next_mark = step
            with tmp.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress is not None and step and done >= next_mark:
                        suffix = f" / {total // (1024 * 1024)} MB" if total else ""
                        progress.event("log", level="out",
                                       message=f"  … {done // (1024 * 1024)} MB{suffix}")
                        next_mark += step
    except OSError as exc:
        raise RuntimeError(f"download fallito da {url}: {exc}") from exc
    tmp.replace(dest)


def extract_archive(archive: Path, dest: Path,
                    required_root: str | None = "python") -> None:
    """Extract an archive (tar.gz/tgz/tar/zip).

    If `required_root` is given, the archive must contain that root folder
    (protection against unexpected layouts); with None it extracts as-is
    ("flat" archives, e.g. NVEncC_9.17_x64.zip).
    """
    name = archive.name.lower()
    dest.mkdir(parents=True, exist_ok=True)
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive, "r:*") as tar:
            if required_root is not None:
                _require_root(tar.getnames(), required_root)
            try:
                tar.extractall(dest, filter="data")  # PEP 706 (3.12+)
            except TypeError:
                tar.extractall(dest)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            if required_root is not None:
                _require_root(zf.namelist(), required_root)
            zf.extractall(dest)
    else:
        raise ValueError(f"formato archivio non supportato: {archive.name}")


def _require_root(names, required_root: str) -> None:
    normalized = [n.replace("\\", "/") for n in names]
    prefix = required_root.rstrip("/") + "/"
    if not any(n.startswith(prefix) or n.rstrip("/") == required_root
               for n in normalized):
        raise ValueError(f"layout archivio inatteso: manca la radice '{required_root}/'")
