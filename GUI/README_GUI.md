# HAVC Client — GUI

A FreeSimpleGUI-based desktop client that connects to the [HAVC DiT Server](../README.md)
and orchestrates a full video colorization pipeline: extraction → AI colorization → encoding → merge.

---

## Table of Contents

- [Pipeline Overview](#pipeline-overview)
- [System Requirements](#system-requirements)
- [Installation](#installation)
  - [1. Activate the shared virtual environment](#1-activate-the-shared-virtual-environment)
  - [2. Install GUI Python dependencies](#2-install-gui-python-dependencies)
  - [3. Install `vscmnet2`](#3-install-vscmnet2)
  - [4. Install `spatial_correlation_sampler`](#4-install-spatial_correlation_sampler)
  - [5. Install external tools](#5-install-external-tools)
- [Launching the GUI](#launching-the-gui)
- [Interface Guide](#interface-guide)
  - [Dashboard](#dashboard)
  - [Tab 1 — Extraction](#tab-1--extraction)
  - [Tab 2 — Colorization](#tab-2--colorization)
  - [Tab 3 — Encode / Merge](#tab-3--encode--merge)
  - [Tab 4 — Fix Image](#tab-4--fix-image)
  - [Tab 5 — Fix Colors](#tab-5--fix-colors)
  - [Tab 6 — Fix Video](#tab-6--fix-video)
- [Workflow: Step by Step](#workflow-step-by-step)
  - [Step 1: Extract Reference Frames](#step-1-extract-reference-frames)
  - [Step 2: Colorize Frames (AI)](#step-2-colorize-frames-ai)
  - [Step 3: Encode Video](#step-3-encode-video)
  - [Step 4: Merge (optional)](#step-4-merge-optional)
- [Understanding the Merge Step](#understanding-the-merge-step)
- [Settings Persistence](#settings-persistence)
- [Credits](#credits)

---

## Pipeline Overview

```
Original Video
      │
      ▼
 Step 1: EXTRACT
 (VapourSynth → vscmnet2 → reference frames in ref_tht10/)
      │
      ▼
 Step 2: COLORIZE
 (RPC → HAVC DiT Server → colorized frames in ref_qwen/)
      │
      ▼
 Step 3: ENCODE
 (VapourSynth → vscmnet2 → x265 or NVEnc → .h265 video)
      │
      ▼
 Step 4: MERGE (optional)
 (VapourSynth → vscmnet2 → blended .h265 → .mkv)
```

Each step can be toggled on/off independently from the Dashboard. For example,
if reference frames are already extracted you can skip Step 1 and run only
Steps 2–4.

---

## System Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10 / 11 (64-bit) |
| **Python** | 3.12 |
| **GPU** | RTX 30 / 40 / 50 (same as the DiT server) |
| **Tools** | VapourSynth R74, x265, NVEncC, MKVToolNix |
| **Server** | `dit_rpc_server.py` must be running (see [main README](../README.md)) |

The GUI and the server can run on the **same machine** (localhost) or on
**different machines** — just point the RPC host field to the server's IP.

---

## Installation

All packages must be installed in the **same `.venv`** already created for the
DiT RPC server. If you haven't set up the server yet, follow the
[main README](../README.md) first.

### 1. Activate the shared virtual environment

```powershell
# From the project root (HAVCServerDiT)
.venv\Scripts\activate
```

### 2. Install GUI Python dependencies

```powershell
pip install -r GUI\requirements.txt
```

This installs:

- **Pillow** — image loading and preview
- **FreeSimpleGUI** — GUI toolkit (PySimpleGUI fork)
- **VapourSynth R74** — video frameserver bindings
- **send2trash** — safe file deletion
- **tkinter_embed** — tkinter integration for FreeSimpleGUI

### 3. Install `vscmnet2`

The `vscmnet2` package provides the VapourSynth functions used by Steps 1, 3,
and 4 (scene-change detection, edge-aware frame extraction, color merging,
and encoding). It is available from [github.com/dan64/vs-cmnet2](https://github.com/dan64/vs-cmnet2):

```powershell
pip install packages\vscmnet2-1.0.3-py3-none-any.whl
```

To complete the installation of this filter is necessary to install the models, weights and plugins, as described in the filter home page: [vs-cmnet2](https://github.com/dan64/vs-cmnet2#installation)

### 4. Install `spatial_correlation_sampler`

This is a compiled extension (PyTorch 2.10 + CUDA 13.0) of
[Pytorch-Correlation-extension](https://github.com/ClementPinard/Pytorch-Correlation-extension),
required by `vscmnet2` for temporal alignment during encoding:

```powershell
pip install packages\spatial_correlation_sampler-0.5.0-cp312-cp312-win_amd64.whl
```

> The wheel is pre-built for **Python 3.12 / PyTorch 2.10+cu130 / Windows x64**.
> It will only work with that exact combination.

### 5. Install external tools

The GUI relies on three command-line tools that must be present on disk
(they are **not** Python packages):

| Tool | Purpose | Default location | Download |
|------|---------|------------------|----------|
| **VapourSynth** | Video frameserver | Bundled in the `.venv` | `pip install VapourSynth==74` |
| **x265** | H.265 software encoder | `GUI/tools/x265/x265.exe` | [x265 downloads](https://www.videolan.org/developers/x265.html) |
| **NVEncC** | NVIDIA GPU encoder | `GUI/tools/NVEncC/NVEncC64.exe` | [rigaya/NVEnc](https://github.com/rigaya/NVEnc/releases) |
| **MKVToolNix** | `.h265` → `.mkv` muxing | `GUI/tools/MKVToolNix/mkvmerge.exe` | [MKVToolNix](https://mkvtoolnix.download/) |

> **Quick setup with Release 1.0.0**: the project's [Release 1.0.0](https://github.com/dan64/HAVCServerDiT/releases/tag/v1.0.0)
> includes a `tools.zip` archive containing `x265.exe` and `mkvmerge.exe`.
> Download it and extract its contents directly into `GUI/tools/` so that the
> default paths match without any additional configuration:
>
> ```
> GUI/tools/
> ├── x265/
> │   └── x265.exe
> ├── MKVToolNix/
> │   └── mkvmerge.exe
> ├── NVEncC/        (download separately)
> └── ...
> ```
>
> You can also place these tools anywhere — just point the GUI to their paths
> in the **Encode/Merge** tab.

---

## Launching the GUI

### From the command line

```powershell
# Activate the venv first
.venv\Scripts\activate
python GUI\CMNET2_colorize_client_GUI.py
```

### From the launcher (silent, no console)

Double-click `GUI/run_colorize_client_GUI.vbs`. This runs the `.cmd` wrapper
in a hidden console, so no Terminal window stays open.

### Desktop shortcut (optional)

You can create a desktop shortcut to launch the GUI without ever seeing a
command prompt:

1. Right-click on the desktop → **New → Shortcut**
2. For the location, enter the full path to the `.vbs` file:
   ```
   D:\PProjects\HAVCServerDiT\GUI\run_colorize_client_GUI.vbs
   ```
3. Click **Next**, give the shortcut a name (e.g. *CMNET2 Colorize Client*)
4. Click **Finish**

To change the shortcut's icon:

1. Right-click the new shortcut → **Properties**
2. Click **Change Icon...**
3. Browse to any `.ico` file on your system (or download one you like)
4. Click **OK** twice

The shortcut launches the GUI silently – the VBScript runs the `.cmd` wrapper
in a hidden window.

---

### Before using .cmd / .vbs launcher

The launcher auto-detects the Python interpreter in this order:

1. **Explicit `PYTHON_EXE`** – set it in `GUI/run_colorize_client_GUI.cmd` if
   you use a custom environment
2. **`.venv` in the project root** – looks for
   `.venv\Scripts\python.exe` one level above `GUI/`
3. **`python` from PATH** – fallback

If you use a non-standard environment location, edit `PYTHON_EXE` in the
**USER CONFIGURATION** block at the top of `run_colorize_client_GUI.cmd`:

```batch
set PYTHON_EXE=C:\Users\YourName\.conda\envs\my-env\python.exe
```

---

## Interface Guide

The GUI has seven tabs plus a persistent status bar at the bottom.

### Dashboard

![GUI Dashboard](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page1.jpg)

- **Task checkboxes**: enable/disable each pipeline step
- **START PIPELINE**: runs the selected steps sequentially
- **STOP**: gracefully interrupts the current step (sends stop signal to both
  subprocesses and the RPC server)
- **Progress bar**: shows overall completion percentage
- **Log window**: live output from VapourSynth, x265/NVEnc, and the RPC client
- **Shutdown PC when finished**: triggers `shutdown /s /t 60` after completion

### Tab 1 — Extraction

![GUI Tab #1](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page2.jpg)

| Setting | Description |
|---------|-------------|
| **VapourSynth Pipe** | Path to `vspipe.exe` (bundled in `.venv`) |
| **Script Directory** | Folder containing the `.vpy` scripts (`GUI/scripts/`) |
| **Extract VPY** | VapourSynth script for frame extraction |
| **Threshold / tht_ssim / min_int / mult/freq** | Scene-change detection parameters |
| **Ref Override** | Force re-extraction even if reference frames exist |
| **Duplicate first frame** | Copies the second extracted frame to `ref_000000.jpg` (useful for frame 0 coverage) |
| **Video Directory** | Folder containing the video to process |
| **Select Video** | Dropdown populated from the video directory |

After selecting a video, the **Video Technical Details** panel shows
resolution, FPS, frame count, and pixel format.

### Tab 2 — Colorization

![GUI Tab #2](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page3.jpg)

| Setting | Description |
|---------|-------------|
| **RPC Host / Port** | Server address (default: `127.0.0.1:8765`) |
| **Connect button + LED** | Tests the RPC connection with a ping |
| **Model / Precision / Rank / Steps** | Pipeline configuration sent to the server |
| **Colorization Steps** | Diffusion steps per frame (lower = faster) |
| **Fast Pipeline** | Enables **paired inference**: two frames colorized in one forward pass (~2× faster, temporally consistent) |
| **Prompt** | Text prompt sent to the model |
| **Cache Directory** | HuggingFace cache (leave empty for default) |

The two image panels show a live preview of the B&W input and the AI output
as frames are processed.

### Tab 3 — Encode / Merge

![GUI Tab #3](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page4.jpg)

| Setting | Description |
|---------|-------------|
| **MKVmerge Path** | Path to `mkvmerge.exe` |
| **x265 Path** | Path to `x265.exe` (also used to locate NVEncC) |
| **Encode VPY** | VapourSynth script for encoding |
| **CRF** | x265 quality (lower = better, typical: 18–24) |
| **FPS** | Output frame rate |
| **Encoder** | `x265` (software) or `Nvenc` (GPU hardware) |
| **Memory Frames** | Max frames buffered by VapourSynth |
| **Render Speed** | VapourSynth render preset (`auto`, `fast`, `medium`, `slow`, `slower`) |
| **Merge Weight** | Blend ratio for Step 4 (0.30 = 30% original, 0.75 = 75% original) |
| **VBR Quality** | NVEnc quality target (lower = better) |
| **NVEnc Sharpness** | Enables `--vpp-unsharp --vpp-edgelevel` on NVEnc |

### Tab 4 — Fix Image

![GUI Tab #4](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page5.jpg)

A standalone image colorization tab independent of the video pipeline.
Supports both SHM (same-host) and PNG-over-RPC (remote server) transport.

| Control | Description |
|---------|-------------|
| **Colorization Steps** | Inference steps (default: 2) |
| **Convert in B&W before colorization** | Check/Unchek if you want to colorize/fix an image already colorized |
| **Prompt** | Text prompt for the model |
| **Max** | Max prompts history size |
| **Delete** | Delete current prompt from history list |
| **Clear** | Clear the prompt's history list |
| **Load Image** | Load image from drag-and-drop or Browser button (via `load_image_DtD_GUI.py`) |
| **Colorize** | Run colorization with fixed seed (42) |
| **Colorize (Random)** | Run colorization with random seed for variation |
| **Overwrite** | Overwrite the last loaded image with last colorized image | 
| **Save As...** | Save the colorized result (PNG / JPG) |
| **Swap Output** | Copy the output image as input image for the next colorization |

The input image is previewed scaled to 370×350 pixels; the full-resolution
output is stored in memory and saved to disk via the **Save As...** button.

> **Prerequisite**: the HAVC DiT Server must be connected (Tab 2 — Connect).

### Tab 5 — Fix Colors

![GUI Tab #5](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page6.jpg)

A standalone image colorization tab that uses the local **CMNET2** model
(exemplar-based color propagation) instead of the DiT RPC server. It
colorizes a B&W target image using a color reference image as context.

| Control | Description |
|---------|-------------|
| **Reference Image (Color)** | Load a color reference image (drag & drop or Browse) that provides the color palette |
| **Target Image (B&W)** | Load the B&W image to colorize (drag & drop or Browse) |
| **Colorize** | Run CMNET2 colorization in a background thread. The first call loads the model (~5–10 s); subsequent calls reuse it (~1–2 s) |
| **Overwrite** | Overwrite the original target file with the colorized result |
| **Save As...** | Save the colorized result to a new file (PNG / JPG) |
| **Copy → Fix Image** | Copy the colorized output as the input image for Tab 4 (Fix Image), enabling a two‑stage pipeline: CMNET2 → DiT RPC |

Three preview panels show the reference, target, and colorized output
side‑by‑side (250×240 px each). Full‑resolution images are always preserved
in memory; resizing only applies to the previews.

> **Prerequisite**: `vscmnet2` must be installed and model weights/checkpoints
> must be present (see [Installation](#3-install-vscmnet2)).
> No RPC connection required — CMNET2 runs entirely on the local GPU.

### Tab 6 — Fix Video

![GUI Tab #6](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page7.jpg)

A standalone video recoloring tab that runs a VapourSynth + NVEnc pipeline
using the selected video, encode script, and two reference images.

| Control | Description |
|---------|-------------|
| **Video Directory** | Folder containing the video to recolor |
| **Select Video** | Dropdown populated from the video directory |
| **Encode VPY** | VapourSynth script for encoding / recoloring (script: encode_cmnet2_recolor.vpy) |
| **FPS** | Output frame rate |
| **VBR Quality** | NVEnc quality target (lower = better) |
| **Memory Frames** | Max frames buffered by VapourSynth |
| **Render Speed** | VapourSynth render preset (`auto`, `fast`, `medium`, `slow`, `slower`) |
| **First Reference** | Load a reference image (drag & drop or Browse) for the start of the clip |
| **Last Reference** | Load a reference image (drag & drop or Browse) for the end of the clip |
| **Recolor** | Runs the VapourSynth → NVEnc pipeline in a background thread |

The two reference images guide the recoloring script: they are passed to the
VapourSynth script as `RefStart` and `RefEnd` parameters. The `RefDir`
parameter is automatically set to the folder containing the first reference
image. Only the frames between **RefStart / RefEnd** will be recolored. 

**Startup check**: before launching, the tab verifies that `NVEncC64.exe` exists
next to `x265.exe` (derived from the x265 path configured in Tab 3). If
missing, an error popup instructs the user to install NVEncC in `tools\NVEncC`.

The output file is named `[video]_cmnet2_dt-recolor.mkv` and is saved in the
video directory. The `.h265` intermediate is automatically converted to `.mkv`
via mkvmerge and deleted. A log file `[video]_dt-recolor_log.txt` (or
`_cmnet2_dt-recolor_log.txt`) is also written to the same directory with the
full session output.

> **Important**: this tab uses **NVEnc only** — the x265 software encoder is
> not available here. NVEncC64.exe must be installed.

---

## Workflow: Step by Step

### Step 1: Extract Reference Frames

VapourSynth reads the video through `vscmnet2` and runs scene-change
detection (`sc_algo=1`). Keyframes that differ significantly from their
neighbors are exported as JPEG images to `ref_tht10/`.

The extraction parameters control how aggressively frames are selected:

- **threshold** (`sc_threshold`): sensitivity — lower = more frames
- **tht_ssim** (`sc_tht_ssim`): SSIM threshold for scene-change
- **min_int** (`sc_min_int`): minimum frame interval between selections
- **mult/freq** (`sc_mult_tht`): minimum frequency multiplier

### Step 2: Colorize Frames (AI)

The GUI connects to the HAVC DiT Server and sends each extracted frame for
colorization. Results are saved to `ref_qwen/`.

Two modes are available:

- **Standard**: each frame is sent individually
- **Fast Pipeline** (paired inference): two frames are placed side-by-side
  and colorized in a single forward pass. This is faster and produces
  temporally-consistent results between adjacent frames.

The server's pipeline is loaded on demand (if not already loaded at boot).

### Step 3: Encode Video

VapourSynth reads the original video and the colorized frames from
`ref_qwen/`, then `vscmnet2` overlays the color onto the original luminance
channel. The result is piped to the chosen encoder.

| Encoder | Pros | Cons |
|---------|------|------|
| **x265** | Higher quality, fine CRF control | Slower (CPU-bound) |
| **NVEnc** | Fast (GPU), VBR quality control | Requires NVIDIA GPU |

The output is a `.h265` raw video stream. If MKVToolNix is configured, a
`.mkv` container is created automatically and the raw `.h265` is deleted.

### Step 4: Merge (optional)

This step **only makes sense when the original video clip is already
colorized** (e.g., a previous colorization pass or a naturally color source).

VapourSynth reads both the original color clip and the newly encoded DiT
clip, then blends them using `vscmnet2.vs_merge`:

```
output = (DiT clip × (1 - weight)) + (original color clip × weight)
```

The **Merge Weight** slider (0.30–0.74) controls how much of the original
color clip is kept:

| Weight | Effect |
|--------|--------|
| 0.30 | 30% original color, 70% DiT — DiT look dominates |
| 0.50 | 50/50 — balanced blend |
| 0.74 | 74% original color, 26% DiT — original colors dominate |

> If the original clip is black-and-white, **disable Step 4**.
> Blending a B&W clip with a colorized one only desaturates the result.

The merged output is saved as `[video]_cmnet2_dt-color_merged.mkv`.

---

## Understanding the Merge Step

The merge is a **luminance-guided chroma blend**: the `vscmnet2.vs_merge`
function takes the chroma from the DiT-colorized clip and the chroma from the
original color clip, then blends them according to the weight parameter while
keeping the original luma channel.

This is useful when:

- You have a **manually colorized** version of the clip and you want to see
  which parts the AI interprets differently
- You want to **tone down** the AI's color choices by mixing in a known-good
  reference
- You want to **compare** the AI output against a baseline by creating a
  50/50 split

---

## Settings Persistence

All GUI settings are saved to `gui_cmnet2_settings.json` in the `GUI/` folder
when you click **Save Global Settings**. The file is loaded automatically at
startup and includes:

- Tool paths (VapourSynth, x265, MKVToolNix)
- Script directory and script filenames
- Model configuration (name, precision, rank, steps)
- Extraction parameters
- Encoding parameters (CRF, FPS, encoder choice)
- Merge weight and VBR quality
- Fix Colors reference/target image paths
- RPC host and port
- Window size

---

## Credits

- **CMNET2 / vscmnet2**: [github.com/dan64/vs-cmnet2](https://github.com/dan64/vs-cmnet2) — VapourSynth color-matching and scene-detection functions
- **spatial_correlation_sampler**: [Pytorch-Correlation-extension](https://github.com/ClementPinard/Pytorch-Correlation-extension) — GPU correlation layer used by vscmnet2
- **DiT Model**: [Qwen/Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)
- **VapourSynth**: [vapoursynth.com](https://www.vapoursynth.com/)
- **x265**: [videolan.org](https://www.videolan.org/developers/x265.html)
- **NVEncC**: [rigaya/NVEnc](https://github.com/rigaya/NVEnc)
- **MKVToolNix**: [mkvtoolnix.download](https://mkvtoolnix.download/)
