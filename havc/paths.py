"""Data path resolution: installed wheel vs repo checkout.

Rule: the wheel bundles copies of `config/` and `requirements/` inside the
package (`havc/configs`, `havc/requirements`); if they are missing (running
from a checkout), the repo folders are used.
See installer/PHASE0_SPEC.md §2.
"""

from __future__ import annotations

from pathlib import Path


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path | None:
    """The checkout folder containing `config/` and `requirements/`, if it exists."""
    parent = package_dir().parent
    if (parent / "config").is_dir() and (parent / "requirements").is_dir():
        return parent
    return None


def _data_dir(name: str) -> Path:
    packaged = package_dir() / name  # installed wheel
    if packaged.is_dir():
        return packaged
    root = repo_root()
    if root is not None and (root / name).is_dir():
        return root / name  # repo checkout
    return packaged  # the caller reports the error


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
    """patch_nunchaku.py as an installed py-module (site-packages) or in the checkout."""
    here = package_dir()
    for candidate in (here.parent / "patch_nunchaku.py", here / "patch_nunchaku.py"):
        if candidate.is_file():
            return candidate
    return None


def gui_source_dir() -> Path | None:
    """GUI folder (main script + scripts/*.vpy): copy bundled in the package
    (`havc/gui`) or repo checkout (`GUI/`)."""
    packaged = package_dir() / "gui"
    if (packaged / "CMNET2_colorize_client_GUI.py").is_file():
        return packaged
    root = repo_root()
    if root is not None and (root / "GUI" / "CMNET2_colorize_client_GUI.py").is_file():
        return root / "GUI"
    return None
