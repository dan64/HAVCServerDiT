"""`havc-install` — bootstrap idempotente e convergente dello stack Python del server.

Principio guida: "install = update da stato vuoto". Ogni passo verifica prima di
agire e salta ciò che è già a posto (vedi installer/PHASE0_SPEC.md §4).

Esempi:
    havc-install --install-dir C:/HAVC --plan
    havc-install --install-dir C:/HAVC --runtime-zip runtime.tar.gz --assets-dir packages --wheel dist\\havc-0.1.0-py3-none-any.whl
    havc-install --install-dir C:/HAVC --only runtime,venv,pip --json-progress
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from . import __version__, paths
from .lockfile import read_lock, read_pins_file
from .progress import Progress, force_utf8
from .runtime import (RUNTIME, download_archive, extract_archive, probe_version,
                      sha256_of, runtime_python as find_runtime_python)

TORCH_INDEX = "https://download.pytorch.org/whl/cu130"
PIP_MIN = (24, 0)  # sotto questa soglia il passo `pip` aggiorna pip


class BootstrapError(RuntimeError):
    def __init__(self, message: str, remediation: str = ""):
        super().__init__(message)
        self.remediation = remediation


@dataclasses.dataclass
class Ctx:
    install_dir: Path
    progress: Progress
    dry_run: bool = False
    plan_only: bool = False
    assets_dir: Optional[Path] = None
    wheel: Optional[Path] = None
    python: Optional[Path] = None
    runtime_zip: Optional[Path] = None
    use_system_python: bool = False

    @property
    def env_dir(self) -> Path:
        """Il venv dell'installazione (creato dal runtime provisionato)."""
        return self.install_dir / "venv"

    @property
    def runtime_dir(self) -> Path:
        return self.install_dir / "runtime"

    @property
    def runtime_python(self) -> Path:
        return find_runtime_python(self.install_dir)

    @property
    def cache_dir(self) -> Path:
        return self.install_dir / "cache"

    @property
    def venv_python(self) -> Path:
        if os.name == "nt":
            return self.env_dir / "Scripts" / "python.exe"
        return self.env_dir / "bin" / "python"

    def venv_exists(self) -> bool:
        return (self.env_dir / "pyvenv.cfg").is_file() and self.venv_python.is_file()

    def env_python(self) -> Optional[Path]:
        """Interprete per creare il venv: runtime provisionato, altrimenti --python/3.12 di sistema."""
        if not self.use_system_python and self.runtime_python.is_file():
            return self.runtime_python
        return self.python or find_python312()

    # ---------------------------------------------------------------- run --
    def run(self, cmd, *, capture: Optional[bool] = None, check: bool = True,
            timeout: Optional[int] = None, env: Optional[dict] = None):
        if capture is None:
            capture = self.progress.json_mode
        cmd = [str(c) for c in cmd]
        pretty = " ".join(cmd)
        self.progress.event("log", level="cmd", message=pretty)
        if self.dry_run:
            self.progress.event("log", level="dry-run", message=f"[dry-run] {pretty}")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        proc = subprocess.run(cmd, capture_output=capture, text=True,
                              timeout=timeout, env=env)
        if capture:
            for line in (proc.stdout or "").splitlines():
                self.progress.event("log", level="out", message=line)
            for line in (proc.stderr or "").splitlines():
                self.progress.event("log", level="err", message=line)
        if check and proc.returncode != 0:
            detail = ""
            if capture:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                if tail:
                    detail = f" — ultima riga: {tail[-1]}"
            raise BootstrapError(f"comando fallito (exit {proc.returncode}): {pretty}{detail}")
        return proc

    # -------------------------------------------------------- query (ro) --
    def dist_version(self, dist: str) -> Optional[str]:
        if not self.venv_exists():
            return None
        code = (
            "import importlib.metadata as m, sys\n"
            "try:\n"
            "    print(m.version(sys.argv[1]))\n"
            "except Exception:\n"
            "    pass\n"
        )
        proc = subprocess.run([str(self.venv_python), "-c", code, dist],
                              capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        return out or None

    def unmet(self, expected: dict[str, str]) -> list[str]:
        problems = []
        for name, want in sorted(expected.items()):
            have = self.dist_version(name)
            if have is None:
                problems.append(f"{name} assente")
            elif have != want:
                problems.append(f"{name}: atteso {want}, trovato {have}")
        return problems


@dataclasses.dataclass
class Step:
    id: str
    title: str
    hint: str
    check: Callable[[Ctx], Optional[str]]  # None = da eseguire; str = motivo di salto
    run: Callable[[Ctx], Optional[str]]    # dettaglio opzionale per step_ok


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def find_python312() -> Optional[Path]:
    """Interprete 3.12 per creare il venv: quello corrente, `py -3.12`, o python3.12."""
    if sys.version_info[:2] == (3, 12):
        return Path(sys.executable)
    if os.name == "nt":
        probe = subprocess.run(
            ["py", "-3.12", "-c", "import sys;print(sys.executable)"],
            capture_output=True, text=True,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return Path(probe.stdout.strip().splitlines()[-1])
    found = shutil.which("python3.12")
    return Path(found) if found else None


def pip_version(ctx: Ctx) -> Optional[tuple[int, int]]:
    if not ctx.venv_exists():
        return None
    proc = subprocess.run([str(ctx.venv_python), "-m", "pip", "--version"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    tokens = (proc.stdout or "").split()
    if len(tokens) >= 2 and tokens[0] == "pip":
        try:
            major, minor = tokens[1].split(".")[:2]
            return int(major), int(minor)
        except (ValueError, IndexError):
            return None
    return None


def patch_state(ctx: Ctx) -> Optional[str]:
    """'patched' | 'original' | 'unknown' | None (= non determinabile)."""
    script = paths.find_patch_script()
    if script is None or ctx.dist_version("nunchaku") is None:
        return None
    proc = subprocess.run([str(ctx.venv_python), str(script), "--check"],
                          capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    if "already patched" in out:
        return "patched"
    if "original (not yet patched)" in out:
        return "original"
    return "unknown"


def find_diffusers_wheel(ctx: Ctx) -> Optional[Path]:
    if ctx.assets_dir is None:
        return None
    wheels = sorted(ctx.assets_dir.glob("diffusers-*.whl"))
    return wheels[0] if wheels else None


# ---------------------------------------------------------------------------
# Passi
# ---------------------------------------------------------------------------

def build_steps() -> list[Step]:
    req_dir = paths.requirements_dir()
    torch_txt = req_dir / "torch.txt"
    nunchaku_txt = req_dir / "nunchaku.txt"
    core_txt = req_dir / "core.txt"
    lock = read_lock(req_dir) if req_dir.is_dir() else {}
    core_pins = read_pins_file(core_txt) if core_txt.is_file() else {}
    torch_pins = {n: lock[n] for n in ("torch", "torchvision", "torchaudio") if n in lock}

    # -- 1. preflight ------------------------------------------------------
    def preflight_run(c: Ctx) -> str:
        if sys.version_info[:2] < (3, 9):
            raise BootstrapError(
                f"il bootstrap richiede Python >= 3.9 (trovato {sys.version.split()[0]})"
            )
        if not req_dir.is_dir():
            raise BootstrapError(
                f"lockfile non trovato: {req_dir}",
                "esegui dal checkout del progetto o reinstalla la wheel `havc`",
            )
        nota = "" if sys.version_info[:2] == (3, 12) else \
            " (il venv userà il runtime 3.12 provisionato)"
        return f"host: {sys.version.split()[0]}{nota}"

    # -- 2. runtime (Python provisionato) ----------------------------------
    def runtime_check(c: Ctx) -> Optional[str]:
        if c.use_system_python:
            return "uso il Python di sistema (--use-system-python)"
        found = probe_version(c.runtime_python)
        if found == RUNTIME["python"]:
            return f"runtime Python {found} già presente"
        return None

    def runtime_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event(
                "log", level="dry-run",
                message=f"[dry-run] runtime: archivio -> {c.cache_dir / RUNTIME['name']}; "
                        f"estrazione in {c.runtime_dir}; venv da {c.runtime_python}",
            )
            return "dry-run"
        if c.runtime_zip is not None:
            if not c.runtime_zip.is_file():
                raise BootstrapError(f"archivio runtime non trovato: {c.runtime_zip}")
            archive = c.runtime_zip
        else:
            cached = c.cache_dir / RUNTIME["name"]
            if cached.is_file() and sha256_of(cached) == RUNTIME["sha256"]:
                archive = cached
                c.progress.event("log", level="out",
                                 message=f"uso l'archivio in cache: {cached}")
            else:
                c.progress.event("log", level="out",
                                 message=f"scarico il runtime: {RUNTIME['url']}")
                try:
                    download_archive(RUNTIME["url"], cached, progress=c.progress)
                except Exception as exc:
                    raise BootstrapError(
                        f"download del runtime fallito: {exc}",
                        "verifica la connessione; oppure usa --runtime-zip con un archivio locale",
                    )
                archive = cached
        digest = sha256_of(archive)
        if digest != RUNTIME["sha256"]:
            raise BootstrapError(
                f"sha256 del runtime non corrisponde: {digest} != {RUNTIME['sha256']}",
                "riscarica l'archivio; se persiste, il file sorgente è cambiato",
            )
        target = c.runtime_dir / "python"
        if target.exists():
            shutil.rmtree(target)
        c.progress.event("log", level="out", message=f"estrazione in {c.runtime_dir} …")
        extract_archive(archive, c.runtime_dir)
        found = probe_version(c.runtime_python)
        if found != RUNTIME["python"]:
            raise BootstrapError(
                f"runtime inatteso dopo l'estrazione: {found!r} (atteso {RUNTIME['python']})"
            )
        return f"runtime Python {found} in {c.runtime_dir}"

    # -- 3. venv -----------------------------------------------------------
    def venv_check(c: Ctx) -> Optional[str]:
        return "venv già presente" if c.venv_exists() else None

    def venv_run(c: Ctx) -> str:
        base = c.env_python()
        if base is None:
            raise BootstrapError(
                "nessun Python utilizzabile per creare il venv",
                "abilita il runtime provisionato (default) oppure passa --python <3.12>",
            )
        c.run([base, "-m", "venv", str(c.env_dir)])
        return f"{c.env_dir} (da {base})"

    # -- 4. pip ------------------------------------------------------------
    def pip_check(c: Ctx) -> Optional[str]:
        version = pip_version(c)
        if version is not None and version >= PIP_MIN:
            return f"pip {version[0]}.{version[1]} già aggiornato"
        return None

    def pip_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        return "pip aggiornato"

    # -- 5. torch ----------------------------------------------------------
    def torch_check(c: Ctx) -> Optional[str]:
        return "torch già alla versione pinnata" if not c.unmet(torch_pins) else None

    def torch_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", torch_txt,
               "--index-url", TORCH_INDEX])
        return "PyTorch 2.10.0+cu130"

    # -- 6. nunchaku -------------------------------------------------------
    def nunchaku_check(c: Ctx) -> Optional[str]:
        want = lock.get("nunchaku")
        if want and c.dist_version("nunchaku") == want:
            return f"nunchaku {want} già installato"
        return None

    def nunchaku_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", nunchaku_txt])
        return str(lock.get("nunchaku", "nunchaku"))

    # -- 7. torch-repin ----------------------------------------------------
    def repin_check(c: Ctx) -> Optional[str]:
        return "torch invariato dopo nunchaku" if not c.unmet(torch_pins) else None

    def repin_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", torch_txt,
               "--index-url", TORCH_INDEX, "--force-reinstall"])
        return "re-pin torch 2.10.0+cu130"

    # -- 8. patch ----------------------------------------------------------
    def patch_check(c: Ctx) -> Optional[str]:
        if c.dist_version("nunchaku") is None:
            return "nunchaku non installato"
        if patch_state(c) == "patched":
            return "patch già applicata"
        return None

    def patch_run(c: Ctx) -> str:
        script = paths.find_patch_script()
        if script is None:
            raise BootstrapError("patch_nunchaku.py non trovato nella wheel/checkout")
        c.run([c.venv_python, str(script)])
        return "patch nunchaku applicata"

    # -- 9. diffusers ------------------------------------------------------
    def diffusers_check(c: Ctx) -> Optional[str]:
        want = lock.get("diffusers")
        if want and c.dist_version("diffusers") == want:
            return f"diffusers {want} già installato"
        return None

    def diffusers_run(c: Ctx) -> str:
        wheel = find_diffusers_wheel(c)
        if wheel is None:
            raise BootstrapError(
                "wheel diffusers non trovata",
                "passa --assets-dir <cartella con le wheel del repo> (es. packages/)",
            )
        c.run([c.venv_python, "-m", "pip", "install", str(wheel)])
        return wheel.name

    # -- 10. deps ----------------------------------------------------------
    def deps_check(c: Ctx) -> Optional[str]:
        return "dipendenze core già a posto" if not c.unmet(core_pins) else None

    def deps_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", core_txt])
        return "dipendenze core"

    # -- 11. wheel del progetto -------------------------------------------
    def wheel_check(c: Ctx) -> Optional[str]:
        if c.wheel is None:
            return "nessuna wheel del progetto fornita"
        if c.dist_version("havc") == __version__:
            return f"havc {__version__} già installato"
        return None

    def wheel_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "--force-reinstall",
               "--no-deps", str(c.wheel)])
        return c.wheel.name

    # -- 12. verify --------------------------------------------------------
    def verify_run(c: Ctx) -> str:
        env = dict(os.environ)
        if c.dist_version("havc") is None:
            env["PYTHONPATH"] = str(paths.repo_root() or paths.package_dir().parent)
        proc = c.run([c.venv_python, "-m", "havc.doctor", "--json"],
                     capture=True, check=False, env=env)
        if c.dry_run:
            return "dry-run"
        report = None
        for line in reversed((proc.stdout or "").strip().splitlines()):
            try:
                report = json.loads(line)
                break
            except Exception:
                continue
        if report is None:
            raise BootstrapError(
                "output di `havc doctor --json` non interpretabile",
                f"esegui a mano: {c.venv_python} -m havc.doctor",
            )
        failed = [x["check"] for x in report.get("checks", []) if x["status"] == "fail"]
        if failed:
            raise BootstrapError(
                "havc doctor segnala problemi: " + ", ".join(failed),
                "vedi il report del doctor",
            )
        return "doctor: tutti i check OK"

    return [
        Step("preflight", "Verifiche preliminari (host, lockfile)", "",
             lambda c: None, preflight_run),
        Step("runtime", "Runtime Python 3.12 (python-build-standalone)",
             "scarica/verifica/estrae l'archivio pinnato",
             runtime_check, runtime_run),
        Step("venv", "Virtualenv di destinazione", "python -m venv dal runtime",
             venv_check, venv_run),
        Step("pip", "Aggiornamento pip", "pip install --upgrade pip",
             pip_check, pip_run),
        Step("torch", "PyTorch 2.10.0+cu130", "pip install -r requirements/torch.txt --index-url ...",
             torch_check, torch_run),
        Step("nunchaku", "Nunchaku 1.2.1 (wheel da GitHub)", "pip install -r requirements/nunchaku.txt",
             nunchaku_check, nunchaku_run),
        Step("torch-repin", "Re-pin torch (se nunchaku l'ha aggiornato)", "pip install --force-reinstall",
             repin_check, repin_run),
        Step("patch", "Patch di compatibilità nunchaku", "python patch_nunchaku.py",
             patch_check, patch_run),
        Step("diffusers", "diffusers 0.37.0.dev0 (wheel locale)", "pip install packages/diffusers-*.whl",
             diffusers_check, diffusers_run),
        Step("deps", "Dipendenze core", "pip install -r requirements/core.txt",
             deps_check, deps_run),
        Step("wheel", "Wheel del progetto (havc)", "pip install --no-deps havc-*.whl",
             wheel_check, wheel_run),
        Step("verify", "Verifica finale (havc doctor)", "python -m havc.doctor",
             lambda c: None, verify_run),
    ]


