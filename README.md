# HAVC Server DiT

Hybrid Automatic Video Colorizer (HAVC) server that exposes a GPU-accelerated colorization pipeline for black-and-white images and video frames based on Diffusion Transformer (DiT) models.

6 backends, one API : pick the one that fits your hardware:

- **nunchaku-qwen**: SVDQuant FP4/INT4 transformer via [Nunchaku](https://github.com/nunchaku-ai/nunchaku) : **4 sec/frame**¹, requires RTX 30/40/50 (16GB+ VRAM, 64GB RAM) & CUDA 13.0
- **gguf-qwen**: Qwen-Image-Edit 2511 (native int8 ConvRot or GGUF Q3_K_S) : **~7.3 sec/frame**¹ (Fast Pipeline) or ~10.5 sec/frame, runs on RTX 30/40/50 (12GB+ VRAM with Q3_K_S, 16GB+ with int8; 32GB+ RAM with Q3_K_S, 48GB+ with int8), zero ComfyUI GUI dependency
- **longcat-gguf**: [LongCat-Image-Edit-Turbo](https://huggingface.co/meituan-longcat/LongCat-Image-Edit-Turbo) GGUF pipeline (Q3_K_M–Q8_0) : **~12 sec/frame**², runs on RTX 30/40/50 (12GB+ VRAM, 32GB+ RAM), better image quality than gguf-qwen, zero ComfyUI GUI dependency
- **qwen21-viggle**: Qwen-Image-2.1 (native ComfyUI int8 ConvRot UNet) + [Viggle-Turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo) LoRA : **~1.7 sec/frame**¹ (Fast Pipeline) or ~3.5 sec/frame — the fastest backend, with the lowest minimum requirements (**12 GB VRAM / 32 GB RAM**) thanks to Dynamic VRAM and the text-encoder split — the other 12 GB-class options run at ~7–12 sec/frame; runs on RTX 30/40/50 (14GB+ VRAM on the standard path; 12GB with Fast Pipeline; 32GB+ RAM), optional `enhance_prompt` (Qwen3-VL image-aware prompt rewriting)
- **qwen21-turbo**: Qwen-Image-2.1-Turbo (native ComfyUI int8 ConvRot UNet) : **~4.5 sec/frame**¹ (single split) or **~2.3 sec/frame** with the paired split (`fast_split_TE`), runs on RTX 30/40/50 (14GB+ VRAM; 12GB with Fast Pipeline; 32GB+ RAM), richer colors than qwen21-viggle but less stable between similar frames — the shipped default stays qwen21-viggle
- **flux2**: FLUX.2-dev + Mistral-3 text encoder + FLUX.2 **small-decoder** VAE, Flux.2 Turbo LoRA : **~4.0 sec/frame**¹ (paired split, int4 ConvRot) or **~5.5 sec/frame** (fp8 mixed; the Q2/Q3 GGUF variants are lighter but slower), runs on RTX 30/40/50 (16GB+ VRAM, 64GB+ RAM). The int4 config sets `"vram_headroom": 3` for 16 GB cards — **0 on 12 GB and 24 GB+** cards, see [docs/backends.md](docs/backends.md)

> ¹ Measured with **Fast Pipeline** — the cached text-encoder split for `qwen21-viggle`, `qwen21-turbo` (the ~2.3 s/frame figure: its paired `fast_split_TE` variant), `gguf-qwen` and `flux2` (paired for `qwen21_turbo-fast_int8` and all the `flux2` configs), paired inference for `nunchaku-qwen`. ² `longcat-gguf` has no Fast Pipeline path — single-image time, not directly comparable. Steady-state per-frame times, warm-up excluded; the `gguf-qwen` figure comes from a 17-frame test at 2 steps. Speed/hardware/quality trade-offs, the recommended picks and the full measurement notes: **[docs/backends.md](docs/backends.md)**.

## 📥 Install

**Installer (recommended)** — download `HAVC-Setup-<version>.exe` from the [Releases](https://github.com/dan64/HAVCServerDiT/releases) page and run it: a single self-contained file (no .NET runtime needed) that installs the pinned Python runtime, the server stack, the GUI, external tools and the vs-cmnet2 plugins/weights — and keeps everything updated (*Check for updates*, *Repair*, *Uninstall* from the manager). Model weights are downloaded on first use and preserved across updates. Details: [docs/installation.md](docs/installation.md).

> ⚠️ Windows **SmartScreen** will warn on first run because the exe is not code-signed: *More info* → *Run anyway*. The sha256 of every asset is published in the release notes.

**Manual installation (advanced)** — clone the repository and run `install.cmd` (requires Git + Python 3.12): step-by-step instructions in [docs/installation.md](docs/installation.md#manual-installation).

## 🚀 Quick start

From the install folder (or the repository root on a manual install):

```
HAVC.vbs               # desktop GUI (the recommended front-end)
HAVC-Server.cmd        # console server — optional arg: alias or config name (no arg: int4)
start_server.cmd q3    # console server with a backend/quantization or a config name
```

CLI arguments, the full launch-script reference and the suggested inference steps: [docs/server_usage.md](docs/server_usage.md).

## 📋 Requirements

- Windows 10/11, NVIDIA RTX 30/40/50 GPU, CUDA 13.0+
- VRAM / RAM by backend: **nunchaku-qwen** 16 GB+ / 64 GB+ · **gguf-qwen** 12 GB+ (`qwen-2511_q3`) or 16 GB+ (`qwen-2511_int8`) / 32 GB+ (`qwen-2511_q3`) or 48 GB+ (`qwen-2511_int8`) · **longcat-gguf** 12 GB+ / 32 GB+ · **qwen21-viggle** / **qwen21-turbo** 14 GB+ (12 GB+ with Fast Pipeline) / 32 GB+ · **flux2** 16 GB+ / 64 GB+ — [details](docs/backends.md)
- Disk: a few GB for the software stack; model weights (up to tens of GB for the largest configs) are downloaded on first use

## ✨ Features

- 📦 **6 backends, one API** : nunchaku-qwen (FP4/INT4, 4 sec/frame), gguf-qwen (Qwen-Image-Edit 2511: native int8 ConvRot or Q3_K_S, ~7.3 sec/frame with Fast Pipeline) and longcat-gguf (Q3, …, Q8) for lower VRAM, qwen21-viggle (int8 ConvRot UNet, **fastest**: ~1.7 sec/frame with Fast Pipeline, 12 GB VRAM / 32 GB RAM minimum) with optional Qwen3-VL prompt rewriting, qwen21-turbo (Qwen-Image-2.1-Turbo, ~2.3 sec/frame with the paired split) for the richest colors, flux2 (FLUX.2-dev with the Turbo LoRA, ~4.0 sec/frame int4 / ~5.5 fp8 with the paired split) for FLUX-family colors
- 🎨 **Batch colorization** : process entire directories of B&W images via filesystem paths
- 🖼️ **Paired inference** : colorize two images in a single forward pass (faster, temporally consistent)
- 📡 **In-memory RPC** : pass raw PNG frames over XML-RPC without touching the filesystem (ideal for video pipelines)
- ⚡ **4-step lightning model** : SVDQuant FP4 quantized transformer for maximum throughput
- 🔒 **Thread-safe** : pipeline loading and stop control are protected by locks; every RPC call runs in its own thread
- ⚙️ **Startup preload** : optional `--load-pipeline` flag loads the model at boot from a JSON config file
- 🚀 **Shared memory transport** : zero-copy image transfer for same-host deployments (~23% faster than standard RPC)

---

## 📚 Documentation

- [Installation](docs/installation.md) — installer, manual setup, updating, project layout
- [Backends & requirements](docs/backends.md) — choosing the right backend
- [Server usage](docs/server_usage.md) — server startup, launch scripts, CLI arguments, suggested steps
- [Pipeline configuration](docs/configuration.md) — config files and key reference
- [RPC API](docs/rpc-api.md) — XML-RPC API, example clients, shared-memory transport
- [GUI usage](docs/gui_usage.md) — the desktop client
- [Troubleshooting](docs/troubleshooting.md)
- [What's New](docs/whats-new.md) — changelog

## 🔗 Credits

- **Model**: [Qwen/Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511), [Qwen/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1), [LongCat-Image-Edit-Turbo](https://huggingface.co/meituan-longcat/LongCat-Image-Edit-Turbo), [FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev) + [FLUX.2-small-decoder](https://huggingface.co/black-forest-labs/FLUX.2-small-decoder) (Black Forest Labs)
- **Flux.2 Turbo LoRA**: [Comfy-Org/flux2-dev](https://huggingface.co/Comfy-Org/flux2-dev) · int4 ConvRot community repack: [Winnougan/INT4-Convrot-Comfy-Models](https://huggingface.co/Winnougan/INT4-Convrot-Comfy-Models)
- ****VapourSynth filter for video colorization with CMNET2****: [vs-cmnet2](https://github.com/dan64/vs-cmnet2)
- **Viggle-Turbo LoRA**: [Viggle/Qwen-Image-2.1-viggle-turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo)
- **Nunchaku quantization**: [Nunchaku / SVDQuant](https://github.com/mit-han-lab/nunchaku)
- **GGUF dequantization kernels**: adapted from [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) (Apache 2.0), Qwen3-VL mmproj support from the [ComfyUI-GGUF-Reboot](https://github.com/molbal/ComfyUI-GGUF) fork (molbal)
- **Pipeline**: [Hugging Face Diffusers](https://github.com/huggingface/diffusers)
