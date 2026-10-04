"""Provisioning del runtime Python per l'installazione.

Il runtime è una build **python-build-standalone** (Astral — gli stessi Python
usati da `uv`), pinnata per versione e sha256, estratta in
`<install-dir>\\runtime\\python`. Da lì viene creato il venv.

Scelta e verifica (2026-10-04): l'embed ufficiale di python.org è inadatto —
privo di tkinter (serve alla GUI), venv ed ensurepip. La build
`install_only_stripped` di python-build-standalone include tutto (tkinter 8.6,
venv, ensurepip, pip) e si estrae senza installer né registry.
Vedi installer/PHASE0_SPEC.md §4-bis.
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
# Runtime pinnato. Dopo l'upload del mirror su GitHub (release con tag
# dedicato, es. `runtime-312`) `url` punterà al *nostro* asset; `mirror_of`
# resta l'URL upstream. Lo sha256 è verificato anche contro il `digest`
# ufficiale dell'asset GitHub di Astral (2026-10-04).
# ---------------------------------------------------------------------------
RUNTIME = {
    "name": "cpython-3.12.15+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "mirror_of": "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "sha256": "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402",
    "python": "3.12.15",
    "size": 22011023,
}


def runtime_python(install_dir: Path) -> Path:
    """Percorso dell'interprete dentro il runtime provisionato."""
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
    """Versione dell'interprete, o None se assente/non eseguibile."""
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
    """Scarica `url` in `dest` in modo atomico (file `.part` + rename)."""
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


def extract_archive(archive: Path, dest: Path) -> None:
    """Estrae mantenendo la radice `python/` dell'archivio (tar.gz/tgz/tar/zip)."""
    name = archive.name.lower()
    dest.mkdir(parents=True, exist_ok=True)
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive, "r:*") as tar:
            _require_python_root(tar.getnames())
            try:
                tar.extractall(dest, filter="data")  # PEP 706 (3.12+)
            except TypeError:
                tar.extractall(dest)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            _require_python_root(zf.namelist())
            zf.extractall(dest)
    else:
        raise ValueError(f"formato archivio non supportato: {archive.name}")


def _require_python_root(names) -> None:
    normalized = [n.replace("\\", "/") for n in names]
    if not any(n.startswith("python/") for n in normalized):
        raise ValueError("layout archivio inatteso: manca la radice 'python/'")
