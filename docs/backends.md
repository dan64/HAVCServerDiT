# Backends

Four backends, one API — pick the one that fits your hardware.

> ¹ Measured with **Fast Pipeline** (paired inference, two frames per forward pass) at the backend's fastest recommended step count. ² `gguf-qwen`/`longcat-gguf` don't support paired inference (fall back to per-image processing, see [What's New](whats-new.md)) — their figure is a genuine single-image time, not directly comparable to the Fast Pipeline figures above.

> **Recommended**: **nunchaku-qwen** and **qwen21-viggle** are both recommended for production use, nunchaku-qwen at the fastest usable step count (`steps=2`) has an inference speed of about **4 sec/frame** using _Fast Pipeline_, **qwen21-viggle** at fastest usable step count (`steps=2`) has an inference speed of about **8 sec/frame**; using _Fast Pipeline_ the speed improves to about **6 sec/frame** (not 4 — the pair-mode working resolution was deliberately raised for this backend to avoid a color artifact, see the `⚠️ Fast Pipeline` note below). `qwen21-viggle` needs meaningfully less hardware (14GB+ VRAM / 32GB+ RAM vs. 16GB+ VRAM / 64GB+ RAM). `longcat-gguf` remain the choice for VRAM-constrained setups where neither of the above fits, at a real speed cost (see the `⚠️ Experimental` note under GGUF below).
>
> ⚠️ **Fast Pipeline + `qwen21-viggle`**: paired inference uses a higher working resolution for this backend specifically (`1280` vs. `1024` for single images and for the other backends, since [What's New](whats-new.md) 2026-09-27) — this fixes a color artifact previously seen on fine detail near the merge boundary (e.g. a hand rendered in tones close to the surrounding foliage), at the cost of some speed (~6 sec/frame instead of 4). A milder residual effect can still appear on secondary, color-ambiguous details (e.g. a flower's petals taking a noticeably different but still plausible hue between runs) — not a defect on the same order as the original artifact, more of the same color-hedging behavior described elsewhere in this README. The [Viggle-Turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo) LoRA is still an experimental release, and this residual effect may be a limitation of the LoRA itself. If maximum consistency matters more than speed, disable _Fast Pipeline_ for `qwen21-viggle` (~8 sec/frame, no longer speed-competitive with `nunchaku-qwen`) or spot-check the output before a long batch run.
>
> **Color stability vs. variety**: based on real-world use across thousands of frames, `nunchaku-qwen` tends to show more color variability between similar frames — can look more vivid, but with weaker frame-to-frame consistency — while `qwen21-viggle` is more conservative in its color choices and more stable, likely a consequence of the Viggle-Turbo LoRA's aggressive step-distillation, which tends to narrow the range of plausible outputs toward "safe" choices. For video work, where flickering color between consecutive frames is a visible defect, this makes `qwen21-viggle`'s conservatism a practical advantage rather than just a stylistic difference — worth factoring in alongside the speed/hardware trade-offs above. The same pattern shows up specifically in _Fast Pipeline_ (paired inference): when both frames share an object, `qwen21-viggle` consistently colors it the same way in both halves, while `nunchaku-qwen` is less reliable at this — the exact cause (the LoRA itself vs. something more general about the two pipelines) is not established.

## Requirements by backend

Choose the backend that matches your hardware:

### nunchaku-qwen : 4 sec/frame (FP4/INT4)

| Requirement      | Details                            |
| ---------------- | ---------------------------------- |
| **GPU**          | NVIDIA RTX 30/40/50  (16 GB+ VRAM) |
| **RAM**          | 64 GB+                             |
| **CUDA**         | 13.0 or newer                      |
| **CUDA Toolkit** | Must match the PyTorch build       |

> **RTX 30/40-Series (Ampere / Ada)**: use `"model_precision": "int4"`. FP4 requires Blackwell (RTX 50).
> Requires Nunchaku 1.2.1 and `diffusers==0.37.0.dev0` (wheel published in the release assets).

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

### longcat-gguf : 12 sec/frame (Q3–Q8) — Best Quality

| Requirement | Details                            |
| ----------- | ---------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (12 GB+ VRAM) |
| **RAM**     | 32 GB+                             |
| **CUDA**    | 13.0+                              |

> LongCat-Image-Edit-Turbo delivers noticeably better colorization than the
> gguf-qwen model — richer colors, more natural skin tones, and better
> detail preservation — at the same ~12 s/frame speed.
> 
> Uses GGUF quantized UNet (Q3_K_M to Q8_0) + CLIP Q4_K_M. The UNet is
> distributed in five quantization levels to fit different VRAM budgets.
> All files are auto-downloaded on first run.
> 
> See `config/longcat_gguf_q*.json` — the general rule: lower quant = less VRAM.
> Launch with `run_server_longcat.cmd` (Q4_K_M) or `start_server.cmd longcat|longcat-q3|...`.

### qwen21-viggle : ~8-11 sec/frame (Qwen-Image-2.1 int8 ConvRot)

| Requirement | Details                            |
| ----------- | ----------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (14 GB+ VRAM) |
| **RAM**     | 32 GB+                             |
| **CUDA**    | 13.0+                              |

> Native ComfyUI int8 ConvRot weights for the **UNet** (not GGUF — a GGUF
> UNet was evaluated but is ~2× slower for this model). The **CLIP/text
> encoder**, unlike the UNet, uses GGUF+mmproj by default (`Qwen3-VL-8B-
> Instruct-UD`, see [What's New](whats-new.md)) — a `.safetensors` CLIP
> (`int8_convrot`/`w4a8`) remains a valid, simpler alternative, see
> [Pipeline Configuration](configuration.md). Requires
> `comfy-kitchen==0.2.35` and `comfy-aimdo==0.5.5` exactly (pinned, not a
> minimum — both are compiled packages and an untested newer build is not
> assumed safe). A fresh `install.cmd` run sets these; an **existing**
> `.venv` needs an explicit upgrade, see [Quick Update](installation.md#-quick-update-existing-installation).
> All files are auto-downloaded on first run — see [What's New](whats-new.md).
> Launch with `run_server_qwen21.cmd`.

### All backends

| Requirement | Details                |
| ----------- | ---------------------- |
| **OS**      | Windows 10/11 or Linux |
| **Python**  | 3.12                   |
