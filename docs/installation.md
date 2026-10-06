# Installation

Two ways to install HAVC: the **installer** (recommended) or the **manual setup** (advanced users / development).

## Installer (recommended)

Download **`HAVC-Setup-<version>.exe`** from the
[Releases page](https://github.com/dan64/HAVCServerDiT/releases) and run it.
The installer is a single self-contained file (no .NET runtime needed) and
sets up everything: the pinned Python runtime, the server stack, the GUI,
external tools and the vs-cmnet2 plugins/weights — model weights are fetched
on first use.

- Windows **SmartScreen** may warn because the exe is not code-signed:
  *Windows protected your PC* → **More info** → **Run anyway**; the sha256 is
  published in the release notes.
- The manager fetches its manifest from the latest release URL; for testing
  or offline use you can keep a `release.json` next to the exe, or pass
  `--release-tag vX`.
- Default install folder: `%LOCALAPPDATA%\HAVCServerDiT` (per-user, no admin).
  Model files live in `<install>\comfy_bridge\models` and are preserved by
  update/repair and by the uninstaller (which asks before deleting them).
- The manager (installed copy or the setup exe) offers *Open GUI*,
  *Start server*, *Check for updates*, *Repair* and *Uninstall*. Installed
  layouts also ship the launcher scripts — see
  [Windows launch script](usage.md#-windows-launch-script).

## Manual installation

For advanced users and development: clone the repository and run
`install.cmd`, or follow the steps below. Requires **Git** and **Python
3.12**.

## 🛠️ Installing Git and Python

Before setting up the project environment, make sure both Git and Python 3.12 are installed on your system.

### Git

**Windows**: download and install [Git for Windows](https://git-scm.com/download/win).
Accept the default options : in particular keep `core.autocrlf=true` (the default),
which ensures correct line endings for `.cmd` files.

**Linux**:

```bash
sudo apt install git        # Debian / Ubuntu
sudo dnf install git        # Fedora / RHEL
```

Verify: `git --version`

---

### Python 3.12

**Windows**: download the installer from [python.org/downloads](https://www.python.org/downloads/windows/).
During installation, check **"Add Python to PATH"** : without this, `python` will not be
recognized in the terminal.

**Linux**:

```bash
sudo apt install python3.12 python3.12-venv   # Debian / Ubuntu
sudo dnf install python3.12                   # Fedora / RHEL
```

Verify: `python --version` (Windows) or `python3.12 --version` (Linux)

---

## ⚙️ Environment Setup

### 1 : Clone the repository and create a virtual environment

Clone the repository with git : this ensures correct line endings for all files
(`.gitattributes` is applied automatically at checkout):

```bash
git clone https://github.com/dan64/HAVCServerDiT.git
cd HAVCServerDiT
```

Then create and activate the virtual environment inside the project directory:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

> **Windows quick-start**: once the venv is active you can run `install.cmd` to execute
> steps 2–6 automatically instead of running them one by one.

---

### 2 : Install PyTorch 2.10.0 + CUDA 13.0

Use the **stable** build for all GPU generations (RTX 30 / 40 / 50):

```bash
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130
```

Verify the installation:

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
# Expected: 2.10.0+cu130, True
```

---

### 3 : Install Nunchaku

> ⚠️ **Do NOT use `pip install nunchaku`** : that installs an unrelated package from PyPI
> with the same name that will fail with `ModuleNotFoundError: No module named 'nunchaku.models'`.

Install the correct MIT Han Lab build directly from the GitHub release:

```bash
# Windows / Python 3.12 / CUDA 13.0 / PyTorch 2.10
pip install https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu13.0torch2.10-cp312-cp312-win_amd64.whl
```

For other platforms or Python versions, browse the full list of available wheels on the
[Nunchaku releases page](https://github.com/nunchaku-ai/nunchaku/releases/tag/v1.2.1)
and replace the filename accordingly.

> **Nunchaku pulls `torch>=2.0` as a dependency (via `accelerate`) and may upgrade
> PyTorch to a newer version.** After installing Nunchaku, re-pin PyTorch:

```bash
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 --index-url https://download.pytorch.org/whl/cu130 --force-reinstall
```

Verify the correct package is installed :

```bash
pip show nunchaku
# Version: 1.2.1+cu13.0torch2.10
pip show torch
# Version: 2.10.0+cu130
```

### 4 : Patch Nunchaku

Nunchaku 1.2.1 contains a bug in its transformer forward pass: `txt_seq_lens` is always
`None` at the point where it is passed to `pos_embed`, causing a `ValueError` with
diffusers `>= 0.37.0.dev0`. The included `patch_nunchaku.py` fixes this by deriving
`max_txt_seq_len` directly from `encoder_hidden_states`:

```bash
python patch_nunchaku.py
```

On Windows you can also double-click `patch_nunchaku.cmd` or run it from a terminal:

```
patch_nunchaku.cmd            # apply the patch
patch_nunchaku.cmd --check    # check status without modifying files
patch_nunchaku.cmd --revert   # revert to original (.bak backup)
```

You can verify the patch status at any time:

```bash
python patch_nunchaku.py --check
```

And revert to the original if needed (a `.bak` backup is created automatically):

```bash
python patch_nunchaku.py --revert
```

---

### 5 : Install Diffusers

> ⚠️ **Do NOT install diffusers from GitHub (`pip install git+https://...`).**
> Nunchaku 1.2.1 requires exactly `0.37.0.dev0`. Later dev builds (≥ 0.39.0) changed
> the `QwenEmbedRope` API in a way that is incompatible even after the nunchaku patch.

A tested compatible wheel is published in the release assets.
Download it (or install it straight from the URL):

```bash
pip install https://github.com/dan64/HAVCServerDiT/releases/download/v1.0.0/diffusers-0.37.0.dev0-py3-none-any.whl
```

Verify:

```bash
python -c "import diffusers; print(diffusers.__version__)"
# Expected: 0.37.0.dev0
```

---

### 6 : Install remaining dependencies

Pin the versions to match the tested working environment:

```bash
pip install \
    transformers==4.57.6 \
    accelerate==1.12.0 \
    "huggingface_hub>=0.26.0" \
    "Pillow>=10.0.0" \
    scipy \
    av \
    torchsde \
    gguf \
    comfy-aimdo==0.5.5 \
    comfy-kitchen==0.2.35
```

> **Nunchaku users**: `diffusers` was already installed in step 5 as the compatible
> `0.37.0.dev0` wheel. Do NOT upgrade it  :  nunchaku 1.2.1 requires exactly that version.
> 
> `safetensors` is pulled automatically by diffusers.
> 
> `scipy`, `av`, and `torchsde` are required by the diffusers pipeline.
> `gguf`, `comfy-aimdo`, and `comfy-kitchen` are required by the GGUF backends
> (`gguf-qwen`/`longcat-gguf`) and by `qwen21-viggle`. The pinned versions
> here (`0.5.5`/`0.2.35`) are required specifically for `qwen21-viggle` —
> exact pins, not just a minimum, to avoid drifting to an untested newer
> build of these compiled packages.

## 📦 Quick Update (existing installation)

> If you already have the `.venv` with CUDA 13.0 and just need to update
> the project to the latest version, follow these steps:

> **Shortcut**: `quick_update.cmd` automates all of the steps below
> (including the `comfy-kitchen`/`comfy-aimdo` pin) — activate the `.venv`
> first, then double-click it or run it from a terminal. The manual steps
> are documented here for reference and for non-Windows setups.

```powershell
# 1) Pull the latest code
git pull

# 2) Activate the virtual environment
.venv\Scripts\activate

# 3) Install / update the GUI dependencies (if new packages were added)
pip install -r GUI\requirements.txt

# 4) Update vscmnet2 (if a newer release is available)
pip install https://github.com/dan64/vs-cmnet2/releases/download/v1.2.1/vscmnet2-1.2.1-py3-none-any.whl

# 5) Re-apply the Nunchaku patch
python patch_nunchaku.py

# 6) Required for qwen21-viggle (see What's New, 2026-09-26): pin
#    comfy-kitchen and comfy-aimdo to the tested versions — install.cmd
#    only sets these for a fresh install, an existing .venv needs this
#    explicitly
pip install comfy-kitchen==0.2.35
pip install comfy-aimdo==0.5.5

# 7) Verify everything is up-to-date
pip show torch          # Expected: 2.10.0+cu130
pip show nunchaku       # Expected: 1.2.1+cu13.0torch2.10
pip show comfy-kitchen  # Expected: 0.2.35
pip show comfy-aimdo    # Expected: 0.5.5
```

> **Note**: steps 4–5 are only needed if `vscmnet2` or `patch_nunchaku.py`
> have changed. Step 6 is only needed to use `qwen21-viggle` — the other
> three backends work with the older `comfy-kitchen`/`comfy-aimdo` versions.
> Check `git log --oneline -5` to see what was updated.

---

## 🔄 Upgrading from CUDA 12.8 to 13.0

> If you already created the `.venv` with a previous version (CUDA 12.8,
> PyTorch 2.9.1, Nunchaku cu12.8torch2.9), upgrade to get these benefits:

| Improvement            | Before (12.8)                           | After (13.0)                                       |
| ---------------------- | --------------------------------------- | -------------------------------------------------- |
| **CUDA allocator**     | `native` (slower reallocation)          | `cudaMallocAsync` (async, ~10 % faster memory ops) |
| **comfy-kitchen CUDA** | `disabled: True` (fallback to eager)    | `disabled: False` (native dequantization kernels)  |
| **Warning**            | `You need pytorch with cu130 or higher` | gone (build matches Nunchaku)                      |

**Upgrade steps:**

```bash
# 1) Deactivate and reactivate the venv to ensure a clean shell
deactivate
.venv\Scripts\activate

# 2) Upgrade PyTorch to 2.10 + CUDA 13.0
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 --index-url https://download.pytorch.org/whl/cu130 --force-reinstall

# 3) Upgrade Nunchaku (CUDA 13.0 + PyTorch 2.10 build)
pip install https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu13.0torch2.10-cp312-cp312-win_amd64.whl --force-reinstall

# 4) Re-pin PyTorch (Nunchaku may have upgraded it to 2.12)
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 --index-url https://download.pytorch.org/whl/cu130 --force-reinstall

# 5) Re-apply the Nunchaku patch
python patch_nunchaku.py

# 6) Verify
pip show torch       # Expected: 2.10.0+cu130
pip show nunchaku    # Expected: 1.2.1+cu13.0torch2.10
```

---

## 📂 Project Structure

```
dit-colorize-rpc/
├── dit_rpc_server.py            # XML-RPC server (entry point)
├── dit_colorize_main.py         # Colorization pipeline and image utilities
├── dit_client_example.py        # Example RPC client : single frame
├── dit_client_pair_example.py   # Example RPC client : paired inference
├── patch_nunchaku.py            # Compatibility patch for nunchaku 1.2.1
├── config/                      # Pipeline configs (nunchaku FP4/INT4, gguf/longcat Q3–Q8, qwen21-viggle)
├── comfy_bridge/                # Self-contained ComfyUI runtime (gguf-qwen/longcat-gguf/qwen21-viggle)
├── install.cmd                  # Windows automated installer
├── start_server.cmd             # Windows launcher : server (nunchaku/gguf/longcat)
├── run_server_longcat.cmd       # Windows launcher : LongCat server
├── run_server_qwen21.cmd        # Windows launcher : qwen21-viggle server
├── run_client_example.cmd       # Windows launcher : single frame example
├── run_client_pair_example.cmd  # Windows launcher : paired inference example
├── patch_nunchaku.cmd           # Windows launcher : nunchaku patch
├── assets/
│   ├── santa_bw.png             # Sample B&W image (single frame test)
│   ├── sample1_bw.jpg           # Sample B&W image 1 (paired inference test)
│   └── sample2_bw.jpg           # Sample B&W image 2 (paired inference test)
└── README.md
```
