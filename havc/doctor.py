"""`havc doctor` — non-destructive verification of the HAVC environment.

Runs a set of checks and prints a report (readable or JSON).
Protocol: installer/PHASE0_SPEC.md §7.
Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = usage error.
"""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, paths
from .lockfile import read_lock
from .progress import force_utf8

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"


def _result(name: str, status: str, detail: str, remediation: str | None = None) -> dict:
    return {"check": name, "status": status, "detail": detail, "remediation": remediation}


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check_env() -> dict:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        return _result("env", OK, f"venv: {sys.prefix}")
    return _result(
        "env", WARN, "you are not running inside a virtual environment",
        "use the venv python (e.g. .venv\\Scripts\\python.exe)",
    )


def check_python() -> dict:
    if sys.version_info[:2] == (3, 12):
        return _result("python", OK, f"Python {sys.version.split()[0]}")
    return _result(
        "python", FAIL, f"Python {sys.version.split()[0]} (3.12 required)",
        "the nunchaku and spatial_correlation_sampler wheels are cp312",
    )


def check_packages(req_dir: Path) -> dict:
    if not req_dir.is_dir():
        return _result(
            "packages", FAIL, f"lockfile not found: {req_dir}",
            "reinstall the `havc` wheel or pass --lock-dir",
        )
    expected = read_lock(req_dir)
    if not expected:
        return _result("packages", FAIL, f"no readable pins in {req_dir}")
    missing, mismatch, matching = [], [], 0
    for name, want in sorted(expected.items()):
        try:
            have = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            missing.append(name)
            continue
        if have == want:
            matching += 1
        else:
            mismatch.append(f"{name}: expected {want}, found {have}")
    if missing or mismatch:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if mismatch:
            parts.append("; ".join(mismatch))
        return _result(
            "packages", FAIL, " | ".join(parts),
            "run `havc-install` (or install.cmd) to align the environment",
        )
    return _result("packages", OK, f"{matching} packages matching the lockfile")


def check_patch() -> dict:
    if importlib.util.find_spec("nunchaku") is None:
        return _result("nunchaku-patch", SKIP, "nunchaku not installed")
    script = paths.find_patch_script()
    if script is None:
        return _result("nunchaku-patch", SKIP, "patch_nunchaku.py not found")
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--check"],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:
        return _result("nunchaku-patch", WARN, f"check execution failed: {exc}")
    out = (proc.stdout or "") + (proc.stderr or "")
    if "already patched" in out:
        return _result("nunchaku-patch", OK, "patch applied")
    if "original (not yet patched)" in out:
        return _result(
            "nunchaku-patch", FAIL, "patch NOT applied",
            "run `havc-patch-nunchaku` or `havc-install`",
        )
    return _result("nunchaku-patch", WARN, "unrecognized state (different nunchaku version?)")


def check_cuda() -> dict:
    if importlib.util.find_spec("torch") is None:
        return _result("cuda", FAIL, "torch not installed", "run `havc-install`")
    try:
        import torch
    except Exception as exc:
        return _result("cuda", FAIL, f"torch import failed: {exc}")
    if not torch.cuda.is_available():
        return _result(
            "cuda", FAIL, f"torch {torch.__version__}: CUDA not available",
            "check the NVIDIA driver (required for the GPU backends)",
        )
    name = torch.cuda.get_device_name(0)
    return _result("cuda", OK, f"torch {torch.__version__} · CUDA {torch.version.cuda} · {name}")


def check_gpu() -> dict:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return _result("gpu", WARN, "nvidia-smi not found", "NVIDIA driver missing or not on PATH")
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return _result("gpu", WARN, f"nvidia-smi error: {exc}")
    out = (proc.stdout or "").strip()
    if not out:
        return _result("gpu", WARN, "nvidia-smi: no GPU detected")
    return _result("gpu", OK, out.replace("\n", " | "))


def check_gui() -> dict:
    """GUI installed next to the venv (in development: present in the checkout)."""
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        gui_dir = Path(sys.prefix).parent / "gui"
        if (gui_dir / "CMNET2_colorize_client_GUI.py").is_file():
            return _result("gui", OK, f"GUI installed ({gui_dir})")
    root = paths.repo_root()
    if root is not None and (root / "GUI" / "CMNET2_colorize_client_GUI.py").is_file():
        return _result("gui", OK, "GUI present in the repo checkout")
    return _result("gui", WARN, "GUI not found (server-only install?)")


def check_cmnet2() -> dict:
    """vscmnet2 plugins and weights (only if vscmnet2 is installed)."""
    if importlib.util.find_spec("vscmnet2") is None:
        return _result("cmnet2", SKIP, "vscmnet2 not installed")
    try:
        pkg = Path(importlib.util.find_spec("vscmnet2").origin).parent
    except Exception:
        return _result("cmnet2", WARN, "vscmnet2 path not determinable")
    missing = [
        label for label, path in (
            ("checkpoint DINOv3", pkg / "weights" / "DINOv3FeatureV6_LocalAtten_p374099.pth"),
            ("dinov3-vitb16", pkg / "weights" / "dinov3-vitb16" / "model.safetensors"),
            ("plugin", pkg / "plugins" / "SourceFilter" / "LSmashSource" / "LSMASHSource.dll"),
        ) if not path.is_file()
    ]
    if missing:
        return _result("cmnet2", WARN, "mancano: " + ", ".join(missing),
                       "run `havc-install` (cmnet2-plugins / cmnet2-weights steps)")
    return _result("cmnet2", OK, "plugins and DINOv3 weights present")


def check_havc() -> dict:
    return _result("havc", OK, f"havc {__version__} ({paths.package_dir().parent})")


# ---------------------------------------------------------------------------
# Runner + CLI
# ---------------------------------------------------------------------------

def run_checks(lock_dir: Path | None = None, fast: bool = False) -> list[dict]:
    req_dir = lock_dir or paths.requirements_dir()
    checks = [check_env(), check_python(), check_packages(req_dir), check_patch()]
    if not fast:
        checks.append(check_cuda())
        checks.append(check_gpu())
    checks.append(check_gui())
    checks.append(check_cmnet2())
    checks.append(check_havc())
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="havc-doctor",
        description="Verify the HAVC environment (packages vs lockfile, nunchaku patch, CUDA).",
        epilog="Specification: installer/PHASE0_SPEC.md",
    )
    parser.add_argument("--json", action="store_true", help="one-line JSON output")
    parser.add_argument("--fast", action="store_true", help="skip the CUDA/GPU checks (slow)")
    parser.add_argument("--lock-dir", type=Path, default=None,
                        help="lockfile folder (default: requirements bundled in the wheel)")
    args = parser.parse_args(argv)
    force_utf8()

    checks = run_checks(args.lock_dir, args.fast)
    ok = all(c["status"] != FAIL for c in checks)
    if args.json:
        print(json.dumps({"ok": ok, "version": __version__, "checks": checks},
                         ensure_ascii=False))
    else:
        icons = {OK: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]", SKIP: "[skip]"}
        print(f"HAVC doctor — havc {__version__}")
        for c in checks:
            print(f"  {icons.get(c['status'], '?')} {c['check']:<15} {c['detail']}")
            if c["remediation"] and c["status"] in (FAIL, WARN):
                print(f"         -> {c['remediation']}")
        print(f"\nEsito: {'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
