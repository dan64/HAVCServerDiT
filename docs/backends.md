# Backends

Four backends, one API — pick the one that fits your hardware.

> ¹ Measured with **Fast Pipeline** — for `qwen21-viggle` and `gguf-qwen` the cached text-encoder split, for `nunchaku-qwen` paired inference (two frames per forward pass) — at the backend's fastest recommended step count, warm-up excluded. ² `longcat-gguf` has no Fast Pipeline path (falls back to per-image processing, see [What's New](whats-new.md)) — its figure is a genuine single-image time, not directly comparable to the Fast Pipeline figures above.

> **Recommended**: **nunchaku-qwen** and **qwen21-viggle** are both recommended for production use, nunchaku-qwen at the fastest usable step count (`steps=2`) has an inference speed of about **4 sec/frame** using _Fast Pipeline_, **qwen21-viggle** at fastest usable step count (`steps=2`) has an inference speed of about **6 sec/frame**; using _Fast Pipeline_ the speed improves to about **3 sec/frame** (the cached text-encoder split, see the `⚠️ Fast Pipeline` note below). `qwen21-viggle` needs meaningfully less hardware (14GB+ VRAM / 32GB+ RAM vs. 16GB+ VRAM / 64GB+ RAM; with _Fast Pipeline_ it runs in **12 GB** of VRAM). **`gguf-qwen`** (Qwen-Image-Edit 2511) now also supports the cached-TE split: **~7.3 sec/frame** against ~10.5 sec/frame for the standard path (~1.4×, 17-frame test at 2 steps), on a 16 GB+ GPU / 48 GB+ RAM for the recommended `qwen-2511_int8` config (12 GB+ with `qwen-2511_q3`). `longcat-gguf` remain the choice for VRAM-constrained setups where neither of the above fits, at a real speed cost (see the `⚠️ Experimental` note under GGUF below).
>
> ⚠️ **Fast Pipeline + `qwen21-viggle`** (2.4.0): this backend no longer uses paired inference — _Fast Pipeline_ runs a **cached text-encoder split**: each frame's text-encoder conditioning is computed once and cached, then the sampling runs with the UNet resident, in chunks of 200 frames (~**3 sec/frame**, roughly 2× the standard path). There is no merge boundary, nor the paired-mode resolution trade-off it required. A chunk's cache is deleted once its frames are colorized, and a cancelled run resumes from the first missing frame. In standard (non-Fast) mode the single-frame path runs at about **6 sec/frame**. On secondary, color-ambiguous details (e.g. a flower's petals) a run can still land on a noticeably different but plausible hue — the color-hedging behavior described above, not a defect. The [Viggle-Turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo) LoRA is still an experimental release: spot-check the output before a long batch run.
>
> **Color stability vs. variety**: based on real-world use across thousands of frames, `nunchaku-qwen` tends to show more color variability between similar frames — can look more vivid, but with weaker frame-to-frame consistency — while `qwen21-viggle` is more conservative in its color choices and more stable, likely a consequence of the Viggle-Turbo LoRA's aggressive step-distillation, which tends to narrow the range of plausible outputs toward "safe" choices. For video work, where flickering color between consecutive frames is a visible defect, this makes `qwen21-viggle`'s conservatism a practical advantage rather than just a stylistic difference — worth factoring in alongside the speed/hardware trade-offs above. The same pattern showed up in paired inference (which `qwen21-viggle` used before 2.4.0 and `nunchaku-qwen` still uses): when both frames of a pair shared an object, `qwen21-viggle` consistently colored it the same way in both halves, while `nunchaku-qwen` is less reliable at this — the exact cause (the LoRA itself vs. something more general about the two pipelines) is not established.

> **Color stability, qwen21-turbo vs qwen21-viggle** (field verdict, 2026-10-11): the turbo family colors *better* — richer, often more accurate hues — but with noticeably more variability between similar frames; over a whole film that reads as visible color flicker and outweighs the better rendition. Its paired variant (`qwen21_turbo-fast_int8`, `fast_split_TE`) is a middle ground, though some frames come out almost black-and-white. `qwen21-viggle` at **2 steps** therefore stays the nominal default — the best speed / quality / stability trade-off.

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

### qwen-2511 (gguf-qwen) : ~7.3 sec/frame with Fast Pipeline, ~10.5 without (int8 ConvRot 16 GB+ / Q3_K_S 12 GB+)

| Requirement | Details                                |
| ----------- | -------------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (12 GB+: `qwen-2511_q3`; 16 GB+: `qwen-2511_int8`) |
| **RAM**     | 32 GB+ (`qwen-2511_q3`); 48 GB+ (`qwen-2511_int8` — streams through system RAM) |
| **CUDA**    | 13.0+ (or CPU-only: slower, zero VRAM) |

> **`qwen-2511_int8`** is the recommended config: the official Comfy-Org int8
> ConvRot checkpoint, loaded through the native UNet loader — the int8 kernels
> run natively instead of the GGUF per-op dequant, so it is measurably faster
> per frame than the GGUF quants.
> **`qwen-2511_q3`** (GGUF Q3_K_S) is the low-VRAM option for 12 GB-class GPUs;
> on fine details it shows the quant's artifacts — in a side-by-side run the
> character's expression visibly shifted (a smile appeared), and the int8
> checkpoint was clearly ahead overall. Use it only when VRAM rules out
> `qwen-2511_int8`.
>
> **Fast Pipeline is supported** (cached-TE split, `ref_te_edit/`): the edit
> conditioning is cached per frame, then the sampling runs with the UNet
> resident. Measured with `qwen-2511_int8` on an RTX 5070 Ti 16 GB
> (920×672 frames, 2 steps, warm-up excluded): **7.33 s/frame** steady —
> 1.33 s conditioning + 6.00 s sampling from the cache — on a 17-frame run
> (the first frame costs ~14 s more, one-time; at 4 steps the split measures
> ~11.9 s/frame). The standard single-frame path runs at
> **~10.4–10.8 s/frame**, so the split is ~1.4× faster here; on 16 GB the
> UNet is partly streamed from system RAM (peak VRAM ~13.4 GB, ~6.9 GB
> offloaded; measured process RAM ~40 GB working set / ~50 GB committed).
> Uses ComfyUI-native code : no ComfyUI GUI installation needed.
> Both configs live in the `config/` folder.

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

### qwen21-viggle : ~3 sec/frame with Fast Pipeline, ~6 without (Qwen-Image-2.1 int8 ConvRot)

| Requirement | Details                            |
| ----------- | ----------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (14 GB+ VRAM; **12 GB+** with Fast Pipeline) |
| **RAM**     | 32 GB+                             |
| **CUDA**    | 13.0+                              |

> Native ComfyUI int8 ConvRot weights for the **UNet** (not GGUF — a GGUF
> UNet was evaluated but is ~2× slower for this model). The **CLIP/text
> encoder** is the int8 ConvRot `.safetensors` (`qwen3vl_8b_int8_convrot`,
> default since 2.4.0 — faster and, in side-by-side tests, visually cleaner
> than the previous GGUF+mmproj pair; see [What's New](whats-new.md)). The
> GGUF pair (`Qwen3-VL-8B-Instruct-UD`) remains available by editing the
> config's `clip_name`/`clip_mmproj`, see [Pipeline Configuration](configuration.md). Requires
> `comfy-kitchen==0.2.35` and `comfy-aimdo==0.5.5` exactly (pinned, not a
> minimum — both are compiled packages and an untested newer build is not
> assumed safe). A fresh `install.cmd` run sets these; an **existing**
> `.venv` needs an explicit upgrade, see [Quick Update](installation.md#-quick-update-existing-installation).
> All files are auto-downloaded on first run — see [What's New](whats-new.md).
> Launch with `start_server.cmd qwen21_viggle`.

### qwen21-turbo : ~4.5 sec/frame single split, ~2.3 with the paired split (Qwen-Image-2.1-Turbo int8 ConvRot)

| Requirement | Details                            |
| ----------- | ---------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (14 GB+ VRAM; **12 GB+** with Fast Pipeline) |
| **RAM**     | 32 GB+                             |
| **CUDA**    | 13.0+                              |

> The second Qwen-Image-2.1 variant: same loading path as `qwen21-viggle`
> (int8 ConvRot UNet + int8 ConvRot text encoder, native ComfyUI loaders)
> with no LoRA. The checkpoint carries its **own 8-step sigma schedule** —
> the Colorization Steps setting does not apply — and there is no prompt
> enhancer; like qwen21-viggle it wants a **detailed prompt**. Measured on
> an RTX 5070 Ti 16 GB: **~4.5 s/frame** on the single split (`1024`
> budget), **~2.3 s/frame** with the paired split
> (`qwen21_turbo-fast_int8`, `fast_split_TE`). It colors better than the
> viggle family but is noticeably **less stable** between similar frames —
> see the note at the top; the shipped default stays
> `qwen21_viggle-soft_int8`. Configs: `qwen21_turbo_int8` /
> `qwen21_turbo-fast_int8`; launch with `start_server.cmd qwen21_turbo_int8`.

### All backends

| Requirement | Details                |
| ----------- | ---------------------- |
| **OS**      | Windows 10/11 or Linux |
| **Python**  | 3.12                   |
