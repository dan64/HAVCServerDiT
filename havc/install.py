"""`havc-install` — idempotent, convergent bootstrap of the server Python stack.

Guiding principle: "install = update from an empty state". Every step checks
first and skips what is already in place (see installer/PHASE0_SPEC.md §4).

Examples:
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
PIP_MIN = (24, 0)  # below this threshold the `pip` step upgrades pip

# External tools (x265/x264/mkvmerge) — archive pinned to Release v1.0.0;
# sha256 also verified against the official GitHub `digest` (2026-10-04).
TOOLS = {
    "name": "tools.zip",
    "url": "https://github.com/dan64/HAVCServerDiT/releases/download/v1.0.0/tools.zip",
    "sha256": "0a17002e1bb8964d81ab892fdcf250c760764a71b3d5990d3f7865b38765aef5",
}

# NVEncC (rigaya's GPU encoder) — "flat" package (NVEncC64.exe + DLLs in the
# zip root): extracted into <install>\tools\NVEncC\. Same tag as TOOLS.
NVENC = {
    "name": "NVEncC_9.17_x64.zip",
    "url": "https://github.com/dan64/HAVCServerDiT/releases/download/v1.0.0/NVEncC_9.17_x64.zip",
    "sha256": "81111c82b954e582f6c4b59102537af61e7deb22c87c9d000855ff8782b51624",
    "size": 105481170,
}

# Vendored ComfyUI runtime (comfy_bridge) — no longer part of the wheel
# (2026-10-05): it ships as a pinned zip, published as a release asset and
# extracted at the install root (<install>\comfy_bridge), where both the
# runtime imports and the model paths resolve consistently. Extracted by the
# `comfy-bridge` step; existing `models/` files are preserved on update.
COMFY_BRIDGE = {
    "name": "comfy_bridge_v0.30.zip",
    "url": "https://github.com/dan64/HAVCServerDiT/releases/download/v0.1.8/comfy_bridge_v0.30.zip",
    "sha256": "294311d0ca6b0b373bef64ea691429f14eba7252314ab58693234d0d4b4b7736",
    "size": 10557227,
}

# cmnet2 assets (plugins + weights) — pinned; sha256 also verified against
# the official GitHub `digest`s (2026-10-04). DINOv3 weights from cmnet2
# release v1.3.0 (NOT v1.2.0: the link in the READMEs pointed to a missing
# asset) and v1.1.0; plugins from vs-cmnet2 release v1.0.0.
CMNET2_PLUGINS = {
    "name": "plugins_win.zip",
    "url": "https://github.com/dan64/vs-cmnet2/releases/download/v1.0.0/plugins_win.zip",
    "sha256": "3fa5117519e0d49211c90d496c65905a036c0a364e7b2b1addc00ca38d9bf256",
    "size": 31056312,
}

# (dest is relative to the vscmnet2 package folder; extract_root=None
#  means "single file to copy", otherwise a zip to extract)
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

# Default model seeded into the GUI settings when the value is missing: the
# user-facing name from the GUI model list (the launcher argument mapping the
# same model in HAVC-Server.cmd is `qwen21`; `longcat3` maps longcat-gguf).
# The manager passes --default-model: below the RAM threshold of the nominal
# default (qwen21-viggle) it seeds the lighter longcat-gguf (Q3).
DEFAULT_MODEL_NAME = "qwen21-viggle"

# GUI precision paired with a non-viggle default model (seeded/wired only
# when absent; qwen21-viggle ignores the precision).
DEFAULT_MODEL_PRECISION = {"longcat-gguf": "q3"}

# Launchers written into the install folder (default front-end = GUI).
# ASCII content; lines are rewritten with CRLF on save (.cmd files with
# LF-only line endings can be misparsed by cmd.exe).
LAUNCHERS = {
    "HAVC.cmd": r"""@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%venv\Scripts\python.exe"
