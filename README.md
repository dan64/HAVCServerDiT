# DiT Colorize RPC Server

An XML-RPC server that exposes a GPU-accelerated colorization pipeline for black-and-white images and video frames.
Built on top of the [Nunchaku](https://github.com/mit-han-lab/nunchaku) SVDQuant FP4 transformer and the `Qwen-Image-Edit-2509` diffusion model.

**Optimized for NVIDIA RTX 50-Series (Blackwell) & CUDA 12.8.**

---

## ✨ Features

- 🎨 **Batch colorization** — process entire directories of B&W images via filesystem paths
- 🖼️ **Paired inference** — colorize two images in a single forward pass (faster, temporally consistent)
- 📡 **In-memory RPC** — pass raw PNG frames over XML-RPC without touching the filesystem (ideal for video pipelines)
- ⚡ **4-step lightning model** — SVDQuant FP4 quantized transformer for maximum throughput
- 🔒 **Thread-safe** — pipeline loading and stop control are protected by locks; every RPC call runs in its own thread
- ⚙️ **Startup preload** — optional `--load-pipeline` flag loads the model at boot from a JSON config file

---

## 📋 Prerequisites

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11 or Linux |
| **Python** | 3.12 |
| **GPU** | NVIDIA RTX 3090 / 4090 / 5070 Ti / 5090 (16 GB+ VRAM recommended) |
| **CUDA** | 12.8 or newer |
| **CUDA Toolkit** | Must match the PyTorch build (see below) |

> **RTX 40-Series and older**: use `"model_precision": "int4"` in the pipeline config file.
> FP4 quantization requires Blackwell hardware; INT4 is the correct precision for Ampere (RTX 30) and Ada Lovelace (RTX 40) GPUs.

---

## ⚙️ Environment Setup

### 1 — Create a virtual environment

Open a terminal, move into the project directory and create the venv there:

```bash
cd C:\path\to\dit-colorize-rpc

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

> **Windows quick-start**: once the venv is active you can run `install.cmd` to execute
> steps 2–6 automatically instead of running them one by one.

---

### 2 — Install PyTorch 2.9.1 + CUDA 12.8

Use the **stable** build for all GPU generations (RTX 30 / 40 / 50):

```bash
pip install torch==2.9.1+cu128 torchvision==0.24.1+cu128 torchaudio==2.9.1+cu128 \
    --index-url https://download.pytorch.org/whl/cu128
```

Verify the installation:

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

---

### 3 — Install Nunchaku

> ⚠️ **Do NOT use `pip install nunchaku`** — that installs an unrelated package from PyPI
> with the same name that will fail with `ModuleNotFoundError: No module named 'nunchaku.models'`.

Install the correct MIT Han Lab build directly from the GitHub release:

```bash
# Windows / Python 3.12 / CUDA 12.8 / PyTorch 2.9
pip install https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu12.8torch2.9-cp312-cp312-win_amd64.whl
```

For other platforms or Python versions, browse the full list of available wheels on the
[Nunchaku releases page](https://github.com/nunchaku-ai/nunchaku/releases/tag/v1.2.1)
and replace the filename accordingly.

Verify the correct package is installed — the version string must contain the build tags:

```bash
pip show nunchaku
# Expected: Version: 1.2.1+cu12.8torch2.9
```

### 4 — Patch Nunchaku

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

### 5 — Install Diffusers

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

### 6 — Install remaining dependencies

Pin the versions to match the tested working environment:

```bash
pip install \
    transformers==4.57.6 \
    accelerate==1.12.0 \
    huggingface_hub>=0.26.0 \
    Pillow>=10.0.0
```

> `safetensors` is intentionally not pinned here — diffusers pulls the correct version
> automatically as a dependency (`>=0.8.0-rc.0`).

---

## 📂 Project Structure

```
dit-colorize-rpc/
├── dit_rpc_server.py            # XML-RPC server (entry point)
├── dit_colorize_main.py         # Colorization pipeline and image utilities
├── dit_client_example.py        # Example RPC client — single frame
├── dit_client_pair_example.py   # Example RPC client — paired inference
├── patch_nunchaku.py            # Compatibility patch for nunchaku 1.2.1
├── qwen_config_fp4.json         # Config for RTX 50-Series (FP4)
├── qwen_config_int4.json        # Config for RTX 30 / 40-Series (INT4)
├── install.cmd                  # Windows automated installer
├── start_server.cmd             # Windows launcher — server
├── run_client_example.cmd       # Windows launcher — single frame example
├── run_client_pair_example.cmd  # Windows launcher — paired inference example
├── patch_nunchaku.cmd           # Windows launcher — nunchaku patch
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

Two ready-to-use config files are provided. Pick the one that matches your GPU and pass it to `--pipeline-config`.

### `qwen_config_fp4.json` — RTX 50-Series (Blackwell)

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

### `qwen_config_int4.json` — RTX 30 / 40-Series (Ampere / Ada Lovelace)

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
> use `"int4"` — FP4 kernels require sm_120 and will fail on older architectures.

### Key reference

| Key | Required | Description |
|---|---|---|
| `model_name` | ✅ | Must be `"nunchaku-qwen"` |
| `model_precision` | ✅ | `"fp4"` (RTX 50) or `"int4"` (RTX 30/40) |
| `model_rank` | ✅ | SVD rank — `"32"` is a good default |
| `model_inference_steps` | ✅ | Diffusion steps used to **select the model file** to download — must be `"4"` (no 2-step model file exists). To run inference faster, pass `steps=2` in the RPC call — this is independent of the downloaded model and reduces latency by ~30% |
| `cache_dir` | ➖ | HuggingFace cache directory. Omit or set to `""` to use the default (`~/.cache/huggingface`) |
| `full_model_path` | ➖ | Absolute path to a local `.safetensors` file. Omit or set to `""` to download from HuggingFace |

---

## 🚀 Usage

### Start the server (no preload — pipeline loaded later via RPC)

```bash
python dit_rpc_server.py
```

### Start the server with pipeline preloaded at boot

```bash
# RTX 50-Series
python dit_rpc_server.py --load-pipeline --pipeline-config qwen_config_fp4.json

# RTX 30 / 40-Series
python dit_rpc_server.py --load-pipeline --pipeline-config qwen_config_int4.json
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

| Method | Returns | Description |
|---|---|---|
| `ping()` | `"pong"` | Connectivity check |

### Pipeline management

| Method | Returns | Description |
|---|---|---|
| `load_pipeline(model_name, model_precision, model_rank, model_inference_steps, cache_dir="", full_model_path="")` | `{"ok", "msg"}` | Load the model into VRAM |
| `is_pipeline_loaded()` | `bool` | True if the pipeline is ready |
| `unload_pipeline()` | `{"ok", "msg"}` | Release VRAM |

### Stop control

| Method | Returns | Description |
|---|---|---|
| `request_stop()` | `bool` | Ask the server to refuse new colorization calls |
| `clear_stop()` | `bool` | Reset the stop flag before a new batch |
| `is_stop_requested()` | `bool` | Check the current stop flag |

### Colorization — filesystem-based

| Method | Returns | Description |
|---|---|---|
| `colorize_image(in_path, out_path, prompt, img_size=0, steps=2)` | `{"ok", "elapsed", "skipped", "msg"}` | Single image, paths on the server filesystem |
| `colorize_image_pair(img1_path, img2_path, out_dir, prompt, gap_px=8)` | `{"ok", "elapsed", "msg"}` | Two images, single inference pass |
| `colorize_single_image(img_path, out_dir, prompt)` | `{"ok", "elapsed", "msg"}` | Single image fallback (odd batch end) |

### Colorization — in-memory (PNG bytes over RPC)

| Method | Returns | Description |
|---|---|---|
| `colorize_frame(img_data, prompt, img_size=0, steps=2)` | `{"ok", "data", "elapsed", "skipped", "msg"}` | Single frame as raw PNG bytes |
| `colorize_frame_pair(img1_data, img2_data, prompt, gap_px=8)` | `{"ok", "data1", "data2", "elapsed", "skipped1", "skipped2", "msg"}` | Two frames, single inference pass |

> `skipped=True` means the frame was too dark to colorize (average brightness < 9/255).
> The returned `data` field contains the unchanged input in that case.

---

## 🧪 Example Clients

### Single frame — `dit_client_example.py`

Colorizes `assets/santa_bw.png` and saves the result as `assets/santa_colorized.png`.

```bash
# pipeline already loaded on the server
python dit_client_example.py

# let the client load the pipeline first
python dit_client_example.py --pipeline-config qwen_config_fp4.json   # RTX 50
python dit_client_example.py --pipeline-config qwen_config_int4.json  # RTX 30/40
```

Windows: `run_client_example.cmd [fp4|int4]`

---

### Paired inference — `dit_client_pair_example.py`

Colorizes `assets/sample1_bw.jpg` and `assets/sample2_bw.jpg` in a **single forward
pass**, saving `assets/sample1_colorized.jpg` and `assets/sample2_colorized.jpg`.

Paired inference places the two images side-by-side and runs one inference instead of
two, roughly halving the per-image cost (~4.5s/image vs ~11s standalone).

```bash
python dit_client_pair_example.py --pipeline-config qwen_config_fp4.json   # RTX 50
python dit_client_pair_example.py --pipeline-config qwen_config_int4.json  # RTX 30/40
```

Windows: `run_client_pair_example.cmd [fp4|int4]`

### Full list of arguments (both clients)

```
  --host HOST                  Server host (default: 127.0.0.1)
  --port PORT                  Server port (default: 8765)
  --pipeline-config CONFIG     Load pipeline before colorizing
  --prompt PROMPT              Text prompt for the model
```

Additional argument for the paired client:

```
  --gap-px N                   Separator width in pixels between the two
                               images in the merged input (default: 8)
```

---

## 🪟 Windows Launch Script

`start_server.cmd` is a ready-to-use launcher for Windows.
Edit the variables at the top of the file to match your setup, then double-click it or run it from a terminal.

```
start_server.cmd [fp4|int4]
```

If no argument is passed it defaults to `fp4`. Pass `int4` for RTX 30 / 40-Series:

```
start_server.cmd int4
```

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
The only supported value for `model_name` is `"nunchaku-qwen"`.

**Pipeline takes a long time to load**
On the first run the model weights (~15–30 GB) are downloaded from HuggingFace.
Subsequent runs load from the local cache. Set `cache_dir` in the config to control where the cache is stored.

---

## 🔗 Credits

- **Model**: [Qwen/Qwen-Image-Edit-2509](https://huggingface.co/Qwen/Qwen-Image-Edit-2509)
- **Quantization**: [Nunchaku / SVDQuant](https://github.com/mit-han-lab/nunchaku)
- **Pipeline**: [Hugging Face Diffusers](https://github.com/huggingface/diffusers)
