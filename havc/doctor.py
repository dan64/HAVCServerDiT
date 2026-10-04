"""`havc doctor` — verifica non distruttiva dell'ambiente HAVC.

Esegue un set di check e stampa un report (leggibile o JSON).
Protocollo: installer/PHASE0_SPEC.md §7.
Exit code: 0 = nessun FAIL, 1 = almeno un FAIL, 2 = errore d'uso.
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
        "env", WARN, "non stai girando dentro un virtual environment",
        "usa il python del venv (es. .venv\\Scripts\\python.exe)",
    )


def check_python() -> dict:
    if sys.version_info[:2] == (3, 12):
        return _result("python", OK, f"Python {sys.version.split()[0]}")
    return _result(
        "python", FAIL, f"Python {sys.version.split()[0]} (richiesto 3.12)",
        "le wheel nunchaku e spatial_correlation_sampler sono cp312",
    )


def check_packages(req_dir: Path) -> dict:
    if not req_dir.is_dir():
        return _result(
            "packages", FAIL, f"lockfile non trovato: {req_dir}",
            "reinstalla la wheel `havc` o passa --lock-dir",
        )
    expected = read_lock(req_dir)
    if not expected:
        return _result("packages", FAIL, f"nessun pin leggibile in {req_dir}")
    missing, mismatch, conformi = [], [], 0
    for name, want in sorted(expected.items()):
        try:
            have = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            missing.append(name)
            continue
        if have == want:
            conformi += 1
        else:
            mismatch.append(f"{name}: atteso {want}, trovato {have}")
    if missing or mismatch:
        parts = []
        if missing:
            parts.append("mancanti: " + ", ".join(missing))
        if mismatch:
            parts.append("; ".join(mismatch))
        return _result(
            "packages", FAIL, " | ".join(parts),
            "esegui `havc-install` (o install.cmd) per allineare l'ambiente",
        )
    return _result("packages", OK, f"{conformi} pacchetti conformi al lock")


def check_patch() -> dict:
    if importlib.util.find_spec("nunchaku") is None:
        return _result("nunchaku-patch", SKIP, "nunchaku non installato")
    script = paths.find_patch_script()
    if script is None:
        return _result("nunchaku-patch", SKIP, "patch_nunchaku.py non trovato")
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--check"],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:
        return _result("nunchaku-patch", WARN, f"esecuzione del check fallita: {exc}")
    out = (proc.stdout or "") + (proc.stderr or "")
    if "already patched" in out:
        return _result("nunchaku-patch", OK, "patch applicata")
    if "original (not yet patched)" in out:
        return _result(
            "nunchaku-patch", FAIL, "patch NON applicata",
            "esegui `havc-patch-nunchaku` oppure `havc-install`",
        )
    return _result("nunchaku-patch", WARN, "stato non riconosciuto (versione nunchaku diversa?)")


def check_cuda() -> dict:
    if importlib.util.find_spec("torch") is None:
        return _result("cuda", FAIL, "torch non installato", "esegui `havc-install`")
    try:
        import torch
    except Exception as exc:
        return _result("cuda", FAIL, f"import torch fallito: {exc}")
    if not torch.cuda.is_available():
        return _result(
            "cuda", FAIL, f"torch {torch.__version__}: CUDA non disponibile",
            "verifica il driver NVIDIA (richiesto per i backend GPU)",
        )
    name = torch.cuda.get_device_name(0)
    return _result("cuda", OK, f"torch {torch.__version__} · CUDA {torch.version.cuda} · {name}")


def check_gpu() -> dict:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return _result("gpu", WARN, "nvidia-smi non trovato", "driver NVIDIA assente o fuori dal PATH")
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return _result("gpu", WARN, f"nvidia-smi errore: {exc}")
    out = (proc.stdout or "").strip()
    if not out:
        return _result("gpu", WARN, "nvidia-smi: nessuna GPU rilevata")
    return _result("gpu", OK, out.replace("\n", " | "))


def check_gui() -> dict:
    """GUI installata accanto al venv (in sviluppo: presente nel checkout)."""
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        gui_dir = Path(sys.prefix).parent / "gui"
        if (gui_dir / "CMNET2_colorize_client_GUI.py").is_file():
            return _result("gui", OK, f"GUI installata ({gui_dir})")
    root = paths.repo_root()
    if root is not None and (root / "GUI" / "CMNET2_colorize_client_GUI.py").is_file():
        return _result("gui", OK, "GUI presente nel checkout del repo")
    return _result("gui", WARN, "GUI non trovata (installazione server-only?)")


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
    checks.append(check_havc())
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="havc-doctor",
        description="Verifica l'ambiente HAVC (pacchetti vs lockfile, patch nunchaku, CUDA).",
        epilog="Specifica: installer/PHASE0_SPEC.md",
    )
    parser.add_argument("--json", action="store_true", help="output JSON su una riga")
    parser.add_argument("--fast", action="store_true", help="salta i check CUDA/GPU (lenti)")
    parser.add_argument("--lock-dir", type=Path, default=None,
                        help="cartella del lockfile (default: requirements inclusi nella wheel)")
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
        print(f"\nEsito: {'OK' if ok else 'FALLITO'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