rem The GUI starts the managed server with a bare "python": put the venv first.
set "PATH=%HERE%venv\Scripts;%PATH%"
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
rem Anchor the working directory: `-m dit_rpc_server` imports comfy_bridge
rem from the install root (root copy).
cd /d "%HERE%"
set "WHICH=%~1"
if "%WHICH%"=="" set "WHICH=int4"
set "CFG="
if /i "%WHICH%"=="int4"    set "CFG=qwen_nunchaku_int4.json"
if /i "%WHICH%"=="fp4"     set "CFG=qwen_nunchaku_fp4.json"
if /i "%WHICH%"=="q3"      set "CFG=qwen_gguf_q3.json"
if /i "%WHICH%"=="q4"      set "CFG=qwen_gguf_q4.json"
if /i "%WHICH%"=="longcat"  set "CFG=longcat_gguf_q4.json"
if /i "%WHICH%"=="longcat3" set "CFG=longcat_gguf_q3.json"
if /i "%WHICH%"=="qwen21"   set "CFG=qwen21_viggle.json"
if "%CFG%"=="" (
    echo [ERROR] Unknown model "%WHICH%". Available: int4 fp4 q3 q4 longcat longcat3 qwen21
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
    "start_server.cmd": r"""@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] HAVC environment not found under "%HERE%".
    echo         Run the installer first, or check that the folder is complete.
    pause
    exit /b 1
)
rem HAVC DiT Server launcher for the GUI "External console" mode and manual use
rem (same argument names as the historical start_server.cmd).
set "WHICH=%~1"
if "%WHICH%"=="" set "WHICH=q4"
set "CFG="
if /i "%WHICH%"=="fp4"        set "CFG=qwen_nunchaku_fp4.json"
if /i "%WHICH%"=="int4"       set "CFG=qwen_nunchaku_int4.json"
if /i "%WHICH%"=="q3"         set "CFG=qwen_gguf_q3.json"
if /i "%WHICH%"=="q4"         set "CFG=qwen_gguf_q4.json"
if /i "%WHICH%"=="q5"         set "CFG=qwen_gguf_q5.json"
if /i "%WHICH%"=="q6"         set "CFG=qwen_gguf_q6.json"
if /i "%WHICH%"=="q8"         set "CFG=qwen_gguf_q8.json"
if /i "%WHICH%"=="longcat"    set "CFG=longcat_gguf_q4.json"
if /i "%WHICH%"=="longcat-q3" set "CFG=longcat_gguf_q3.json"
if /i "%WHICH%"=="longcat-q4" set "CFG=longcat_gguf_q4.json"
if /i "%WHICH%"=="longcat-q5" set "CFG=longcat_gguf_q5.json"
if /i "%WHICH%"=="longcat-q6" set "CFG=longcat_gguf_q6.json"
if /i "%WHICH%"=="longcat-q8" set "CFG=longcat_gguf_q8.json"
if "%CFG%"=="" (
    echo [ERROR] Unknown model "%WHICH%". Available: fp4 int4 q3 q4 q5 q6 q8 longcat longcat-q3 longcat-q4 longcat-q5 longcat-q6 longcat-q8
    pause
    exit /b 1
)
echo Starting HAVC DiT Server (%WHICH%) ...
rem strip the trailing backslash: a quoted path ending in \ would swallow the
rem closing quote and merge the rest of the command line into the argument.
"%PY%" -u "%HERE%dit_rpc_server.py" --host 127.0.0.1 --port 8765 --module-dir "%HERE:~0,-1%" --load-pipeline --pipeline-config "%HERE%config\%CFG%" --logfile "%HERE%dit_server.log"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server exited with code %errorlevel%.
    pause
)
endlocal
""",
    "run_server_qwen21.cmd": r"""@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] HAVC environment not found under "%HERE%".
    echo         Run the installer first, or check that the folder is complete.
    pause
    exit /b 1
)
rem HAVC DiT Server launcher for qwen21-viggle (single config, no argument).
echo Starting HAVC DiT Server (qwen21-viggle) ...
rem strip the trailing backslash: a quoted path ending in \ would swallow the
rem closing quote and merge the rest of the command line into the argument.
"%PY%" -u "%HERE%dit_rpc_server.py" --host 127.0.0.1 --port 8765 --module-dir "%HERE:~0,-1%" --load-pipeline --pipeline-config "%HERE%config\qwen21_viggle.json" --logfile "%HERE%dit_server.log"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server exited with code %errorlevel%.
    pause
)
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
    comfy_zip: Optional[Path] = None
    default_model: str = DEFAULT_MODEL_NAME
    with_dinov2: bool = False
    use_system_python: bool = False
    update_configs: bool = False

    @property
    def env_dir(self) -> Path:
        """The installation venv (created from the provisioned runtime)."""
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

    @property
    def gui_venv_dir(self) -> Path:
        """The `.venv` alias the HAVC GUI probes before starting its server.

        The GUI looks for `<server_dir>\\.venv\\Scripts\\python.exe` and
        falls back to a bare `python` when missing (dev layout), which can
        resolve to an interpreter without the venv packages. The bootstrap
        keeps this junction in place so the GUI always finds the venv
        (issue found on 2026-10-05: the managed server crashed with
        ModuleNotFoundError after a non-standard launch context).
        """
        return self.install_dir / ".venv"

    def gui_venv_link_ok(self) -> bool:
        """True when the GUI venv probe resolves (or the alias is not needed)."""
        if os.name != "nt":
            return True
        return (self.gui_venv_dir / "Scripts" / "python.exe").is_file()

    def ensure_gui_venv_link(self) -> str:
        """Create `<install>\\.venv` as a junction to the real venv.

        Junctions need no admin rights; where the filesystem has no reparse
        support (FAT/exFAT) creation fails and the HAVC launchers' PATH line
        remains the fallback. Returns a short outcome string for the step.
        """
        if os.name != "nt":
            return "not needed on this platform"
        if self.gui_venv_link_ok():
            return "already present"
        if self.dry_run:
            self.progress.event(
                "log", level="dry-run",
                message=f"[dry-run] mklink /J {self.gui_venv_dir} -> {self.env_dir}",
            )
            return "dry-run"
        proc = self.run(["cmd", "/c", "mklink", "/J",
                         str(self.gui_venv_dir), str(self.env_dir)],
                        check=False)
        if proc.returncode == 0 and self.gui_venv_link_ok():
            return "created"
        note = " (path exists but is not a usable venv)" if self.gui_venv_dir.exists() else ""
        self.progress.event(
            "log", level="err",
            message=(f"could not create the GUI alias {self.gui_venv_dir}{note}: the HAVC "
                     "GUI will fall back to a bare `python`; use the HAVC launchers, "
                     "which put the venv first on PATH"),
        )
        return "not created"

    def child_cwd(self) -> str:
        """Neutral CWD for child processes.

        Prevents the bootstrap CWD (e.g. a repo checkout with
        `havc.egg-info`) from shadowing the venv packages in metadata
        queries and in the `havc.doctor` import — bug found on 2026-10-04
        with the end-to-end test on the test folder.
        """
        return str(self.install_dir if self.install_dir.is_dir()
                   else Path(tempfile.gettempdir()))

    def env_python(self) -> Optional[Path]:
        """Interpreter used to create the venv: provisioned runtime, otherwise --python/system 3.12."""
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
                    detail = f" — last line: {tail[-1]}"
            raise BootstrapError(f"command failed (exit {proc.returncode}): {pretty}{detail}")
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
                problems.append(f"{name} missing")
            elif have != want:
                problems.append(f"{name}: expected {want}, found {have}")
        return problems


@dataclasses.dataclass
class Step:
    id: str
    title: str
    hint: str
    check: Callable[[Ctx], Optional[str]]  # None = must run; str = skip reason
    run: Callable[[Ctx], Optional[str]]    # optional detail for step_ok


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def find_python312() -> Optional[Path]:
    """Python 3.12 interpreter to create the venv: the current one, `py -3.12`, or python3.12."""
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
    """'patched' | 'original' | 'unknown' | None (= not determinable)."""
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
    """First wheel matching the pattern in --assets-dir."""
    if ctx.assets_dir is None:
        return None
    wheels = sorted(ctx.assets_dir.glob(pattern))
    return wheels[0] if wheels else None


def find_diffusers_wheel(ctx: Ctx) -> Optional[Path]:
    return find_asset_wheel(ctx, "diffusers-*.whl")


def vscmnet2_dir(ctx: Ctx) -> Optional[Path]:
    """vscmnet2 package folder in the venv (None if not installed).

    Uses `find_spec` without executing the package (no torch import).
    """
    if not ctx.venv_exists():
        return None
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
    """Obtain a pinned asset — local file, cache or download — always with
    sha256 verification."""
    if local is not None:
        if not local.is_file():
            raise BootstrapError(f"local archive not found: {local}")
        digest = sha256_of(local)
        if digest != asset["sha256"]:
            raise BootstrapError(
                f"{local.name} sha256 mismatch: {digest} != {asset['sha256']}",
                "the local file differs from the pinned asset")
        return local
    cached = ctx.cache_dir / asset["name"]
    if cached.is_file() and sha256_of(cached) == asset["sha256"]:
        ctx.progress.event("log", level="out",
                           message=f"using cached archive: {cached}")
        return cached
    ctx.progress.event("log", level="out", message=f"downloading: {asset['url']}")
    try:
        download_archive(asset["url"], cached, progress=ctx.progress)
    except Exception as exc:
        raise BootstrapError(f"download failed ({asset['name']}): {exc}",
                             "check your connection; retry")
    digest = sha256_of(cached)
    if digest != asset["sha256"]:
        raise BootstrapError(
            f"sha256 mismatch for {asset['name']}: {digest} != {asset['sha256']}",
            "re-download the archive; if it persists, the source file has changed")
    return cached


def staged_asset(ctx: Ctx, asset: dict, local: Optional[Path] = None) -> Path:
    """Obtain a pinned asset, preferring `local`, then a copy staged in
    `--assets-dir` (as delivered by the release manifest), then cache/download."""
    if local is None and ctx.assets_dir is not None:
        candidate = ctx.assets_dir / asset["name"]
        if candidate.is_file():
            local = candidate
    return cached_download(ctx, asset, local=local)


# ---------------------------------------------------------------------------
# GUI settings wiring
#
# Fill empty/absent managed values in gui_cmnet2_settings.json (rules: only
# empty/absent values are filled in; user values are never overwritten).
# ---------------------------------------------------------------------------

def wire_gui_settings(ctx: Ctx, settings_path: Path) -> int:
    """Fill empty/absent managed values in gui_cmnet2_settings.json
    (default `model_name`/`model_precision`). Returns 1 if changed."""
    if not settings_path.is_file():
        return 0
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    changed = False
    if not data.get("model_name"):
        data["model_name"] = ctx.default_model
        precision = DEFAULT_MODEL_PRECISION.get(ctx.default_model)
        if precision and not data.get("model_precision"):
            data["model_precision"] = precision
        changed = True
    if not changed:
        return 0
    with settings_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=4) + "\n")
    return 1


# ---------------------------------------------------------------------------
# Steps
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
                f"the bootstrap requires Python >= 3.9 (found {sys.version.split()[0]})"
            )
        if not req_dir.is_dir():
            raise BootstrapError(
                f"lockfile not found: {req_dir}",
                "run from the project checkout or reinstall the `havc` wheel",
            )
        note = "" if sys.version_info[:2] == (3, 12) else \
            " (the venv will use the provisioned 3.12 runtime)"
        return f"host: {sys.version.split()[0]}{note}"

    # -- 2. runtime (provisioned Python) ----------------------------------
    def runtime_check(c: Ctx) -> Optional[str]:
        if c.use_system_python:
            return "using the system Python (--use-system-python)"
        found = probe_version(c.runtime_python)
        if found == RUNTIME["python"]:
            return f"runtime Python {found} already present"
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
                raise BootstrapError(f"runtime archive not found: {c.runtime_zip}")
            archive = c.runtime_zip
        else:
            cached = c.cache_dir / RUNTIME["name"]
            if cached.is_file() and sha256_of(cached) == RUNTIME["sha256"]:
                archive = cached
                c.progress.event("log", level="out",
                                 message=f"using cached archive: {cached}")
            else:
                c.progress.event("log", level="out",
                                 message=f"downloading the runtime: {RUNTIME['url']}")
                try:
                    download_archive(RUNTIME["url"], cached, progress=c.progress)
                except Exception as exc:
                    raise BootstrapError(
                        f"runtime download failed: {exc}",
                        "check your connection; or use --runtime-zip with a local archive",
                    )
                archive = cached
        digest = sha256_of(archive)
        if digest != RUNTIME["sha256"]:
            raise BootstrapError(
                f"runtime sha256 mismatch: {digest} != {RUNTIME['sha256']}",
                "re-download the archive; if it persists, the source file has changed",
            )
        target = c.runtime_dir / "python"
        if target.exists():
            shutil.rmtree(target)
        c.progress.event("log", level="out", message=f"extracting into {c.runtime_dir} …")
        extract_archive(archive, c.runtime_dir)
        found = probe_version(c.runtime_python)
        if found != RUNTIME["python"]:
            raise BootstrapError(
                f"unexpected runtime after extraction: {found!r} (expected {RUNTIME['python']})"
            )
        return f"runtime Python {found} in {c.runtime_dir}"

    # -- 3. venv -----------------------------------------------------------
    def venv_check(c: Ctx) -> Optional[str]:
        if not c.venv_exists():
            return None
        if os.name == "nt" and not c.gui_venv_link_ok():
            return None  # venv present, but the GUI `.venv` alias is missing
        return "venv already present"

    def venv_run(c: Ctx) -> str:
        if not c.venv_exists():
            base = c.env_python()
            if base is None:
                raise BootstrapError(
                    "no usable Python to create the venv",
                    "enable the provisioned runtime (default) or pass --python <3.12>",
                )
            c.run([base, "-m", "venv", str(c.env_dir)])
            detail = f"{c.env_dir} (from {base})"
        else:
            detail = f"{c.env_dir} (existing)"
        if c.ensure_gui_venv_link() == "created":
            detail += "; GUI `.venv` alias created"
        return detail

    # -- 4. pip ------------------------------------------------------------
    def pip_check(c: Ctx) -> Optional[str]:
        version = pip_version(c)
        if version is not None and version >= PIP_MIN:
            return f"pip {version[0]}.{version[1]} already up to date"
        return None

    def pip_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        return "pip upgraded"

    # -- 5. torch ----------------------------------------------------------
    def torch_check(c: Ctx) -> Optional[str]:
        return "torch already at the pinned version" if not c.unmet(torch_pins) else None

    def torch_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", torch_txt,
               "--index-url", TORCH_INDEX])
        return "PyTorch 2.10.0+cu130"

    # -- 6. nunchaku -------------------------------------------------------
    def nunchaku_check(c: Ctx) -> Optional[str]:
        want = lock.get("nunchaku")
        if want and c.dist_version("nunchaku") == want:
            return f"nunchaku {want} already installed"
        return None

    def nunchaku_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", nunchaku_txt])
        return str(lock.get("nunchaku", "nunchaku"))

    # -- 7. torch-repin ----------------------------------------------------
    def repin_check(c: Ctx) -> Optional[str]:
        return "torch unchanged after nunchaku" if not c.unmet(torch_pins) else None

    def repin_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", torch_txt,
               "--index-url", TORCH_INDEX, "--force-reinstall"])
        return "re-pin torch 2.10.0+cu130"

    # -- 8. patch ----------------------------------------------------------
    def patch_check(c: Ctx) -> Optional[str]:
        if c.dist_version("nunchaku") is None:
            return "nunchaku not installed"
        if patch_state(c) == "patched":
            return "patch already applied"
        return None

    def patch_run(c: Ctx) -> str:
        script = paths.find_patch_script()
        if script is None:
            raise BootstrapError("patch_nunchaku.py not found in the wheel/checkout")
        c.run([c.venv_python, str(script)])
        return "nunchaku patch applied"

    # -- 9. diffusers ------------------------------------------------------
    def diffusers_check(c: Ctx) -> Optional[str]:
        want = lock.get("diffusers")
        if want and c.dist_version("diffusers") == want:
            return f"diffusers {want} already installed"
        return None

    def diffusers_run(c: Ctx) -> str:
        wheel = find_diffusers_wheel(c)
        if wheel is None:
            raise BootstrapError(
                "diffusers wheel not found",
                "pass --assets-dir <folder with the repo wheels> (e.g. packages/)",
            )
        c.run([c.venv_python, "-m", "pip", "install", str(wheel)])
        return wheel.name

    # -- 10. deps ----------------------------------------------------------
    def deps_check(c: Ctx) -> Optional[str]:
        return "core dependencies already in place" if not c.unmet(core_pins) else None

    def deps_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", core_txt])
        return "core dependencies"

    # -- 11. project wheel -------------------------------------------
    def wheel_check(c: Ctx) -> Optional[str]:
        if c.wheel is None:
            return "no project wheel provided"
        if c.dist_version("havc") == __version__:
            return f"havc {__version__} already installed"
        return None

    def wheel_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "--force-reinstall",
               "--no-deps", str(c.wheel)])
        return c.wheel.name

    # -- 12. server entry points -------------------------------------------
    def server_entry_files(c: Ctx) -> dict[str, Path]:
        """Server entry points as installed by the wheel (venv top level)."""
        if os.name == "nt":
            site = c.env_dir / "Lib" / "site-packages"
        else:
            matches = sorted((c.env_dir / "lib").glob("python3*/site-packages"))
            site = matches[-1] if matches else c.env_dir / "lib" / "site-packages"
        return {name: site / name
                for name in ("dit_rpc_server.py", "dit_colorize_main.py")}

    def server_check(c: Ctx) -> Optional[str]:
        for name, source in server_entry_files(c).items():
            target = c.install_dir / name
            if not source.is_file():
                return None
            if not target.is_file() or target.read_bytes() != source.read_bytes():
                return None
        return "server entry points up to date"

    def server_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] server entry points -> {c.install_dir}")
            return "dry-run"
        copied = []
        for name, source in server_entry_files(c).items():
            if not source.is_file():
                raise BootstrapError(
                    f"{name} missing in the venv",
                    "run the `wheel` step first")
            target = c.install_dir / name
            data = source.read_bytes()
            if not target.is_file() or target.read_bytes() != data:
                target.write_bytes(data)
                copied.append(name)
        return ", ".join(copied) if copied else "already up to date"

    # -- 13. comfy-bridge --------------------------------------------------
    def comfy_bridge_check(c: Ctx) -> Optional[str]:
        root = c.install_dir / "comfy_bridge"
        if not (root / "folder_paths.py").is_file():
            return None
        try:
            if (root / ".source").read_text(encoding="utf-8").strip() != COMFY_BRIDGE["name"]:
                return None
        except OSError:
            return None
        return "comfy_bridge already extracted"

    def comfy_bridge_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] comfy_bridge ({COMFY_BRIDGE['name']}) -> {c.install_dir / 'comfy_bridge'}")
            return "dry-run"
        archive = staged_asset(c, COMFY_BRIDGE, c.comfy_zip)
        extract_archive(archive, c.install_dir, required_root="comfy_bridge")
        (c.install_dir / "comfy_bridge" / ".source").write_text(
            COMFY_BRIDGE["name"] + "\n", encoding="utf-8")
        return COMFY_BRIDGE["name"]

    # -- 14. configs -------------------------------------------------------
    def configs_diff(c: Ctx) -> list[str]:
        """Packaged configs whose installed copy exists and differs (bytes)."""
        src = paths.configs_dir()
        if not src.is_dir():
            return []
        dst = c.install_dir / "config"
        different = []
        for path in sorted(src.glob("*.json")):
            target = dst / path.name
            if target.is_file() and target.read_bytes() != path.read_bytes():
                different.append(path.name)
        return different

    def configs_check(c: Ctx) -> Optional[str]:
        src = paths.configs_dir()
        if not src.is_dir():
            return None
        dst = c.install_dir / "config"
        missing = [p.name for p in src.glob("*.json") if not (dst / p.name).exists()]
        if missing:
            return None
        different = configs_diff(c)
        if different and c.update_configs:
            return None
        if different:
            shown = ", ".join(different[:3]) + ("..." if len(different) > 3 else "")
            return (f"configs already present ({len(different)} differ and are kept: "
                    f"{shown}; pass --update-configs to replace them)")
        return "configs already present"

    def configs_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] copy configs -> {c.install_dir / 'config'}")
            return "dry-run"
        src = paths.configs_dir()
        if not src.is_dir():
            raise BootstrapError(f"source configs not found: {src}",
                                 "reinstall the havc wheel")
        dst = c.install_dir / "config"
        dst.mkdir(parents=True, exist_ok=True)
        copied = updated = kept = 0
        for path in sorted(src.glob("*.json")):
            target = dst / path.name
            if not target.exists():
                shutil.copy2(path, target)
                copied += 1
            elif target.read_bytes() != path.read_bytes():
                if c.update_configs:
                    # previous file kept next to it, then replaced
                    shutil.copy2(target, target.with_name(target.name + ".bak"))
                    shutil.copy2(path, target)
                    updated += 1
                else:
                    kept += 1
        parts = []
        if copied:
            parts.append(f"{copied} copied")
        if updated:
            parts.append(f"{updated} updated (previous kept as .bak)")
        if kept:
            parts.append(f"{kept} differ and were kept (use --update-configs)")
        return ", ".join(parts) if parts else "no config changes"

    # -- 15. gui -----------------------------------------------------------
    def gui_files() -> Optional[dict[str, Path]]:
        """Map relative path -> source for the managed GUI files."""
        src = paths.gui_source_dir()
        if src is None:
            return None
        files = {
            "CMNET2_colorize_client_GUI.py": src / "CMNET2_colorize_client_GUI.py",
            "load_image_DtD_GUI.py": src / "load_image_DtD_GUI.py",
        }
        for path in sorted((src / "scripts").glob("*.vpy")):
            files[f"scripts/{path.name}"] = path
        samples = src / "samples"
        if samples.is_dir():
            for path in sorted(samples.glob("*")):
                if path.is_file():  # sample clips + their .vpy scripts
                    files[f"samples/{path.name}"] = path
        return files

    def gui_check(c: Ctx) -> Optional[str]:
        files = gui_files()
        if files is None:
            return None
        dst_root = c.install_dir / "gui"
        for rel, src_path in files.items():
            target = dst_root / rel
            if not target.is_file() or target.read_bytes() != src_path.read_bytes():
                return None
        return "GUI files already up to date"

    def gui_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] copy GUI -> {c.install_dir / 'gui'}")
            return "dry-run"
        files = gui_files()
        if files is None:
            raise BootstrapError(
                "GUI files not found (neither in the package nor in the checkout)",
                "reinstall the havc wheel or run from the repo checkout")
        dst_root = c.install_dir / "gui"
        for rel, src_path in files.items():
            target = dst_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, target)
        return f"{len(files)} file (GUI + scripts + samples)"

    # -- 16. gui-deps ------------------------------------------------------
    def gui_deps_check(c: Ctx) -> Optional[str]:
        return "GUI dependencies already in place" if not c.unmet(gui_pins) else None

    def gui_deps_run(c: Ctx) -> str:
        c.run([c.venv_python, "-m", "pip", "install", "-r", gui_txt])
        for pattern, label in (("vscmnet2-*.whl", "vscmnet2"),
                               ("spatial_correlation_sampler-*.whl",
                                "spatial_correlation_sampler")):
            wheel = find_asset_wheel(c, pattern)
            if wheel is None:
                raise BootstrapError(
                    f"{label} wheel not found",
                    "pass --assets-dir with the repo wheels (e.g. packages/)")
            c.run([c.venv_python, "-m", "pip", "install", str(wheel)])
        return "GUI + vscmnet2 + spatial_correlation_sampler"

    # -- 17. cmnet2-plugins ------------------------------------------------
    def cmnet2_plugins_check(c: Ctx) -> Optional[str]:
        pkg = vscmnet2_dir(c)
        if pkg is None:
            return "vscmnet2 not installed"
        if (pkg / "plugins" / "SourceFilter" / "LSmashSource" / "LSMASHSource.dll").is_file():
            return "plugins already present"
        return None

    def cmnet2_plugins_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message="[dry-run] vs-cmnet2 plugins -> vscmnet2/plugins")
            return "dry-run"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            raise BootstrapError("vscmnet2 not installed in the venv",
                                 "run the `gui-deps` step first")
        archive = cached_download(c, CMNET2_PLUGINS)
        extract_archive(archive, pkg, required_root="plugins")
        return "plugins in vscmnet2/plugins"

    # -- 18. cmnet2-weights ------------------------------------------------
    def cmnet2_weights_check(c: Ctx) -> Optional[str]:
        pkg = vscmnet2_dir(c)
        if pkg is None:
            return "vscmnet2 not installed"
        checkpoint = pkg / "weights" / CMNET2_DINOV3[0]["name"]
        vitb16 = pkg / "weights" / "dinov3-vitb16" / "model.safetensors"
        if (checkpoint.is_file() and checkpoint.stat().st_size == CMNET2_DINOV3[0]["size"]
                and vitb16.is_file()):
            return "DINOv3 weights already present"
        return None

    def cmnet2_weights_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message="[dry-run] DINOv3 weights -> vscmnet2/weights")
            return "dry-run"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            raise BootstrapError("vscmnet2 not installed in the venv",
                                 "run the `gui-deps` step first")
        weights = pkg / "weights"
        weights.mkdir(parents=True, exist_ok=True)
        done = []
        for asset in CMNET2_DINOV3:
            archive = cached_download(c, asset)
            if asset["extract_root"]:
                extract_archive(archive, weights, required_root=asset["extract_root"])
                done.append(f"{asset['name']} (extracted)")
            else:
                shutil.copy2(archive, weights / asset["name"])
                done.append(asset["name"])
        if not (weights / "dinov3-vitb16" / "model.safetensors").is_file():
            raise BootstrapError(
                "dinov3-vitb16/model.safetensors missing after extraction",
                "the archive may have an unexpected layout")
        return ", ".join(done)

    # -- 19. cmnet2-dinov2 -------------------------------------------------
    def cmnet2_dinov2_check(c: Ctx) -> Optional[str]:
        if not c.with_dinov2:
            return "not requested (--with-dinov2)"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            return "vscmnet2 not installed"
        missing = [a["name"] for a in CMNET2_DINOV2
                   if not (pkg / a["dest"] / a["name"]).is_file()]
        return "DINOv2 weights already present" if not missing else None

    def cmnet2_dinov2_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message="[dry-run] DINOv2 weights -> vscmnet2/weights + models/checkpoints")
            return "dry-run"
        pkg = vscmnet2_dir(c)
        if pkg is None:
            raise BootstrapError("vscmnet2 not installed in the venv",
                                 "run the `gui-deps` step first")
        for asset in CMNET2_DINOV2:
            dest_dir = pkg / asset["dest"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            archive = cached_download(c, asset)
            shutil.copy2(archive, dest_dir / asset["name"])
        return f"{len(CMNET2_DINOV2)} DINOv2 files (legacy)"

    # -- 20. tools ---------------------------------------------------------
    def tools_check(c: Ctx) -> Optional[str]:
        x265 = (c.install_dir / "tools" / "x265" / "x265.exe").is_file()
        nvenc = (c.install_dir / "tools" / "NVEncC" / "NVEncC64.exe").is_file()
        if x265 and nvenc:
            return "external tools already present"
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
                    "NVEncC64.exe missing after extraction",
                    "the archive may have an unexpected layout")
            done.append("NVEncC 9.17")
        return ", ".join(done) if done else "already present"

    # -- 21. gui-settings --------------------------------------------------
    def gui_settings_check(c: Ctx) -> Optional[str]:
        settings = c.install_dir / "gui" / "gui_cmnet2_settings.json"
        if not settings.is_file():
            return None
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "settings already present"
        if not data.get("model_name"):
            return None
        return "settings already present"

    def gui_settings_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] GUI settings -> {c.install_dir / 'gui'}")
            return "dry-run"
        gui_dir = c.install_dir / "gui"
        if not gui_dir.is_dir():
            raise BootstrapError("gui folder missing", "run the `gui` step first")
        path = gui_dir / "gui_cmnet2_settings.json"
        if path.is_file():
            wired = wire_gui_settings(c, path)
            return ("managed values wired in gui_cmnet2_settings.json" if wired
                    else "settings already present")
        settings = {
            "script_dir": str(gui_dir / "scripts"),
            "vspipe_path": str(c.venv_python.parent / "vspipe.exe"),
            "x265_path": str(c.install_dir / "tools" / "x265" / "x265.exe"),
            "mkv_path": str(c.install_dir / "tools" / "MKVToolNix" / "mkvmerge.exe"),
            "base_dir": str(c.install_dir / "work"),
            "fixv_base_dir": str(c.install_dir / "work"),
            "model_name": c.default_model,
        }
        precision = DEFAULT_MODEL_PRECISION.get(c.default_model)
        if precision:
            settings["model_precision"] = precision
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(settings, indent=4) + "\n")
        return "gui_cmnet2_settings.json created"

    # -- 22. launchers -----------------------------------------------------
    def launcher_files(c: Ctx) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        for name, content in LAUNCHERS.items():
            files[name] = content.replace("\n", "\r\n").encode("utf-8")
        return files

    def launchers_check(c: Ctx) -> Optional[str]:
        for name, data in launcher_files(c).items():
            path = c.install_dir / name
            if not path.is_file() or path.read_bytes() != data:
                return None
        return "launchers already up to date"

    def launchers_run(c: Ctx) -> str:
        if c.dry_run:
            c.progress.event("log", level="dry-run",
                             message=f"[dry-run] launcher -> {c.install_dir}")
            return "dry-run"
        for name, data in launcher_files(c).items():
            (c.install_dir / name).write_bytes(data)
        return ", ".join(LAUNCHERS)

    # -- 23. verify --------------------------------------------------------
    def verify_run(c: Ctx) -> str:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)  # no shadowing from the caller
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
                "`havc doctor --json` output not parseable",
                f"run manually: {c.venv_python} -m havc.doctor",
            )
        failed = [x["check"] for x in report.get("checks", []) if x["status"] == "fail"]
        if failed:
            raise BootstrapError(
                "havc doctor reports problems: " + ", ".join(failed),
                "see the doctor report",
            )
        return "doctor: all checks OK"

    return [
        Step("preflight", "Preliminary checks (host, lockfile)", "",
             lambda c: None, preflight_run),
        Step("runtime", "Runtime Python 3.12 (python-build-standalone)",
             "download/verify/extract the pinned archive",
             runtime_check, runtime_run),
        Step("venv", "Target virtualenv + GUI alias",
             "python -m venv from the runtime; junction `.venv` -> `venv` for the GUI",
             venv_check, venv_run),
        Step("pip", "pip upgrade", "pip install --upgrade pip",
             pip_check, pip_run),
        Step("torch", "PyTorch 2.10.0+cu130", "pip install -r requirements/torch.txt --index-url ...",
             torch_check, torch_run),
        Step("nunchaku", "Nunchaku 1.2.1 (wheel from GitHub)", "pip install -r requirements/nunchaku.txt",
             nunchaku_check, nunchaku_run),
        Step("torch-repin", "Re-pin torch (if nunchaku upgraded it)", "pip install --force-reinstall",
             repin_check, repin_run),
        Step("patch", "Nunchaku compatibility patch", "python patch_nunchaku.py",
             patch_check, patch_run),
        Step("diffusers", "diffusers 0.37.0.dev0 (local wheel)", "pip install packages/diffusers-*.whl",
             diffusers_check, diffusers_run),
        Step("deps", "Core dependencies", "pip install -r requirements/core.txt",
             deps_check, deps_run),
        Step("wheel", "Project wheel (havc)", "pip install --no-deps havc-*.whl",
             wheel_check, wheel_run),
        Step("server", "Server entry points in <install>",
             "dit_rpc_server.py + dit_colorize_main.py (copied from the venv, rewritten if different)",
             server_check, server_run),
        Step("comfy-bridge", "comfy_bridge in <install>",
             f"{COMFY_BRIDGE['name']} (pinned; models/ is preserved)",
             comfy_bridge_check, comfy_bridge_run),
        Step("configs", "Pipeline configs in <install>/config",
             "copy missing configs; --update-configs replaces differing ones (.bak kept)",
             configs_check, configs_run),
        Step("gui", "GUI files in <install>/gui",
             "GUI + scripts + samples (updated if different)",
             gui_check, gui_run),
        Step("gui-deps", "GUI dependencies (FreeSimpleGUI, tkinterdnd2, VapourSynth, vscmnet2, SCS)",
             "pip install -r requirements/gui.txt + local wheels",
             gui_deps_check, gui_deps_run),
        Step("cmnet2-plugins", "vs-cmnet2 plugins in vscmnet2/plugins",
             "plugins_win.zip (vs-cmnet2 v1.0.0, sha256)",
             cmnet2_plugins_check, cmnet2_plugins_run),
        Step("cmnet2-weights", "DINOv3 weights for vs-cmnet2",
             "checkpoint (cmnet2 v1.3.0) + dinov3-vitb16.zip (v1.1.0)",
             cmnet2_weights_check, cmnet2_weights_run),
        Step("cmnet2-dinov2", "Legacy DINOv2 weights (optional)",
             "only with --with-dinov2",
             cmnet2_dinov2_check, cmnet2_dinov2_run),
        Step("tools", "External tools in <install>/tools",
             "tools.zip + NVEncC_9.17_x64.zip (Release v1.0.0) or --tools-zip",
             tools_check, tools_run),
        Step("gui-settings", "GUI settings (seeded/wired when missing)",
             "gui_cmnet2_settings.json: model_name/model_precision only if empty",
             gui_settings_check, gui_settings_run),
        Step("launchers", "Launcher in <install>",
             "HAVC.cmd/.vbs (GUI), HAVC-Server.cmd, HAVC-Doctor.cmd, start_server.cmd/run_server_qwen21.cmd (rewritten if different)",
             launchers_check, launchers_run),
        Step("verify", "Final verification (havc doctor)", "python -m havc.doctor",
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
    # Announce the plan up-front so the manager can show all step rows as
    # pending; skip reasons are computed on the fly by the loop below.
    ctx.progress.event("plan", steps=[
        {"id": s.id, "title": s.title, "hint": s.hint, "skip_reason": None}
        for s in selected
    ])
    stop = ctx.cache_dir / ".stop-request"
    if not ctx.dry_run:
        try:
            stop.unlink()
        except FileNotFoundError:
            pass
    for step in selected:
        if not ctx.dry_run and stop.is_file():
            ctx.progress.event("log", level="out",
                               message="stop requested: aborting after the previous step")
            ok = False
            break
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
        except Exception as exc:  # unexpected error: do not hide the type
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
        description="Idempotent bootstrap of the HAVC server stack "
                    "(install = update from an empty state).",
        epilog="Specification: installer/PHASE0_SPEC.md",
    )
    parser.add_argument("--install-dir", required=True, type=Path,
                        help="installation folder: runtime/, venv/, cache/ "
                             "(required; nothing is touched outside it)")
    parser.add_argument("--python", type=Path, default=None,
                        help="interpreter used to create the venv (default: provisioned runtime)")
    parser.add_argument("--runtime-zip", type=Path, default=None,
                        help="use a local runtime archive instead of downloading it (sha256 verified)")
    parser.add_argument("--tools-zip", type=Path, default=None,
                        help="use a local tools.zip archive instead of downloading it (sha256 verified)")
    parser.add_argument("--with-dinov2", action="store_true",
                        help="also download the legacy DINOv2 weights (dinov2 backbone, ~740 MB)")
    parser.add_argument("--update-configs", action="store_true",
                        help="replace pipeline configs that differ from the packaged ones "
                             "(the previous file is kept as <name>.json.bak); "
                             "default: only copy missing configs")
    parser.add_argument("--use-system-python", action="store_true",
                        help="skip runtime provisioning and use the system Python (development)")
    parser.add_argument("--assets-dir", type=Path, default=None,
                        help="folder with the local wheels (default: packages/ of the checkout)")
    parser.add_argument("--wheel", type=Path, default=None,
                        help="project wheel (havc-*.whl) to install")
    parser.add_argument("--comfy-zip", type=Path, default=None,
                        help="use a local comfy_bridge zip archive instead of downloading it "
                             "(sha256 verified)")
    parser.add_argument("--default-model", default=DEFAULT_MODEL_NAME,
                        help="GUI default model seeded/wired in the GUI settings "
                             f"when empty (default: {DEFAULT_MODEL_NAME}; "
                             "e.g. longcat-gguf seeds precision q3)")
    parser.add_argument("--only", default="",
                        help="run only these steps (comma-separated ids)")
    parser.add_argument("--plan", action="store_true",
                        help="show the plan without executing anything")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the commands without executing them")
    parser.add_argument("--json-progress", action="store_true",
                        help="JSON events on stdout (one line per event)")
    args = parser.parse_args(argv)
    force_utf8()

    progress = Progress(json_mode=args.json_progress)
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    steps = build_steps()
    ids = {s.id for s in steps}
    if only:
        unknown = only - ids
        if unknown:
            parser.error(f"unknown steps: {', '.join(sorted(unknown))} "
                         f"(valid: {', '.join(sorted(ids))})")

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
        comfy_zip=args.comfy_zip.resolve() if args.comfy_zip else None,
        default_model=args.default_model,
        with_dinov2=args.with_dinov2,
        use_system_python=args.use_system_python,
        update_configs=args.update_configs,
    )
    ok = run_steps(ctx, steps, only)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
