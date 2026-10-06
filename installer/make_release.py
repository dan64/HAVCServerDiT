#!/usr/bin/env python3
"""Generate (or verify) the `release.json` manifest of a HAVC release.

Contract: installer/PHASE0_SPEC.md §6. The single sources of truth stay in
the repo: the version in `havc/__init__.py`, the `runtime` block in
`havc/runtime.py`. This script computes sha256 and sizes from local
artifacts.

Generation (after building the wheel):

    python installer/make_release.py --tag v0.1.0 --artifacts-dir dist/staging

Verification of a manifest against local artifacts:

    python installer/make_release.py --verify dist/staging/release.json --artifacts-dir dist/staging

No publishing: uploading to GitHub stays a separate step
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
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


def collect_wheels(artifacts_dir: Path, version: str) -> tuple[Path, list[Path]]:
    """The project wheel (exactly one, with matching version) and the other wheels."""
    wheels = sorted(artifacts_dir.glob("*.whl"))
    if not wheels:
        fail(f"no wheels found in {artifacts_dir}")
    ignored = [
        p.name for p in sorted(artifacts_dir.iterdir())
        if p.is_file() and p.suffix != ".whl" and p.name != "release.json"
        and not p.name.startswith("comfy_bridge_v")
    ]
    if ignored:
        print(f"[warning] ignored files (not wheels): {', '.join(ignored)}")
    project = [p for p in wheels if p.name.startswith(f"havc-{version}-")]
    if len(project) != 1:
        fail(f"expected exactly one 'havc-{version}-*.whl' wheel in {artifacts_dir}, "
             f"found {len(project)}")
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
        fail(f"artifacts folder not found: {artifacts_dir}")
    if args.version and args.version != HAVC_VERSION:
        fail(f"--version {args.version} does not match havc/__init__.py "
             f"({HAVC_VERSION}): the version is changed ONLY in havc/__init__.py")
    version = HAVC_VERSION

    project, others = collect_wheels(artifacts_dir, version)

    wheels = [{**make_entry(project, args.repo, args.tag),
               "kind": "project", "install": "no-deps"}]
    assets = [{**make_entry(path, args.repo, args.tag),
               "kind": "python-wheel", "target": path.name.split("-")[0]}
              for path in others]

    # Vendored ComfyUI runtime: a versioned zip asset (e.g.
    # comfy_bridge_v0.30.zip), extracted by the `comfy-bridge` bootstrap
    # step at the install root. Optional: installs can also fall back to the
    # pinned URL in havc/install.py.
    comfy_zips = sorted(artifacts_dir.glob("comfy_bridge_v*.zip"))
    assets += [{**make_entry(path, args.repo, args.tag),
                "kind": "comfy-bridge", "target": "comfy_bridge"}
               for path in comfy_zips]

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

    print(f"Manifest generated: {out}")
    print(f"  app_version : {version}")
    print(f"  tag/repo    : {args.tag}  ({args.repo})")
    print(f"  wheels: {len(wheels)} | assets: {len(assets)}")
    for item in wheels + assets:
        print(f"    - {item['name']}  sha256 {item['sha256'][:16]}...  {item['size']} byte")


def verify(args: argparse.Namespace) -> None:
    manifest_path = args.verify.resolve()
    if not manifest_path.is_file():
        fail(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts_dir = args.artifacts_dir.resolve()

    entries = list(manifest.get("wheels", [])) + list(manifest.get("assets", []))
    if not entries:
        fail("the manifest lists no wheels/assets")

    failures = 0
    for item in entries:
        candidate = artifacts_dir / item.get("name", "")
        if not candidate.is_file():
            print(f"[FAIL] {item.get('name')}: file missing in {artifacts_dir}")
            failures += 1
            continue
        digest = sha256_of(candidate)
        size = candidate.stat().st_size
        if digest == item.get("sha256") and size == item.get("size"):
            print(f"[ok]   {item['name']}  ({size} byte)")
        else:
            print(f"[FAIL] {item['name']}  ({size} byte)")
            if digest != item.get("sha256"):
                print(f"        expected sha256 {item.get('sha256')}")
                print(f"        found         {digest}")
            if size != item.get("size"):
                print(f"        expected size {item.get('size')}")
            failures += 1

    for item in manifest.get("wheels", []):
        if item.get("kind") == "project" and \
                not item.get("name", "").startswith(f"havc-{manifest.get('app_version')}-"):
            print(f"[FAIL] {item.get('name')} does not match "
                  f"app_version {manifest.get('app_version')}")
            failures += 1

    if failures:
        print(f"\nVerification FAILED: {failures} problem(s)")
        sys.exit(1)
    print("\nVerification OK: all artifacts match the manifest")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="make_release.py",
        description="Generate or verify the release.json manifest "
                    "(spec: installer/PHASE0_SPEC.md §6).",
    )
    parser.add_argument("--tag", default=None,
                        help="release tag (e.g. v0.1.0) — required for generation")
    parser.add_argument("--artifacts-dir", type=Path, required=True,
                        help="folder with the artifacts (wheels); also used for verification")
    parser.add_argument("--out", type=Path, default=None,
                        help="manifest path (default: <artifacts-dir>/release.json)")
    parser.add_argument("--repo", default="dan64/HAVCServerDiT",
                        help="repo GitHub (default: dan64/HAVCServerDiT)")
    parser.add_argument("--channel", default="stable", choices=("stable", "beta"))
    parser.add_argument("--version", default=None,
                        help="extra assertion: must match havc/__init__.py")
    parser.add_argument("--bootstrap-min-version", default=None,
                        help="minimum bootstrap version (default: app version)")
    parser.add_argument("--requires-env-rebuild", action="store_true",
                        help="set requires_env_rebuild=true (substantial Python/lock change)")
    parser.add_argument("--verify", type=Path, default=None,
                        help="verify an existing manifest against <artifacts-dir>")
    args = parser.parse_args(argv)

    if args.verify is not None:
        verify(args)
        return 0
    if not args.tag:
        parser.error("--tag is required for generation (or use --verify)")
    generate(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
