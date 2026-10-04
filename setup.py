"""Build hook per la wheel `havc`.

Il repo resta l'unica fonte di verità: al momento della build i dati che non
sono pacchetti Python "classici" vengono copiati dentro la wheel:

    config/*.json        ->  havc/configs/        (config di pipeline)
    requirements/*.txt   ->  havc/requirements/   (lockfile unico)
    comfy_bridge/**      ->  comfy_bridge/**      (runtime ComfyUI vendored:
                                                    file dati e cartelle non
                                                    importabili, es.
                                                    custom_nodes/ComfyUI-GGUF*)

Esclusioni volute: cache Python, backup degli editor/script e
`comfy_bridge/blueprints/` (materiale della UI ComfyUI, non referenziato dal
codice del runtime — vedi COPIES). Vedi installer/PHASE0_SPEC.md §2.
"""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".bak", ".orig", ".rej"}

# (sorgente, destinazione, sottocartelle escluse).
# Esclusione esplicita e reversibile (2026-10-04): `blueprints/` è materiale
# della UI ComfyUI (80 template di workflow JSON + 14 shader `.frag` in
# `.glsl/`). Nessun riferimento nel codice del runtime (grep case-insensitive
# su tutto comfy_bridge + file di root); il runtime è usato solo via API.
# Se un percorso reale dovesse mai richiederli, basta togliere la voce.
COPIES = (
    ("config", "havc/configs", ()),
    ("requirements", "havc/requirements", ()),
    ("comfy_bridge", "comfy_bridge", ("blueprints",)),
)


class build_py(_build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        lib = Path(self.build_lib)
        for src_rel, dst_rel, exclude_dirs in COPIES:
            src = root / src_rel
            if not src.is_dir():
                raise SystemExit(f"setup.py: cartella sorgente mancante: {src}")
            target = lib / dst_rel
            # Copia deterministica: si riparte dalla destinazione vuota.
            # Senza questo, i file già copiati in build/lib dalle build
            # precedenti restano lì anche se rimossi/esclusi dal sorgente —
            # e bdist_wheel impacchetta comunque tutto ciò che trova
            # (trovato il 2026-10-04 con l'esclusione di blueprints).
            if target.exists():
                shutil.rmtree(target)
            self._copy_tree(src, target, exclude_dirs)

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
