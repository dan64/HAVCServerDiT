r"""Build hook for the `havc` wheel.

The repo stays the single source of truth: at build time, data that is not a
"classic" Python package is copied into the wheel:

    config/*.json        ->  havc/configs/        (pipeline configs)
    requirements/*.txt   ->  havc/requirements/   (single lockfile)
    GUI/ (script+scripts) ->  havc/gui/            (GUI: default front-end)

The vendored ComfyUI runtime is NOT part of the wheel (2026-10-05): it ships
as a pinned zip (`dist/comfy_bridge_v0.30.zip`, built by
`installer/build_comfy_zip.py`) that havc-install extracts at the install
root (`<install>\comfy_bridge`) — models are preserved on update.

Intentional exclusions: Python caches and editor/script backups. See
installer/PHASE0_SPEC.md §2.
"""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".bak", ".orig", ".rej"}

# (source, destination, excluded subfolders).
# comfy_bridge left the wheel on 2026-10-05 (see the docstring): its zip is
# built by installer/build_comfy_zip.py with the same `blueprints` exclusion.
COPIES = (
    ("config", "havc/configs", ()),
    ("requirements", "havc/requirements", ()),
)

# Individual GUI files and groups to include in the wheel (the GUI is
# installed into <install>\gui by the `gui`/`gui-deps` steps of havc-install).
EXTRA_FILES = (
    ("GUI/CMNET2_colorize_client_GUI.py", "havc/gui/CMNET2_colorize_client_GUI.py"),
    ("GUI/load_image_DtD_GUI.py", "havc/gui/load_image_DtD_GUI.py"),
)
EXTRA_GLOBS = (
    ("GUI/scripts", "havc/gui/scripts", "*.vpy"),
)


class build_py(_build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        lib = Path(self.build_lib)
        # comfy_bridge is no longer part of the wheel: remove any copy left in
        # build/lib by previous builds (the loop below only cleans what it
        # copies from COPIES).
        stale = lib / "comfy_bridge"
        if stale.exists():
            shutil.rmtree(stale)
        for src_rel, dst_rel, exclude_dirs in COPIES:
            src = root / src_rel
            if not src.is_dir():
                raise SystemExit(f"setup.py: cartella sorgente mancante: {src}")
            target = lib / dst_rel
            # Deterministic copy: start from an empty destination.
            # Without this, files already copied into build/lib by previous
            # builds stay there even if removed/excluded from the source —
            # and bdist_wheel packages everything it finds
            # (found on 2026-10-04 with the blueprints exclusion).
            if target.exists():
                shutil.rmtree(target)
            self._copy_tree(src, target, exclude_dirs)
        for src_rel, dst_rel in EXTRA_FILES:
            src = root / src_rel
            if not src.is_file():
                raise SystemExit(f"setup.py: file sorgente mancante: {src}")
            target = lib / dst_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        for src_rel, dst_rel, pattern in EXTRA_GLOBS:
            src = root / src_rel
            if not src.is_dir():
                raise SystemExit(f"setup.py: cartella sorgente mancante: {src}")
            target = lib / dst_rel
            if target.exists():
                shutil.rmtree(target)
            for path in sorted(src.glob(pattern)):
                out = target / path.name
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, out)

    @staticmethod
    def _copy_tree(src: Path, dst: Path, exclude_dirs: tuple = ()) -> None:
        for path in src.rglob("*"):
            if path.is_dir() or path.suffix in SKIP_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(src).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in exclude_dirs):
                continue
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


setup(cmdclass={"build_py": build_py})
