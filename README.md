# DiT Colorize RPC Server

An XML-RPC server that exposes a GPU-accelerated colorization pipeline for black-and-white images and video frames.
Two backends, one API : pick the one that fits your hardware:

- **nunchaku-qwen**: SVDQuant FP4/INT4 transformer via [Nunchaku](https://github.com/nunchaku-ai/nunchaku) : **4 sec/frame**, requires RTX 30/40/50 (16 GB VRAM) & CUDA 13.0
- **gguf-qwen**: ComfyUI-native GGUF pipeline (Q3_K_S, Q4_K_S, Q5_K_M, Q6_K, Q8_0) : **12 sec/frame**, runs on RTX 30/40/50 (12 GB VRAM), zero ComfyUI GUI dependency

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
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130 --force-reinstall

# 3) Upgrade Nunchaku (CUDA 13.0 + PyTorch 2.10 build)
pip install https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu13.0torch2.10-cp312-cp312-win_amd64.whl --force-reinstall

# 4) Re-pin PyTorch (Nunchaku may have upgraded it to 2.12)
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130 --force-reinstall

# 5) Re-apply the Nunchaku patch
python patch_nunchaku.py

# 6) Verify
pip show torch       # Expected: 2.10.0+cu130
pip show nunchaku    # Expected: 1.2.1+cu13.0torch2.10
```

---

## 📢 What's New

### 2026-06-12 — Fix Image Tab (GUI)

A standalone **Fix Image** tab (`Tab 4`) has been added to the desktop GUI (`GUI/CMNET2_colorize_client_GUI.py`).
It allows single-image colorization with seed control, drag-and-drop file loading, and preview:

![GUI Tab #4](https://github.com/dan64/DiTServerRPC/blob/main/GUI/assets/gui_page5.jpg)

1. **Load** a B&W image via drag-and-drop (`GUI/load_image_DtD_GUI.py`) or the Browse button
2. **Colorize** with fixed seed (42) or random seed for variation
3. **Save** the colorized result as PNG / JPG

The Fix Image tab is independent of the batch video pipeline and does not require VapourSynth.

### 2026-06-09 — Improved GGUF

Changed the GGUF configuration files. The pipeline Qwen-Image-Edit-2511 + Qwen-Image-Edit-2511-Lightning-4steps has substituted by the pipeline with  Qwen-Image-Edit-2509 + Qwen-Image-Edit-2511-Lightning-4steps. This change has removed the artifacts problem which affected the colored images with the GGUF models and improved the overall quality of the colored images. It should be noted that, despite these improvements, the Nunchaku model remains the best and is the one recommended for production use.  

### 2026-06-07 — Desktop GUI for Batch Video Processing

A **FreeSimpleGUI desktop client** (`GUI/CMNET2_colorize_client_GUI.py`) has been added to the project.
It orchestrates the full video colorization pipeline from a single graphical interface:

1. **Extract** reference frames via VapourSynth + scene-change detection
2. **Colorize** frames via the DiT RPC Server (standard or paired inference)
3. **Encode** the result as H.265 (x265 or NVEnc)
4. **Merge** the AI output with an existing color clip (optional, luminance-guided chroma blend)

![GUI Tab #2](https://github.com/dan64/DiTServerRPC/blob/main/GUI/assets/gui_page3.jpg)

See [GUI/README_GUI.md](GUI/README_GUI.md) for installation, setup, and usage instructions.

> **Prerequisite**: the DiT RPC Server must be running before the GUI can colorize frames.

---

## ✨ Features

- 📦 **Two backends, one API** : nunchaku-qwen (FP4/INT4, 4 sec/frame) for speed, gguf-qwen (Q3_K_S … Q8_0, 12 sec/frame) for lower VRAM
- 🎨 **Batch colorization** : process entire directories of B&W images via filesystem paths
- 🖼️ **Paired inference** : colorize two images in a single forward pass (faster, temporally consistent)
- 📡 **In-memory RPC** : pass raw PNG frames over XML-RPC without touching the filesystem (ideal for video pipelines)
- ⚡ **4-step lightning model** : SVDQuant FP4 quantized transformer for maximum throughput
- 🔒 **Thread-safe** : pipeline loading and stop control are protected by locks; every RPC call runs in its own thread
- ⚙️ **Startup preload** : optional `--load-pipeline` flag loads the model at boot from a JSON config file
- 🚀 **Shared memory transport** : zero-copy image transfer for same-host deployments (~23% faster than standard RPC)

---

## 📋 Prerequisites

Choose the backend that matches your hardware:

### nunchaku-qwen : 4 sec/frame (FP4/INT4)

| Requirement      | Details                            |
| ---------------- | ---------------------------------- |
| **GPU**          | NVIDIA RTX 30/40/50  (16 GB+ VRAM) |
| **RAM**          | 64 GB+                             |
| **CUDA**         | 13.0 or newer                      |
| **CUDA Toolkit** | Must match the PyTorch build       |

> **RTX 30/40-Series (Ampere / Ada)**: use `"model_precision": "int4"`. FP4 requires Blackwell (RTX 50).
> Requires Nunchaku 1.2.1 and `diffusers==0.37.0.dev0` (wheel included in `packages/`).

### gguf-qwen : 14 sec/frame (Q3, Q4, Q5, Q6, Q8)

| Requirement | Details                                |
| ----------- | -------------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (12 GB+ VRAM)     |
| **RAM**     | 32 GB+                                 |
| **CUDA**    | 13.0+ (or CPU-only: slower, zero VRAM) |

> **Q3_K_S** fits in 12 GB VRAM. **Q4_K_S** (default) balances quality and VRAM.
> **Q5_K_M / Q6_K** improve fidelity at higher VRAM cost. **Q8_0** is near-lossless.
> Uses ComfyUI-native code : no ComfyUI GUI installation needed.
> Pre-made configs for all quantizations are in the `config/` folder.

### Both backends

| Requirement | Details                |
| ----------- | ---------------------- |
| **OS**      | Windows 10/11 or Linux |
| **Python**  | 3.12                   |

---

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
git clone https://github.com/dan64/DiTServerRPC.git
cd DiTServerRPC
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
pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 torchaudio==2.10.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130 --force-reinstall
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

A tested compatible wheel is included in the `packages/` folder.
Install it directly:

```bash
pip install packages\diffusers-0.37.0.dev0-py3-none-any.whl
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
    comfy-aimdo==0.4.7 \
    comfy-kitchen
```

> **Nunchaku users**: `diffusers` was already installed in step 5 as the compatible
> `0.37.0.dev0` wheel. Do NOT upgrade it  :  nunchaku 1.2.1 requires exactly that version.
> 
> `safetensors` is pulled automatically by diffusers.
> 
> `scipy`, `av`, and `torchsde` are required by the diffusers pipeline.
> `gguf`, `comfy-aimdo`, and `comfy-kitchen` are required by the GGUF backend.

## 📂 Project Structure

```
dit-colorize-rpc/
├── dit_rpc_server.py            # XML-RPC server (entry point)
├── dit_colorize_main.py         # Colorization pipeline and image utilities
├── dit_client_example.py        # Example RPC client : single frame
├── dit_client_pair_example.py   # Example RPC client : paired inference
├── patch_nunchaku.py            # Compatibility patch for nunchaku 1.2.1
├── config/                      # Pipeline configs (nunchaku FP4/INT4 + gguf Q3–Q8)
├── install.cmd                  # Windows automated installer
├── start_server.cmd             # Windows launcher : server
├── run_client_example.cmd       # Windows launcher : single frame example
├── run_client_pair_example.cmd  # Windows launcher : paired inference example
├── patch_nunchaku.cmd           # Windows launcher : nunchaku patch
├── assets/
│   ├── santa_bw.png             # Sample B&W image (single frame test)
│   ├── sample1_bw.jpg           # Sample B&W image 1 (paired inference test)
│   └── sample2_bw.jpg           # Sample B&W image 2 (paired inference test)
├── packages/
│   └── diffusers-0.37.0.dev0-py3-none-any.whl  # Tested compatible diffusers build
└── README.md
```

---

## 🔧 Pipeline Configuration

Ready-to-use config files for both backends are in the `config/` folder.
Pick the one that matches your hardware and pass it to `--pipeline-config`.

### Nunchaku Backend : `config/qwen_nunchaku_fp4.json` & `qwen_nunchaku_int4.json`

#### `config/qwen_nunchaku_fp4.json` : RTX 50-Series (Blackwell)

```json
{
    "model_name":            "nunchaku-qwen",
    "model_precision":       "fp4",
    "model_rank":            "32",
    "model_inference_steps": "4",
    "cache_dir":             "",
    "full_model_path":       ""
}
```

#### `config/qwen_nunchaku_int4.json` : RTX 30 / 40-Series (Ampere / Ada Lovelace)

```json
{
    "model_name":            "nunchaku-qwen",
    "model_precision":       "int4",
    "model_rank":            "32",
    "model_inference_steps": "4",
    "cache_dir":             "",
    "full_model_path":       ""
}
```

> ⚠️ **`model_precision`**: use `"fp4"` only on RTX 50-Series (Blackwell). On RTX 30 / 40-Series
> use `"int4"` : FP4 kernels require sm_120 and will fail on older architectures.

### GGUF Backend : `config/qwen_gguf_q3.json` … `qwen_gguf_q8.json`

Five quantization levels are available. All share the same structure with
`model_name: "gguf-qwen"` and a `quant` field that selects the quantization:

| Config file         | `quant` | UNet           | CLIP           |
| ------------------- | ------- | -------------- | -------------- |
| `qwen_gguf_q3.json` | `"q3"`  | `…Q3_K_S.gguf` | `…Q3_K_S.gguf` |
| `qwen_gguf_q4.json` | `"q4"`  | `…Q4_K_S.gguf` | `…Q4_K_S.gguf` |
| `qwen_gguf_q5.json` | `"q5"`  | `…Q5_K_M.gguf` | `…Q5_K_M.gguf` |
| `qwen_gguf_q6.json` | `"q6"`  | `…Q6_K.gguf`   | `…Q6_K.gguf`   |
| `qwen_gguf_q8.json` | `"q8"`  | `…Q8_0.gguf`   | `…Q8_0.gguf`   |

> **Q4 is the recommended default** : good quality/VRAM balance, but even Q3 is capable of delivering frames with acceptable colors.
> All quants share the same VAE, mmproj, and LoRA files (auto-downloaded from HuggingFace).

> **⚠️ The GGUF backend is experimental.** In some cases the frames colors may be faded or little colored. For production use, prefer `nunchaku-qwen` (FP4/INT4) which is not affected by such problems.

Config example (`config/qwen_gguf_q4.json`):

```json
{
    "model_name":       "gguf-qwen",
    "quant":            "q4",
    "unet_gguf":        "models/unet/qwen-image-edit-2511-Q4_K_S.gguf",
    "clip_gguf":        "models/clip/Qwen2.5-VL-7B-Instruct-Q4_K_S.gguf",
    "mmproj_gguf":      "models/clip/Qwen2.5-VL-7B-Instruct-mmproj-BF16.gguf",
    "vae_name":         "qwen_image_vae.safetensors",
    "lora_path":        "models/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
    "steps":            4,
    "hf_unet":          "unsloth/Qwen-Image-Edit-2511-GGUF",
    "hf_clip":          "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
    "hf_vae":           "Comfy-Org/Qwen-Image_ComfyUI",
    "hf_lora":          "lightx2v/Qwen-Image-Edit-2511-Lightning"
}
```

#### LoRA (Lightning 4-step)

The LoRA file `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` enables **4-step inference** (down from 20-50 steps without LoRA). It is a ComfyUI-format LoRA that gets merged directly into the transformer at load time.

- **With LoRA**: call `colorize_image(..., steps=4)`  :  fast, same quality
- **Without LoRA**: set `full_model_path` to `""` and use `steps=20` or higher

The LoRA is merged statically (not applied as an adapter), so there is no runtime overhead.

### Key reference

| Key                                       | Required | Description                                                                                  |
| ----------------------------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `model_name`                              | ✅        | `"nunchaku-qwen"` or `"gguf-qwen"`                                                           |
| `quant`                                   |          | **GGUF only**: quantization level (`"q3"`, `"q4"`, `"q5"`, `"q6"`, `"q8"`). Default: `"q4"`  |
| `model_precision`                         | ✅        | **Nunchaku**: `"fp4"` (RTX 50) or `"int4"` (RTX 30/40). **GGUF**: not used                   |
| `unet_gguf` / `clip_gguf` / `mmproj_gguf` | ✅        | **GGUF only**: local paths to the GGUF model files                                           |
| `model_rank`                              |          | **Nunchaku**: SVD rank (`"32"`). **GGUF**: not used                                          |
| `model_inference_steps`                   |          | **Nunchaku**: diffusion steps (`"4"`). **GGUF**: not used                                    |
| `cache_dir`                               |          | HuggingFace cache directory. Leave empty to use the default `~/.cache/huggingface`           |
| `full_model_path`                         |          | **Nunchaku**: local path to the transformer checkpoint. **GGUF**: not used                   |
| `lora_path`                               |          | **GGUF only**: path to the Lightning 4-step LoRA (`.safetensors`). Omit to skip LoRA merging |
| `steps`                                   |          | **GGUF only**: inference steps (`4` with LoRA, `20` without)                                 |
| `vae_name`                                |          | **GGUF only**: VAE filename                                                                  |
| `hf_*`                                    |          | **GGUF only**: HuggingFace repo names for auto-download                                      |

---

## 🚀 Usage

### Start the server (no preload : pipeline loaded later via RPC)

```bash
python dit_rpc_server.py
```

### Start the server with pipeline preloaded at boot

```bash
# RTX 50-Series
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen_nunchaku_fp4.json

# RTX 30 / 40-Series
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen_nunchaku_int4.json

# GGUF (any quantization)
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen_gguf_q3.json
```

On Windows you can also use the provided `start_server.cmd` (see [Windows launch script](#-windows-launch-script)).

### Full list of CLI arguments

```
usage: dit_rpc_server.py [-h] [--host HOST] [--port PORT]
                         [--logfile LOGFILE] [--module-dir MODULE_DIR]
                         [--load-pipeline] [--pipeline-config CONFIG.json]

options:
  --host HOST                  Address to listen on (default: 127.0.0.1)
  --port PORT                  TCP port (default: 8765)
  --logfile LOGFILE            Optional path for a log file
  --module-dir MODULE_DIR      Directory containing dit_colorize_main.py
                               (default: same directory as this script)
  --load-pipeline              Load the colorization pipeline at startup
  --pipeline-config CONFIG.json
                               Path to the JSON pipeline config file
                               (required when --load-pipeline is set)
```

---

## 📡 RPC API Reference

Connect from any Python client using `xmlrpc.client`:

```python
import xmlrpc.client
proxy = xmlrpc.client.ServerProxy("http://127.0.0.1:8765/", use_builtin_types=True)
```

All methods return a `dict` with at least `{"ok": bool, "msg": str}`.

### Health

| Method   | Returns  | Description        |
| -------- | -------- | ------------------ |
| `ping()` | `"pong"` | Connectivity check |

### Pipeline management

| Method                                                                                                            | Returns         | Description                   |
| ----------------------------------------------------------------------------------------------------------------- | --------------- | ----------------------------- |
| `load_pipeline(model_name, model_precision, model_rank, model_inference_steps, cache_dir="", full_model_path="")` | `{"ok", "msg"}` | Load the model into VRAM      |
| `is_pipeline_loaded()`                                                                                            | `bool`          | True if the pipeline is ready |
| `unload_pipeline()`                                                                                               | `{"ok", "msg"}` | Release VRAM                  |

### Stop control

| Method                | Returns | Description                                     |
| --------------------- | ------- | ----------------------------------------------- |
| `request_stop()`      | `bool`  | Ask the server to refuse new colorization calls |
| `clear_stop()`        | `bool`  | Reset the stop flag before a new batch          |
| `is_stop_requested()` | `bool`  | Check the current stop flag                     |

### Colorization : filesystem-based

| Method                                                                          | Returns                               | Description                                  |
| ------------------------------------------------------------------------------- | ------------------------------------- | -------------------------------------------- |
| `colorize_image(in_path, out_path, prompt, img_size=0, steps=2)`                | `{"ok", "elapsed", "skipped", "msg"}` | Single image, paths on the server filesystem |
| `colorize_image_pair(img1_path, img2_path, out_dir, prompt, gap_px=8, steps=2)` | `{"ok", "elapsed", "msg"}`            | Two images, single inference pass            |
| `colorize_single_image(img_path, out_dir, prompt, steps=2)`                     | `{"ok", "elapsed", "msg"}`            | Single image fallback (odd batch end)        |

### Colorization : in-memory (PNG bytes over RPC)

| Method                                                                 | Returns                                                              | Description                       |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------- |
| `colorize_frame(img_data, prompt, img_size=0, steps=2)`                | `{"ok", "data", "elapsed", "skipped", "msg"}`                        | Single frame as raw PNG bytes     |
| `colorize_frame_pair(img1_data, img2_data, prompt, gap_px=8, steps=2)` | `{"ok", "data1", "data2", "elapsed", "skipped1", "skipped2", "msg"}` | Two frames, single inference pass |

> `skipped=True` means the frame was too dark to colorize (average brightness < 9/255).
> The returned `data` field contains the unchanged input in that case.

### Colorization : shared memory (same-host only, zero-copy)

| Method                                                                                                     | Returns                                            | Description                                         |
| ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------- | --------------------------------------------------- |
| `colorize_frame_shm(shm_in, shm_out, h, w, prompt, img_size=0, steps=2)`                                   | `{"ok", "elapsed", "skipped", "msg"}`              | Single frame via shared memory                      |
| `colorize_frame_pair_shm(shm_in1, shm_out1, h1, w1, shm_in2, shm_out2, h2, w2, prompt, gap_px=8, steps=4)` | `{"ok", "elapsed", "skipped1", "skipped2", "msg"}` | Two frames via shared memory, single inference pass |

> See [Shared Memory Transport](#-shared-memory-transport-same-host-only) for usage details.

---

## 🧪 Example Clients

Both clients support two transport modes selectable via `--use-shm`:

| Mode          | Flag        | When to use                                 | Measured speed (1480×1080 px pair) |
| ------------- | ----------- | ------------------------------------------- | ---------------------------------- |
| Standard RPC  | _(default)_ | Any deployment, including remote server     | ~5.25s/image                       |
| Shared memory | `--use-shm` | Server and client on the **same host** only | ~4.06s/image (**~23% faster**)     |

> The pipeline must be loaded on the server before running the clients.
> Start the server with `--load-pipeline --pipeline-config CONFIG.json`.

### Single frame : `dit_client_example.py`

Colorizes `assets/santa_bw.png` and saves the result as `assets/santa_colorized.png`.

```bash
# standard RPC : works with local and remote server
python dit_client_example.py

# shared memory : same-host only, lower latency
python dit_client_example.py --use-shm
```

Windows: `run_client_example.cmd`
To enable shared memory edit `run_client_example.cmd` and set `USE_SHM=1`.

---

### Paired inference : `dit_client_pair_example.py`

Colorizes `assets/sample1_bw.jpg` and `assets/sample2_bw.jpg` in a **single forward
pass**, saving `assets/sample1_colorized.jpg` and `assets/sample2_colorized.jpg`.

Paired inference places the two images side-by-side and runs one inference instead of
two, roughly halving the per-image cost (~5.25s/image vs ~11s standalone).
Combined with shared memory transport this reaches ~4.06s/image.

```bash
# standard RPC
python dit_client_pair_example.py

# shared memory : same-host only
python dit_client_pair_example.py --use-shm
```

Windows: `run_client_pair_example.cmd`
To enable shared memory edit `run_client_pair_example.cmd` and set `USE_SHM=1`.

### Full list of arguments (both clients)

```
  --host HOST                  Server host (default: 127.0.0.1)
  --port PORT                  Server port (default: 8765)
  --prompt PROMPT              Text prompt for the model
  --use-shm                    Use shared memory transport (same-host only)
```

Additional argument for the paired client:

```
  --gap-px N                   Separator width in pixels between the two
                               images in the merged input (default: 8)
```

---

## 🚀 Shared Memory Transport (same-host only)

### What it is

The standard RPC transport serializes each image as a PNG byte stream, encodes it in
Base64, sends it over a TCP socket, and decodes it on the other side. For a 1480×1080
frame this is roughly 4–5 MB per round trip.

The shared memory transport bypasses the network entirely. The client writes the raw
pixel array directly into a shared memory segment; the server attaches to the same
segment and reads the pixels without any copy. Only the metadata (segment name,
dimensions, prompt) travels over the XML-RPC socket.

### When you can use it

**Requirement: server and client must run on the same machine.**

If the server is on a dedicated GPU machine and the client is on a separate workstation,
shared memory is not available : use the standard RPC transport instead (default).
The clients detect this automatically: passing `--use-shm` when the host is not
`127.0.0.1` / `localhost` prints a warning and falls back to standard RPC.

### Performance

Measured on a 1480×1080 pixel pair (RTX 5070 Ti, FP4, paired inference):

| Transport          | Per-image time  | Round-trip overhead   |
| ------------------ | --------------- | --------------------- |
| Standard RPC (PNG) | ~5.25s          | ~1.1s                 |
| Shared memory      | ~4.06s          | ~0.16s                |
| **Gain**           | **~23% faster** | **~7× less overhead** |

The round-trip overhead with shared memory is essentially zero : the 0.16s gap between
inference time and wall-clock time is just Python function call and numpy overhead.

On a 100k-frame video processed as pairs (50k inference calls) the cumulative saving is:

```
(5.25 - 4.06) × 50,000 ≈ 16.5 hours
```

### How the protocol works

The **client** owns and manages all shared memory segments. The server is fully
stateless with respect to shared memory : it only attaches, reads/writes, and detaches.

```
Client                                     Server
  │                                           │
  │  create shm_in  (h × w × 3 bytes)         │
  │  create shm_out (h × w × 3 bytes)         │
  │  write raw RGB pixels → shm_in            │
  │                                           │
  │  RPC(shm_in_name, shm_out_name, h, w, …) ─►│
  │                                           │  attach shm_in  → PIL Image
  │                                           │  inference
  │                                           │  result → shm_out
  │◄─ return {elapsed, skipped, …} ───────────│
  │                                           │  detach both segments
  │  read shm_out → PIL Image                 │
  │  unlink shm_in + shm_out                  │
```

### Enabling shared memory

**From the command line:**

```bash
python dit_client_pair_example.py --use-shm
python dit_client_example.py      --use-shm
```

**From the Windows `.cmd` launchers**, edit the user configuration block and set:

```batch
set USE_SHM=1
```

The banner will confirm the active transport:

```
Transport   : 1 (0=RPC 1=shared memory)
```

And the Python client will print:

```
[INFO] Transport: shared memory
```

### Implementing shared memory in your own client

```python
import uuid
import numpy as np
from multiprocessing.shared_memory import SharedMemory
from PIL import Image

def colorize_pair_shm(proxy, img1: Image.Image, img2: Image.Image, prompt: str):
    arr1, arr2 = np.array(img1), np.array(img2)
    h1, w1 = arr1.shape[:2]
    h2, w2 = arr2.shape[:2]
    uid = uuid.uuid4().hex[:12]

    # Create all four segments (client owns them)
    segs = {
        tag: SharedMemory(name=f"dit_{tag}_{uid}", create=True, size=h*w*3)
        for tag, h, w in [("in1",h1,w1),("out1",h1,w1),("in2",h2,w2),("out2",h2,w2)]
    }
    try:
        np.ndarray((h1,w1,3), dtype=np.uint8, buffer=segs["in1"].buf)[:] = arr1
        np.ndarray((h2,w2,3), dtype=np.uint8, buffer=segs["in2"].buf)[:] = arr2

        result = proxy.colorize_frame_pair_shm(
            segs["in1"].name, segs["out1"].name, h1, w1,
            segs["in2"].name, segs["out2"].name, h2, w2,
            prompt, 8,  # gap_px
        )

        out1 = Image.fromarray(
            np.ndarray((h1,w1,3), dtype=np.uint8, buffer=segs["out1"].buf).copy())
        out2 = Image.fromarray(
            np.ndarray((h2,w2,3), dtype=np.uint8, buffer=segs["out2"].buf).copy())
        return result, out1, out2
    finally:
        for shm in segs.values():
            shm.close(); shm.unlink()
```

---

## 🪟 Windows Launch Script

`start_server.cmd` is a ready-to-use launcher for Windows.
Edit the variables at the top of the file to match your setup, then double-click it or run it from a terminal.

```
start_server.cmd [q3|q4|q5|q6|q8|fp4|int4]
```

| Argument | Backend  | Quantization | VRAM  |
| -------- | -------- | ------------ | ----- |
| _(none)_ | GGUF     | Q4_K_S       | 12 GB |
| `q3`     | GGUF     | Q3_K_S       | 12 GB |
| `q4`     | GGUF     | Q4_K_S       | 12 GB |
| `q5`     | GGUF     | Q5_K_M       | 16 GB |
| `q6`     | GGUF     | Q6_K         | 18 GB |
| `q8`     | GGUF     | Q8_0         | 22 GB |
| `fp4`    | Nunchaku | FP4          | 16 GB |
| `int4`   | Nunchaku | INT4         | 16 GB |

If no argument is passed it defaults to `q4` (Q4_K_S). Use `int4` for RTX 30 / 40-Series Nunchaku:

```
start_server.cmd int4
```

**Convenience wrappers** — double-click or run from terminal without arguments:

| File                  | Equivalent command      | Backend       |
| --------------------- | ----------------------- | ------------- |
| `run_server_q3.cmd`   | `start_server.cmd q3`   | GGUF Q3_K_S   |
| `run_server_fp4.cmd`  | `start_server.cmd fp4`  | Nunchaku FP4  |
| `run_server_int4.cmd` | `start_server.cmd int4` | Nunchaku INT4 |

---

## 🔧 Troubleshooting

**`CUDA out of memory`**
Close other GPU applications. On 16 GB cards the server automatically enables sequential CPU offload for layers that do not fit in VRAM.

**`dit_colorize_main.py NOT FOUND`**
Use `--module-dir` to point the server to the directory that contains `dit_colorize_main.py`:

```bash
python dit_rpc_server.py --module-dir /path/to/dit_colorize_main
```

**`Model 'xxx' is not supported`**
Supported values for `model_name` are `"nunchaku-qwen"` (FP4/INT4) and `"gguf-qwen"` (Q3_K_S, Q4_K_S, Q5_K_M, Q6_K, Q8_0). For `"gguf-qwen"`, the quantization is selected via the `quant` field in the config (e.g. `"q4"`).

**Pipeline takes a long time to load**
**Nunchaku**: on the first run the model weights (~15–30 GB) are downloaded from HuggingFace.
Subsequent runs load from the local cache.
**GGUF**: only the VAE and tokenizer (~320 MB) are downloaded from HuggingFace; the UNet and CLIP are loaded directly from the local `.gguf` files. Set `cache_dir` in the config to control where the cache is stored.

---

## 🔗 Credits

- **Model**: [Qwen/Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)
- **Nunchaku quantization**: [Nunchaku / SVDQuant](https://github.com/mit-han-lab/nunchaku)
- **GGUF dequantization kernels**: adapted from [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) (Apache 2.0)
- **Pipeline**: [Hugging Face Diffusers](https://github.com/huggingface/diffusers)