#!/usr/bin/env python3
"""Genera (o verifica) il manifest `release.json` di una release HAVC.

Contratto: installer/PHASE0_SPEC.md §6. Le fonti uniche restano nel repo:
la versione in `havc/__init__.py`, il blocco `runtime` in `havc/runtime.py`.
Questo script calcola sha256 e dimensioni dagli artefatti locali.

Generazione (dopo aver buildato la wheel):

    python installer/make_release.py --tag v0.1.0 --artifacts-dir dist/staging

Verifica di un manifest contro gli artefatti locali:

    python installer/make_release.py --verify dist/staging/release.json --artifacts-dir dist/staging

Nessuna pubblicazione: l'upload su GitHub resta un passo separato
(gh release create/upload).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from havc import __version__ as HAVC_VERSION  # noqa: E402
from havc.runtime import RUNTIME as RUNTIME_INFO  # noqa: E402

SCHEMA = 1
APP = "havc"
REQUIRES_PYTHON = "3.12"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    print(f"[ERRORE] {message}", file=sys.stderr)
    sys.exit(1)


def collect_wheels(artifacts_dir: Path, version: str) -> tuple[Path, list[Path]]:
    """La wheel del progetto (una sola, versione coerente) e le altre wheel."""
    wheels = sorted(artifacts_dir.glob("*.whl"))
    if not wheels:
        fail(f"nessuna wheel trovata in {artifacts_dir}")
    ignored = [
        p.name for p in sorted(artifacts_dir.iterdir())
        if p.is_file() and p.suffix != ".whl" and p.name != "release.json"
    ]
    if ignored:
        print(f"[avviso] file ignorati (non wheel): {', '.join(ignored)}")
    project = [p for p in wheels if p.name.startswith(f"havc-{version}-")]
    if len(project) != 1:
        fail(f"attesa esattamente una wheel 'havc-{version}-*.whl' in {artifacts_dir}, "
             f"trovate {len(project)}")
    others = [p for p in wheels if p not in project]
    return project[0], others


def make_entry(path: Path, repo: str, tag: str) -> dict:
    return {
        "name": path.name,
        "url": f"https://github.com/{repo}/releases/download/{tag}/{path.name}",
        "sha256": sha256_of(path),
        "size": path.stat().st_size,
    }


def generate(args: argparse.Namespace) -> None:
    artifacts_dir = args.artifacts_dir.resolve()
    if not artifacts_dir.is_dir():
        fail(f"cartella artefatti non trovata: {artifacts_dir}")
    if args.version and args.version != HAVC_VERSION:
        fail(f"--version {args.version} non corrisponde a havc/__init__.py "
             f"({HAVC_VERSION}): la versione si cambia SOLO in havc/__init__.py")
    version = HAVC_VERSION

    project, others = collect_wheels(artifacts_dir, version)

    wheels = [{**make_entry(project, args.repo, args.tag),
               "kind": "project", "install": "no-deps"}]
    assets = [{**make_entry(path, args.repo, args.tag),
               "kind": "python-wheel", "target": path.name.split("-")[0]}
              for path in others]

    manifest = {
        "schema": SCHEMA,
        "channel": args.channel,
        "app": APP,
        "app_version": version,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "requires_python": REQUIRES_PYTHON,
        "requires_env_rebuild": bool(args.requires_env_rebuild),
        "bootstrap_min_version": args.bootstrap_min_version or version,
        "runtime": {
            "name": RUNTIME_INFO["name"],
            "url": RUNTIME_INFO["url"],
            "sha256": RUNTIME_INFO["sha256"],
            "python": RUNTIME_INFO["python"],
            "kind": "python-build-standalone",
            "mirror_of": RUNTIME_INFO["mirror_of"],
        },
        "wheels": wheels,
        "assets": assets,
        "weights": [],
        "tools": [],
        "notes_url": f"https://github.com/{args.repo}/releases/tag/{args.tag}",
    }

    out = (args.out or (artifacts_dir / "release.json")).resolve()
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(f"Manifest generato: {out}")
    print(f"  app_version : {version}")
    print(f"  tag/repo    : {args.tag}  ({args.repo})")
    print(f"  wheels: {len(wheels)} | assets: {len(assets)}")
    for item in wheels + assets:
        print(f"    - {item['name']}  sha256 {item['sha256'][:16]}...  {item['size']} byte")


def verify(args: argparse.Namespace) -> None:
    manifest_path = args.verify.resolve()
    if not manifest_path.is_file():
        fail(f"manifest non trovato: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts_dir = args.artifacts_dir.resolve()

    entries = list(manifest.get("wheels", [])) + list(manifest.get("assets", []))
    if not entries:
        fail("il manifest non elenca wheel/asset")

    failures = 0
    for item in entries:
        candidate = artifacts_dir / item.get("name", "")
        if not candidate.is_file():
            print(f"[FAIL] {item.get('name')}: file assente in {artifacts_dir}")
            failures += 1
            continue
        digest = sha256_of(candidate)
        size = candidate.stat().st_size
        if digest == item.get("sha256") and size == item.get("size"):
            print(f"[ok]   {item['name']}  ({size} byte)")
        else:
            print(f"[FAIL] {item['name']}  ({size} byte)")
            if digest != item.get("sha256"):
                print(f"        atteso sha256 {item.get('sha256')}")
                print(f"        trovato       {digest}")
            if size != item.get("size"):
                print(f"        atteso size {item.get('size')}")
            failures += 1

    for item in manifest.get("wheels", []):
        if item.get("kind") == "project" and \
                not item.get("name", "").startswith(f"havc-{manifest.get('app_version')}-"):
            print(f"[FAIL] {item.get('name')} non corrisponde ad "
                  f"app_version {manifest.get('app_version')}")
            failures += 1

    if failures:
        print(f"\nVerifica FALLITA: {failures} problema/i")
        sys.exit(1)
    print("\nVerifica OK: tutti gli artefatti corrispondono al manifest")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="make_release.py",
        description="Genera o verifica il manifest release.json "
                    "(specifica: installer/PHASE0_SPEC.md §6).",
    )
    parser.add_argument("--tag", default=None,
                        help="tag della release (es. v0.1.0) — obbligatorio in generazione")
    parser.add_argument("--artifacts-dir", type=Path, required=True,
                        help="cartella con gli artefatti (wheel); usata anche in verifica")
    parser.add_argument("--out", type=Path, default=None,
                        help="percorso del manifest (default: <artifacts-dir>/release.json)")
    parser.add_argument("--repo", default="dan64/HAVCServerDiT",
                        help="repo GitHub (default: dan64/HAVCServerDiT)")
    parser.add_argument("--channel", default="stable", choices=("stable", "beta"))
    parser.add_argument("--version", default=None,
                        help="asserzione extra: deve corrispondere a havc/__init__.py")
    parser.add_argument("--bootstrap-min-version", default=None,
                        help="versione minima del bootstrap (default: versione app)")
    parser.add_argument("--requires-env-rebuild", action="store_true",
                        help="imposta requires_env_rebuild=true (cambio Python/lock sostanziale)")
    parser.add_argument("--verify", type=Path, default=None,
                        help="verifica un manifest esistente contro <artifacts-dir>")
    args = parser.parse_args(argv)

    if args.verify is not None:
        verify(args)
        return 0
    if not args.tag:
        parser.error("--tag è obbligatorio in generazione (oppure usa --verify)")
    generate(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
