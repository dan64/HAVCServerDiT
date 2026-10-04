"""Build hook per la wheel `havc`.

Il repo resta l'unica fonte di verità: al momento della build i dati che non
sono pacchetti Python "classici" vengono copiati dentro la wheel:

    config/*.json        ->  havc/configs/        (config di pipeline)
    requirements/*.txt   ->  havc/requirements/   (lockfile unico)
    comfy_bridge/**      ->  comfy_bridge/**      (runtime ComfyUI vendored:
                                                    file dati e cartelle non
                                                    importabili, es.
                                                    custom_nodes/ComfyUI-GGUF*)

Esclusioni volute: cache Python e backup degli editor/script.
Vedi installer/PHASE0_SPEC.md §2.
"""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".bak", ".orig", ".rej"}

COPIES = (
    ("config", "havc/configs"),
    ("requirements", "havc/requirements"),
    ("comfy_bridge", "comfy_bridge"),
)


class build_py(_build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        lib = Path(self.build_lib)
        for src_rel, dst_rel in COPIES:
            src = root / src_rel
            if not src.is_dir():
                raise SystemExit(f"setup.py: cartella sorgente mancante: {src}")
            self._copy_tree(src, lib / dst_rel)

    @staticmethod
    def _copy_tree(src: Path, dst: Path) -> None:
        for path in src.rglob("*"):
            if path.is_dir() or path.suffix in SKIP_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


setup(cmdclass={"build_py": build_py})
