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

| Requirement      | Details                                                           |
| ---------------- | ----------------------------------------------------------------- |
| **OS**           | Windows 10/11 or Linux                                            |
| **Python**       | 3.12 or newer                                                     |
| **GPU**          | NVIDIA RTX 3090 / 4090 / 5070 Ti / 5090 (16 GB+ VRAM recommended) |
| **CUDA**         | 12.8 or newer                                                     |
| **CUDA Toolkit** | Must match the PyTorch build (see below)                          |

> **RTX 50-Series (Blackwell / sm_120) users**: PyTorch Nightly is required.
> Stable PyTorch releases do not yet include Blackwell CUDA kernels.

> **RTX 40-Series and older**: use `"model_precision": "int4"` in the pipeline config file.
> FP4 quantization requires Blackwell hardware; INT4 is the correct precision for Ampere (RTX 30) and Ada Lovelace (RTX 40) GPUs.

---

## ⚙️ Environment Setup

### 1 — Create a virtual environment

Using `conda` (recommended):

```bash
conda create -n dit-colorize python=3.12 -y
conda activate dit-colorize
```

Or using `venv`:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

---

### 2 — Install PyTorch

#### RTX 50-Series (Blackwell) — PyTorch Nightly + CUDA 12.8

```bash
pip install --pre torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/nightly/cu128
```

#### RTX 30 / 40-Series — PyTorch Stable + CUDA 12.8

```bash
pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128
```

Verify the installation:

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

---

### 3 — Install Nunchaku

Nunchaku provides the SVDQuant FP4 quantized transformer.

```bash
pip install nunchaku
```

> If a pre-built wheel is not available for your platform, follow the
> [Nunchaku build instructions](https://github.com/mit-han-lab/nunchaku?tab=readme-ov-file#installation).

---

### 4 — Install Diffusers

The `QwenImageEditPlusPipeline` used by this project requires a recent version of Diffusers.
Install directly from GitHub to ensure compatibility:

```bash
pip install git+https://github.com/huggingface/diffusers.git
```

---

### 5 — Install remaining dependencies

```bash
pip install \
    transformers>=4.46.0 \
    accelerate>=0.34.0 \
    huggingface_hub>=0.26.0 \
    Pillow>=10.0.0
```

---

## 📂 Project Structure

```
dit-colorize-rpc/
├── dit_rpc_server.py        # XML-RPC server (entry point)
├── dit_colorize_main.py     # Colorization pipeline and image utilities
├── dit_client_example.py    # Example RPC client
├── qwen_config_fp4.json     # Config for RTX 50-Series (FP4)
├── qwen_config_int4.json    # Config for RTX 30 / 40-Series (INT4)
├── start_server.cmd         # Windows launcher — server
├── run_client_example.cmd   # Windows launcher — example client
├── assets/
│   └── santa_bw.png         # Sample B&W image for testing
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

| Key                     | Required | Description                                                                                    |
| ----------------------- | -------- | ---------------------------------------------------------------------------------------------- |
| `model_name`            | ✅        | Must be `"nunchaku-qwen"`                                                                      |
| `model_precision`       | ✅        | `"fp4"` (RTX 50) or `"int4"` (RTX 30/40)                                                       |
| `model_rank`            | ✅        | SVD rank — `"32"` is a good default                                                            |
| `model_inference_steps` | ✅        | Diffusion steps — `"4"` for lightning model                                                    |
| `cache_dir`             | ➖        | HuggingFace cache directory. Omit or set to `""` to use the default (`~/.cache/huggingface`)   |
| `full_model_path`       | ➖        | Absolute path to a local `.safetensors` file. Omit or set to `""` to download from HuggingFace |

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

### Colorization — filesystem-based

| Method                                                                 | Returns                               | Description                                  |
| ---------------------------------------------------------------------- | ------------------------------------- | -------------------------------------------- |
| `colorize_image(in_path, out_path, prompt, img_size=0, steps=2)`       | `{"ok", "elapsed", "skipped", "msg"}` | Single image, paths on the server filesystem |
| `colorize_image_pair(img1_path, img2_path, out_dir, prompt, gap_px=8)` | `{"ok", "elapsed", "msg"}`            | Two images, single inference pass            |
| `colorize_single_image(img_path, out_dir, prompt)`                     | `{"ok", "elapsed", "msg"}`            | Single image fallback (odd batch end)        |

### Colorization — in-memory (PNG bytes over RPC)

| Method                                                        | Returns                                                              | Description                       |
| ------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------- |
| `colorize_frame(img_data, prompt, img_size=0, steps=2)`       | `{"ok", "data", "elapsed", "skipped", "msg"}`                        | Single frame as raw PNG bytes     |
| `colorize_frame_pair(img1_data, img2_data, prompt, gap_px=8)` | `{"ok", "data1", "data2", "elapsed", "skipped1", "skipped2", "msg"}` | Two frames, single inference pass |

> `skipped=True` means the frame was too dark to colorize (average brightness < 9/255).
> The returned `data` field contains the unchanged input in that case.

---

## 🧪 Example Client

`dit_client_example.py` is a minimal working client that colorizes `assets/santa_bw.png`
and saves the result as `assets/santa_colorized.png`.

### Run with pipeline already loaded on the server

```bash
python dit_client_example.py
```

### Run and let the client load the pipeline first

```bash
# RTX 50-Series
python dit_client_example.py --pipeline-config qwen_config_fp4.json

# RTX 30 / 40-Series
python dit_client_example.py --pipeline-config qwen_config_int4.json
```

### Full list of client arguments

```
usage: dit_client_example.py [-h] [--host HOST] [--port PORT]
                              [--pipeline-config CONFIG.json]
                              [--prompt PROMPT]
                              [--img-size IMG_SIZE] [--steps STEPS]

options:
  --host HOST                  Server host (default: 127.0.0.1)
  --port PORT                  Server port (default: 8765)
  --pipeline-config CONFIG.json
                               Load the pipeline before colorizing
  --prompt PROMPT              Text prompt for the model
  --img-size IMG_SIZE          Max long side in pixels (0 = original size)
  --steps STEPS                Inference steps (default: 2)
```

The result image `santa_colorized.png` will be written next to the input in
the `assets/` folder.

On Windows you can also use the provided `run_client_example.cmd`:

```
run_client_example.cmd          # RTX 50-Series (fp4, default)
run_client_example.cmd int4     # RTX 30 / 40-Series
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
