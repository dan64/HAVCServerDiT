#!/usr/bin/env python3
r"""Build `comfy_bridge_<ver>.zip` (the vendored ComfyUI runtime) for a release.

The repo stays the single source of truth: the zip is built from the same
`comfy_bridge/` tree that (until now) was packaged inside the `havc` wheel.
Exclusions are the historical ones: Python caches, editor/script backups and
`comfy_bridge/blueprints/` (ComfyUI UI material, not referenced by the
runtime code — see setup.py history in PHASE0_SPEC §2). `models/` is included
as an empty skeleton (`.gitkeep` only).

The zip is published as a release asset and extracted by `havc-install` step
`comfy-bridge` into `<install>\comfy_bridge` (existing `models/` files are
preserved on update).

Usage:
    python installer/build_comfy_zip.py [--version v0.32] [--out dist/comfy_bridge_v0.32.zip]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ComfyUI version contained in the vendored tree (release naming, e.g. the
# published asset is `comfy_bridge_v0.32.zip`).
DEFAULT_VERSION = "v0.32"

ROOT_DIR = "comfy_bridge"
SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".bak", ".orig", ".rej"}
EXCLUDE_RELS = ("blueprints",)

# Fixed timestamp: rebuilds of the same tree produce the same archive.
FIXED_DATE_TIME = (2026, 10, 5, 0, 0, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help=f"ComfyUI version tag for the file name (default: {DEFAULT_VERSION})")
    parser.add_argument("--out", type=Path, default=None,
                        help="output zip (default: dist/comfy_bridge_<version>.zip)")
    args = parser.parse_args()

    src = REPO_ROOT / ROOT_DIR
    if not src.is_dir():
        print(f"[ERROR] source tree not found: {src}", file=sys.stderr)
        return 1
    out = (args.out or (REPO_ROOT / "dist" / f"comfy_bridge_{args.version}.zip")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    files = []
    for path in sorted(src.rglob("*")):
        if path.is_dir() or path.suffix in SKIP_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(src).as_posix()
        if any(rel == ex or rel.startswith(ex + "/") for ex in EXCLUDE_RELS):
            continue
        # models/ ships as an EMPTY skeleton (the weights are downloaded on
        # first use and live only in the install): anything under it but the
        # .gitkeep placeholders (local test models, HF download caches) must
        # never leak into the release zip.
        if (rel == "models" or rel.startswith("models/")) and path.name != ".gitkeep":
            continue
        files.append((path, f"{ROOT_DIR}/{rel}"))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in files:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    size = out.stat().st_size
    print(f"Built: {out}")
    print(f"  files  : {len(files)}")
    print(f"  size   : {size} byte")
    print(f"  sha256 : {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
