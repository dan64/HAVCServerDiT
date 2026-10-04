"""Risoluzione dei percorsi dati: wheel installata vs checkout del repo.

Regola: la wheel contiene copie di `config/` e `requirements/` dentro il
pacchetto (`havc/configs`, `havc/requirements`); se non ci sono (stiamo
girando da un checkout), si usano le cartelle del repo.
Vedi installer/PHASE0_SPEC.md §2.
"""

from __future__ import annotations

from pathlib import Path


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path | None:
    """La cartella del checkout che contiene `config/` e `requirements/`, se esiste."""
    parent = package_dir().parent
    if (parent / "config").is_dir() and (parent / "requirements").is_dir():
        return parent
    return None


def _data_dir(name: str) -> Path:
    packaged = package_dir() / name  # wheel installata
    if packaged.is_dir():
        return packaged
    root = repo_root()
    if root is not None and (root / name).is_dir():
        return root / name  # checkout del repo
    return packaged  # il chiamante segnala l'errore


def configs_dir() -> Path:
    return _data_dir("configs")


def requirements_dir() -> Path:
    return _data_dir("requirements")


def config_path(name: str) -> Path:
    path = configs_dir() / name
    if not path.is_file():
        raise FileNotFoundError(f"config '{name}' non trovata in {configs_dir()}")
    return path


def find_patch_script() -> Path | None:
    """patch_nunchaku.py come py-module installato (site-packages) o nel checkout."""
    here = package_dir()
    for candidate in (here.parent / "patch_nunchaku.py", here / "patch_nunchaku.py"):
        if candidate.is_file():
            return candidate
    return None
