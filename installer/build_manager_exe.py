"""Build the manager installer exe (HAVC-Setup-<ver>.exe) — PHASE1_SPEC §11.

Runs `dotnet publish` on HavcManager.App (Release, win-x64, self-contained,
single-file) and copies the result to <out>/HAVC-Setup-<ver>.exe. Prints the
size and sha256 (paste the hash in the release notes). Standard release step
since v0.1.11 (AGENTS log (47)).

Usage: python installer/build_manager_exe.py --version 0.1.11 [--out dist]
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_CSPROJ = ROOT / "manager" / "HavcManager.App" / "HavcManager.App.csproj"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True,
                        help="release version used in the file name (e.g. 0.1.11)")
    parser.add_argument("--out", type=Path, default=ROOT / "dist",
                        help="destination folder (default: <repo>/dist)")
    args = parser.parse_args()

    out_dir = args.out if args.out.is_absolute() else (ROOT / args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"HAVC-Setup-{args.version}.exe"

    with tempfile.TemporaryDirectory(prefix="havc-manager-publish-") as tmp:
        cmd = [
            "dotnet", "publish", str(APP_CSPROJ),
            "-c", "Release", "-r", "win-x64", "--self-contained", "true",
            "-p:PublishSingleFile=true",
            "-p:IncludeNativeLibrariesForSelfExtract=true",
            "-p:DebugType=None", "-p:DebugSymbols=false",
            "-o", tmp,
        ]
        print("+ " + " ".join(cmd))
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(f"dotnet publish failed (exit {proc.returncode})", file=sys.stderr)
            return 1
        produced = Path(tmp) / "HavcManager.App.exe"
        if not produced.is_file():
            print(f"publish output not found: {produced}", file=sys.stderr)
            return 1
        shutil.copy2(produced, target)

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"built:  {target}")
    print(f"size:   {target.stat().st_size} bytes")
    print(f"sha256: {digest}")
    print("Next: gh release upload <tag> <exe> and paste the sha256 in the notes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