def run_steps(ctx: Ctx, steps: list[Step], only: Optional[set[str]]) -> bool:
    selected = [s for s in steps if not only or s.id in only]
    if ctx.plan_only:
        plan = [
            {"id": s.id, "title": s.title, "hint": s.hint, "skip_reason": s.check(ctx)}
            for s in selected
        ]
        ctx.progress.event("plan", steps=plan)
        return True
    ok = True
    skipped = 0
    for step in selected:
        reason = step.check(ctx)
        if reason is not None:
            skipped += 1
            ctx.progress.event("step_skip", id=step.id, reason=reason)
            continue
        ctx.progress.event("step_begin", id=step.id, title=step.title)
        try:
            detail = step.run(ctx) or ""
        except BootstrapError as exc:
            ctx.progress.event("step_error", id=step.id, error=str(exc),
                               remediation=exc.remediation)
            ok = False
            break
        except Exception as exc:  # errore imprevisto: non nascondere il tipo
            ctx.progress.event("step_error", id=step.id, error=f"{type(exc).__name__}: {exc}",
                               remediation="")
            ok = False
            break
        ctx.progress.event("step_ok", id=step.id, detail=detail)
    ctx.progress.event("result", ok=ok, steps=len(selected), skipped=skipped)
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="havc-install",
        description="Bootstrap idempotente dello stack server HAVC "
                    "(install = update da stato vuoto).",
        epilog="Specifica: installer/PHASE0_SPEC.md",
    )
    parser.add_argument("--install-dir", required=True, type=Path,
                        help="cartella dell'installazione: runtime/, venv/, cache/ "
                             "(obbligatorio; nulla viene toccato fuori da qui)")
    parser.add_argument("--python", type=Path, default=None,
                        help="interprete con cui creare il venv (default: runtime provisionato)")
    parser.add_argument("--runtime-zip", type=Path, default=None,
                        help="usa un archivio runtime locale invece di scaricarlo (verificato via sha256)")
    parser.add_argument("--use-system-python", action="store_true",
                        help="salta il provisioning del runtime e usa il Python di sistema (sviluppo)")
    parser.add_argument("--assets-dir", type=Path, default=None,
                        help="cartella con le wheel locali (default: packages/ del checkout)")
    parser.add_argument("--wheel", type=Path, default=None,
                        help="wheel del progetto (havc-*.whl) da installare")
    parser.add_argument("--only", default="",
                        help="esegui solo questi passi (id separati da virgola)")
    parser.add_argument("--plan", action="store_true",
                        help="mostra il piano senza eseguire nulla")
    parser.add_argument("--dry-run", action="store_true",
                        help="mostra i comandi senza eseguirli")
    parser.add_argument("--json-progress", action="store_true",
                        help="eventi JSON su stdout (una riga per evento)")
    args = parser.parse_args(argv)
    force_utf8()

    progress = Progress(json_mode=args.json_progress)
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    steps = build_steps()
    ids = {s.id for s in steps}
    if only:
        unknown = only - ids
        if unknown:
            parser.error(f"passi sconosciuti: {', '.join(sorted(unknown))} "
                         f"(validi: {', '.join(sorted(ids))})")

    assets_dir = args.assets_dir
    if assets_dir is None:
        root = paths.repo_root()
        if root is not None and (root / "packages").is_dir():
            assets_dir = root / "packages"

    ctx = Ctx(
        install_dir=args.install_dir.resolve(),
        progress=progress,
        dry_run=args.dry_run,
        plan_only=args.plan,
        assets_dir=assets_dir.resolve() if assets_dir else None,
        wheel=args.wheel.resolve() if args.wheel else None,
        python=args.python,
        runtime_zip=args.runtime_zip.resolve() if args.runtime_zip else None,
        use_system_python=args.use_system_python,
    )
    ok = run_steps(ctx, steps, only)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
