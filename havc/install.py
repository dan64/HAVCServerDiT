"""`havc-install` — bootstrap idempotente e convergente dello stack Python del server.

Principio guida: "install = update da stato vuoto". Ogni passo verifica prima di
agire e salta ciò che è già a posto (vedi installer/PHASE0_SPEC.md §4).

Esempi:
    havc-install --install-dir C:/HAVC --plan
    havc-install --install-dir C:/HAVC --runtime-zip runtime.tar.gz --tools-zip tools.zip --assets-dir packages --wheel dist\\havc-0.1.0-py3-none-any.whl
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
import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import __version__, paths
from .lockfile import read_lock, read_pins_file
from .progress import Progress, force_utf8
from .runtime import (RUNTIME, download_archive, extract_archive, probe_version,
                      sha256_of, runtime_python as find_runtime_python)

TORCH_INDEX = "https://download.pytorch.org/whl/cu130"
PIP_MIN = (24, 0)  # sotto questa soglia il passo `pip` aggiorna pip

# Tool esterni (x265/x264/mkvmerge) — archivio pinnato della Release v1.0.0;
# sha256 verificato anche contro il `digest` ufficiale GitHub (2026-10-04).
TOOLS = {
    "name": "tools.zip",
    "url": "https://github.com/dan64/HAVCServerDiT/releases/download/v1.0.0/tools.zip",
    "sha256": "0a17002e1bb8964d81ab892fdcf250c760764a71b3d5990d3f7865b38765aef5",
}

# NVEncC (encoder GPU di rigaya) — pacchetto "flat" (NVEncC64.exe + DLL nella
# radice dello zip): estratto in <install>\tools\NVEncC\. Stesso tag di TOOLS.
NVENC = {
    "name": "NVEncC_9.17_x64.zip",
    "url": "https://github.com/dan64/HAVCServerDiT/releases/download/v1.0.0/NVEncC_9.17_x64.zip",
    "sha256": "81111c82b954e582f6c4b59102537af61e7deb22c87c9d000855ff8782b51624",
    "size": 105481170,
}

# Asset cmnet2 (plugin + pesi) — pinnati; sha256 verificati anche contro i
# `digest` ufficiali GitHub (2026-10-04). Pesi DINOv3 dalla release cmnet2
# v1.3.0 (NON v1.2.0: il link nei README puntava a un asset inesistente) e
# v1.1.0; plugin dalla release vs-cmnet2 v1.0.0.
CMNET2_PLUGINS = {
    "name": "plugins_win.zip",
    "url": "https://github.com/dan64/vs-cmnet2/releases/download/v1.0.0/plugins_win.zip",
    "sha256": "3fa5117519e0d49211c90d496c65905a036c0a364e7b2b1addc00ca38d9bf256",
    "size": 31056312,
}

# (dest è relativo alla cartella del pacchetto vscmnet2; extract_root=None
#  significa "file singolo da copiare", altrimenti zip da estrarre)
CMNET2_DINOV3 = (
    {
        "name": "DINOv3FeatureV6_LocalAtten_p374099.pth",
        "url": "https://github.com/dan64/cmnet2/releases/download/v1.3.0/DINOv3FeatureV6_LocalAtten_p374099.pth",
        "sha256": "ccb635feeba003b63e9aa7d226e7de09ff0da3824f2b6709cc1b1aa163cad312",
        "size": 758716232,
        "dest": "weights",
        "extract_root": None,
    },
    {
        "name": "dinov3-vitb16.zip",
        "url": "https://github.com/dan64/cmnet2/releases/download/v1.1.0/dinov3-vitb16.zip",
        "sha256": "9a8eecd00d326552f78df733c322868d161246c015ea10ceaee3d3036c7f61b2",
        "size": 318219242,
        "dest": "weights",
        "extract_root": "dinov3-vitb16",
    },
)

CMNET2_DINOV2 = (
    {
        "name": "DINOv2FeatureV6_LocalAtten_s2_154000.pth",
        "url": "https://github.com/dan64/cmnet2/releases/download/v1.0.0/DINOv2FeatureV6_LocalAtten_s2_154000.pth",
        "sha256": "eaf6301d1a088c0d7133008079a83b5fac1fc0f791061b2cf1b657602013457a",
        "size": 494884817,
        "dest": "weights",
        "extract_root": None,
    },
    {
        "name": "dinov2_vits14_pretrain.pth",
        "url": "https://github.com/dan64/cmnet2/releases/download/v1.0.0/dinov2_vits14_pretrain.pth",
        "sha256": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9",
        "size": 88283115,
        "dest": "models/checkpoints",
        "extract_root": None,
    },
    {
        "name": "resnet18-5c106cde.pth",
        "url": "https://github.com/dan64/cmnet2/releases/download/v1.0.0/resnet18-5c106cde.pth",
        "sha256": "5c106cde386e87d4033832f2996f5493238eda96ccf559d1d62760c4de0613f8",
        "size": 46827520,
        "dest": "models/checkpoints",
        "extract_root": None,
    },
    {
        "name": "resnet50-19c8e357.pth",
        "url": "https://github.com/dan64/cmnet2/releases/download/v1.0.0/resnet50-19c8e357.pth",
        "sha256": "19c8e3572231adff6824a2da93fd67b5986919a2e65f8b6007eab4edee220097",
        "size": 102502400,
        "dest": "models/checkpoints",
        "extract_root": None,
    },
)

# Launcher scritti nella cartella di installazione (front-end di default = GUI).
# Contenuto ASCII; le righe vengono riscritte con CRLF al salvataggio (i .cmd
# con soli LF possono essere mal interpretati da cmd.exe).
LAUNCHERS = {
    "HAVC.cmd": r"""@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] HAVC environment not found under "%HERE%".
    echo         Run the installer first, or check that the folder is complete.
    pause
    exit /b 1
)
cd /d "%HERE%gui"
echo ============================================================
echo  HAVC - Hybrid Automatic Video Colorizer (GUI)
echo ============================================================
echo.
"%PY%" "CMNET2_colorize_client_GUI.py"
if errorlevel 1 (
    echo.
    echo [ERROR] The GUI exited with code %errorlevel%.
    pause
)
endlocal
""",
    "HAVC.vbs": r'''Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = here
sh.Run """" & here & "\HAVC.cmd""", 0, False
Set sh = Nothing
''',
    "HAVC-Server.cmd": r"""@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] HAVC environment not found under "%HERE%".
    pause
    exit /b 1
)
set "WHICH=%~1"
if "%WHICH%"=="" set "WHICH=int4"
set "CFG="
if /i "%WHICH%"=="int4"    set "CFG=qwen_nunchaku_int4.json"
if /i "%WHICH%"=="fp4"     set "CFG=qwen_nunchaku_fp4.json"
if /i "%WHICH%"=="q3"      set "CFG=qwen_gguf_q3.json"
if /i "%WHICH%"=="q4"      set "CFG=qwen_gguf_q4.json"
if /i "%WHICH%"=="longcat" set "CFG=longcat_gguf_q4.json"
if /i "%WHICH%"=="qwen21"  set "CFG=qwen21_viggle.json"
if "%CFG%"=="" (
    echo [ERROR] Unknown model "%WHICH%". Available: int4 fp4 q3 q4 longcat qwen21
    pause
    exit /b 1
)
echo Starting HAVC DiT Server (%WHICH%) ...
"%PY%" -u -m dit_rpc_server --host 127.0.0.1 --port 8765 --load-pipeline --pipeline-config "%HERE%config\%CFG%"
echo.
echo Server exited.
pause
endlocal
""",
    "HAVC-Doctor.cmd": r"""@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] HAVC environment not found under "%HERE%".
    pause
    exit /b 1
)
"%PY%" -m havc.doctor
pause
endlocal
""",
}


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
    tools_zip: Optional[Path] = None
    with_dinov2: bool = False
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

    def child_cwd(self) -> str:
        """CWD neutrale per i processi figli.

        Evita che il CWD del bootstrap (es. un checkout del repo con
        `havc.egg-info`) ombreggi i pacchetti del venv nelle query di
        metadata e nell'import di `havc.doctor` — bug trovato il 2026-10-04
        con l'end-to-end su cartella di test.
        """
        return str(self.install_dir if self.install_dir.is_dir()
                   else Path(tempfile.gettempdir()))

    def env_python(self) -> Optional[Path]:
        """Interprete per creare il venv: runtime provisionato, altrimenti --python/3.12 di sistema."""
        if not self.use_system_python and self.runtime_python.is_file():
            return self.runtime_python
        return self.python or find_python312()

    # ---------------------------------------------------------------- run --
    def run(self, cmd, *, capture: Optional[bool] = None, check: bool = True,
            timeout: Optional[int] = None, env: Optional[dict] = None,
            cwd: Optional[str] = None):
        if capture is None:
            capture = self.progress.json_mode
        cmd = [str(c) for c in cmd]
        pretty = " ".join(cmd)
        self.progress.event("log", level="cmd", message=pretty)
        if self.dry_run:
            self.progress.event("log", level="dry-run", message=f"[dry-run] {pretty}")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        proc = subprocess.run(cmd, capture_output=capture, text=True,
                              timeout=timeout, env=env,
                              cwd=cwd if cwd is not None else self.child_cwd())
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
                              capture_output=True, text=True, cwd=self.child_cwd())
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
                          capture_output=True, text=True, cwd=ctx.child_cwd())
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
                          capture_output=True, text=True, timeout=180,
                          cwd=ctx.child_cwd())
    out = (proc.stdout or "") + (proc.stderr or "")
    if "already patched" in out:
        return "patched"
    if "original (not yet patched)" in out:
        return "original"
    return "unknown"


def find_asset_wheel(ctx: Ctx, pattern: str) -> Optional[Path]:
    """Prima wheel che corrisponde al pattern in --assets-dir."""
    if ctx.assets_dir is None:
        return None
    wheels = sorted(ctx.assets_dir.glob(pattern))
    return wheels[0] if wheels else None


def find_diffusers_wheel(ctx: Ctx) -> Optional[Path]:
    return find_asset_wheel(ctx, "diffusers-*.whl")


def vscmnet2_dir(ctx: Ctx) -> Optional[Path]:
    """Cartella del pacchetto vscmnet2 nel venv (None se non installato).

    Usa `find_spec` senza eseguire il pacchetto (niente import di torch).
    """
    code = (
        "import importlib.util as u\n"
        "s = u.find_spec('vscmnet2')\n"
        "loc = list(s.submodule_search_locations)[0] "
        "if s and s.submodule_search_locations else ''\n"
        "print(loc)\n"
    )
    proc = subprocess.run([str(ctx.venv_python), "-c", code],
                          capture_output=True, text=True, cwd=ctx.child_cwd())
    out = (proc.stdout or "").strip()
    return Path(out) if out else None


def cached_download(ctx: Ctx, asset: dict, local: Optional[Path] = None) -> Path:
    """Ottiene un asset pinnato — file locale, cache o download — sempre con
    verifica sha256."""
    if local is not None:
        if not local.is_file():
            raise BootstrapError(f"archivio locale non trovato: {local}")
        digest = sha256_of(local)
        if digest != asset["sha256"]:
            raise BootstrapError(
                f"sha256 di {local.name} non corrisponde: {digest} != {asset['sha256']}",
                "il file locale è diverso dall'asset pinnato")
        return local
    cached = ctx.cache_dir / asset["name"]
    if cached.is_file() and sha256_of(cached) == asset["sha256"]:
        ctx.progress.event("log", level="out",
                           message=f"uso l'archivio in cache: {cached}")
        return cached
    ctx.progress.event("log", level="out", message=f"scarico: {asset['url']}")
    try:
        download_archive(asset["url"], cached, progress=ctx.progress)
    except Exception as exc:
        raise BootstrapError(f"download fallito ({asset['name']}): {exc}",
                             "verifica la connessione; riprova")
    digest = sha256_of(cached)
    if digest != asset["sha256"]:
        raise BootstrapError(
            f"sha256 non corrisponde per {asset['name']}: {digest} != {asset['sha256']}",
            "riscarica l'archivio; se persiste, il file sorgente è cambiato")
    return cached


# ---------------------------------------------------------------------------
# Passi
# ---------------------------------------------------------------------------

def build_steps() -> list[Step]:
    req_dir = paths.requirements_dir()
    torch_txt = req_dir / "torch.txt"
    nunchaku_txt = req_dir / "nunchaku.txt"
    core_txt = req_dir / "core.txt"
    gui_txt = req_dir / "gui.txt"
    lock = read_lock(req_dir) if req_dir.is_dir() else {}
    core_pins = read_pins_file(core_txt) if core_txt.is_file() else {}
    torch_pins = {n: lock[n] for n in ("torch", "torchvision", "torchaudio") if n in lock}
    gui_pins = read_pins_file(gui_txt) if gui_txt.is_file() else {}
    for _name in ("vscmnet2", "spatial_correlation_sampler"):
        if _name in lock:
            gui_pins[_name] = lock[_name]

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

    # -- 12. configs -------------------------------------------------------
    def configs_check(c: Ctx) -> Optional[str]:
        src = paths.configs_dir()
        if not src.is_dir():
            return None
        dst = c.install_dir / "config"
        missing = [p.name for p in src.glob("*.json") if not (dst / p.name).exists()]
        return "config già presenti" if not missing else None

    def configs_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] copia config -> {c.install_dir / 'config'}")
            return "dry-run"
        src = paths.configs_dir()
        if not src.is_dir():
            raise BootstrapError(f"config di origine non trovati: {src}",
                                 "reinstalla la wheel havc")
        dst = c.install_dir / "config"
        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in sorted(src.glob("*.json")):
            target = dst / path.name
            if not target.exists():
                shutil.copy2(path, target)
                copied += 1
        return f"{copied} config copiate" if copied else "nessuna config nuova"

    # -- 13. gui -----------------------------------------------------------
    def gui_check(c: Ctx) -> Optional[str]:
        target = c.install_dir / "gui" / "CMNET2_colorize_client_GUI.py"
        return "file GUI già presenti" if target.is_file() else None

    def gui_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] copia GUI -> {c.install_dir / 'gui'}")
            return "dry-run"
        src = paths.gui_source_dir()
        if src is None:
            raise BootstrapError(
                "file GUI non trovati (né nel pacchetto né nel checkout)",
                "reinstalla la wheel havc oppure esegui dal checkout del repo")
        dst = c.install_dir / "gui"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "CMNET2_colorize_client_GUI.py",
                     dst / "CMNET2_colorize_client_GUI.py")
        shutil.copy2(src / "load_image_DtD_GUI.py", dst / "load_image_DtD_GUI.py")
        scripts_dst = dst / "scripts"
        scripts_dst.mkdir(exist_ok=True)
        count = 0
        for path in sorted((src / "scripts").glob("*.vpy")):
            shutil.copy2(path, scripts_dst / path.name)
            count += 1
        return f"{count} script .vpy"

    # -- 14. gui-deps ------------------------------------------------------
    def gui_deps_check(c: Ctx) -> Optional[str]:
        return "dipendenze GUI già a posto" if not c.unmet(gui_pins) else None

    def gui_deps_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", gui_txt])
        for pattern, label in (("vscmnet2-*.whl", "vscmnet2"),
                               ("spatial_correlation_sampler-*.whl",
                                "spatial_correlation_sampler")):
            wheel = find_asset_wheel(c, pattern)
            if wheel is None:
                raise BootstrapError(
                    f"wheel {label} non trovata",
                    "passa --assets-dir con le wheel del repo (es. packages/)")
            c.run([c.venv_python, "-m", "pip", "install", str(wheel)])
        return "GUI + vscmnet2 + spatial_correlation_sampler"

    # -- 15. cmnet2-plugins ------------------------------------------------
    def cmnet2_plugins_check(c: Ctx) -> Optional[str]:
        pkg = vscmnet2_dir(c)
        if pkg is None:
            return "vscmnet2 non installato"
        if (pkg / "plugins" / "SourceFilter" / "LSmashSource" / "LSMASHSource.dll").is_file():
            return "plugin già presenti"
        return None

    def cmnet2_plugins_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message="[dry-run] plugin vs-cmnet2 -> vscmnet2/plugins")
            return "dry-run"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            raise BootstrapError("vscmnet2 non installato nel venv",
                                 "esegui prima il passo `gui-deps`")
        archive = cached_download(c, CMNET2_PLUGINS)
        extract_archive(archive, pkg, required_root="plugins")
        return "plugin in vscmnet2/plugins"

    # -- 16. cmnet2-weights ------------------------------------------------
    def cmnet2_weights_check(c: Ctx) -> Optional[str]:
        pkg = vscmnet2_dir(c)
        if pkg is None:
            return "vscmnet2 non installato"
        checkpoint = pkg / "weights" / CMNET2_DINOV3[0]["name"]
        vitb16 = pkg / "weights" / "dinov3-vitb16" / "model.safetensors"
        if (checkpoint.is_file() and checkpoint.stat().st_size == CMNET2_DINOV3[0]["size"]
                and vitb16.is_file()):
            return "pesi DINOv3 già presenti"
        return None

    def cmnet2_weights_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message="[dry-run] pesi DINOv3 -> vscmnet2/weights")
            return "dry-run"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            raise BootstrapError("vscmnet2 non installato nel venv",
                                 "esegui prima il passo `gui-deps`")
        weights = pkg / "weights"
        weights.mkdir(parents=True, exist_ok=True)
        done = []
        for asset in CMNET2_DINOV3:
            archive = cached_download(c, asset)
            if asset["extract_root"]:
                extract_archive(archive, weights, required_root=asset["extract_root"])
                done.append(f"{asset['name']} (estratto)")
            else:
                shutil.copy2(archive, weights / asset["name"])
                done.append(asset["name"])
        if not (weights / "dinov3-vitb16" / "model.safetensors").is_file():
            raise BootstrapError(
                "dinov3-vitb16/model.safetensors mancante dopo l'estrazione",
                "l'archivio potrebbe avere un layout inatteso")
        return ", ".join(done)

    # -- 17. cmnet2-dinov2 -------------------------------------------------
    def cmnet2_dinov2_check(c: Ctx) -> Optional[str]:
        if not c.with_dinov2:
            return "non richiesto (--with-dinov2)"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            return "vscmnet2 non installato"
        missing = [a["name"] for a in CMNET2_DINOV2
                   if not (pkg / a["dest"] / a["name"]).is_file()]
        return "pesi DINOv2 già presenti" if not missing else None

    def cmnet2_dinov2_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message="[dry-run] pesi DINOv2 -> vscmnet2/weights + models/checkpoints")
            return "dry-run"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            raise BootstrapError("vscmnet2 non installato nel venv",
                                 "esegui prima il passo `gui-deps`")
        for asset in CMNET2_DINOV2:
            dest_dir = pkg / asset["dest"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            archive = cached_download(c, asset)
            shutil.copy2(archive, dest_dir / asset["name"])
        return f"{len(CMNET2_DINOV2)} file DINOv2 (legacy)"

    # -- 18. tools ---------------------------------------------------------
    def tools_check(c: Ctx) -> Optional[str]:
        x265 = (c.install_dir / "tools" / "x265" / "x265.exe").is_file()
        nvenc = (c.install_dir / "tools" / "NVEncC" / "NVEncC64.exe").is_file()
        if x265 and nvenc:
            return "tool esterni già presenti"
        return None

    def tools_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] tools -> {c.install_dir / 'tools'} "
                                     "(x265/x264/mkvmerge + NVEncC)")
            return "dry-run"
        done = []
        if not (c.install_dir / "tools" / "x265" / "x265.exe").is_file():
            archive = cached_download(c, TOOLS, local=c.tools_zip)
            extract_archive(archive, c.install_dir, required_root="tools")
            done.append("x265, x264, mkvmerge")
        nvenc_exe = c.install_dir / "tools" / "NVEncC" / "NVEncC64.exe"
        if not nvenc_exe.is_file():
            archive = cached_download(c, NVENC)
            extract_archive(archive, c.install_dir / "tools" / "NVEncC",
                            required_root=None)
            if not nvenc_exe.is_file():
                raise BootstrapError(
                    "NVEncC64.exe mancante dopo l'estrazione",
                    "l'archivio potrebbe avere un layout inatteso")
            done.append("NVEncC 9.17")
        return ", ".join(done) if done else "già presenti"

    # -- 19. gui-settings --------------------------------------------------
    def gui_settings_check(c: Ctx) -> Optional[str]:
        settings = c.install_dir / "gui" / "gui_cmnet2_settings.json"
        return "settings già presenti" if settings.is_file() else None

    def gui_settings_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] settings GUI -> {c.install_dir / 'gui'}")
            return "dry-run"
        gui_dir = c.install_dir / "gui"
        if not gui_dir.is_dir():
            raise BootstrapError("cartella gui mancante", "esegui prima il passo `gui`")
        settings = {
            "script_dir": str(gui_dir / "scripts"),
            "vspipe_path": str(c.venv_python.parent / "vspipe.exe"),
            "x265_path": str(c.install_dir / "tools" / "x265" / "x265.exe"),
            "mkv_path": str(c.install_dir / "tools" / "MKVToolNix" / "mkvmerge.exe"),
            "base_dir": str(c.install_dir / "work"),
            "fixv_base_dir": str(c.install_dir / "work"),
        }
        path = gui_dir / "gui_cmnet2_settings.json"
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(settings, indent=4) + "\n")
        return "gui_cmnet2_settings.json creato"

    # -- 20. launchers -----------------------------------------------------
    def launchers_check(c: Ctx) -> Optional[str]:
        return "launcher già presenti" if (c.install_dir / "HAVC.cmd").is_file() else None

    def launchers_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] launcher -> {c.install_dir}")
            return "dry-run"
        for name, content in LAUNCHERS.items():
            path = c.install_dir / name
            path.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
        return ", ".join(LAUNCHERS)

    # -- 21. verify --------------------------------------------------------
    def verify_run(c: Ctx) -> str:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)  # niente ombreggiamenti dal chiamante
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
        Step("configs", "Config di pipeline in <install>/config", "copia le config mancanti",
             configs_check, configs_run),
        Step("gui", "File GUI in <install>/gui", "GUI + scripts .vpy",
             gui_check, gui_run),
        Step("gui-deps", "Dipendenze GUI (FreeSimpleGUI, tkinterdnd2, VapourSynth, vscmnet2, SCS)",
             "pip install -r requirements/gui.txt + wheel locali",
             gui_deps_check, gui_deps_run),
        Step("cmnet2-plugins", "Plugin vs-cmnet2 in vscmnet2/plugins",
             "plugins_win.zip (vs-cmnet2 v1.0.0, sha256)",
             cmnet2_plugins_check, cmnet2_plugins_run),
        Step("cmnet2-weights", "Pesi DINOv3 di vs-cmnet2",
             "checkpoint (cmnet2 v1.3.0) + dinov3-vitb16.zip (v1.1.0)",
             cmnet2_weights_check, cmnet2_weights_run),
        Step("cmnet2-dinov2", "Pesi DINOv2 legacy (opzionale)",
             "solo con --with-dinov2",
             cmnet2_dinov2_check, cmnet2_dinov2_run),
        Step("tools", "Tool esterni in <install>/tools",
             "tools.zip + NVEncC_9.17_x64.zip (Release v1.0.0) o --tools-zip",
             tools_check, tools_run),
        Step("gui-settings", "Settings GUI (solo se assenti)",
             "gui_cmnet2_settings.json pre-seedato",
             gui_settings_check, gui_settings_run),
        Step("launchers", "Launcher in <install>",
             "HAVC.cmd/.vbs (GUI), HAVC-Server.cmd, HAVC-Doctor.cmd",
             launchers_check, launchers_run),
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
    parser.add_argument("--tools-zip", type=Path, default=None,
                        help="usa un archivio tools.zip locale invece di scaricarlo (verificato via sha256)")
    parser.add_argument("--with-dinov2", action="store_true",
                        help="scarica anche i pesi DINOv2 legacy (backbone dinov2, ~740 MB)")
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
        tools_zip=args.tools_zip.resolve() if args.tools_zip else None,
        with_dinov2=args.with_dinov2,
        use_system_python=args.use_system_python,
    )
    ok = run_steps(ctx, steps, only)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
