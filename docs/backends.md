# Backends

Seven backends, one API — pick the one that fits your hardware.

Each backend below shows a side-by-side comparison on the **same frame**: the ground-truth (color) source on the left, and that backend's colorization of it on the right — a quick way to judge how well each model colors known objects.

> ¹ Measured with **Fast Pipeline** — for `qwen21-viggle`, `qwen21-turbo`, `gguf-qwen`, `qwen25-nunchaku`, `longcat-gguf` and `flux2` the cached text-encoder split (paired for `qwen21-turbo`'s fast variant, for `flux2`, for the `qwen25-nunchaku` `-fast` configs and for `longcat-gguf` with `fast_split_TE`), for `nunchaku-qwen` paired inference (two frames per forward pass) — at the backend's fastest recommended step count, warm-up excluded. ² `longcat-gguf`'s figure is its single-image live time: with Fast Pipeline it drops to ~12 s/frame (and ~7.5 paired, see its section).

> **Recommended**: **qwen21-viggle** and **nunchaku-qwen** are both recommended for production use. Thanks to recent code optimizations — Dynamic VRAM and the text-encoder (TE) split — **qwen21-viggle** is now the fastest backend: **1.7 sec/frame** with _Fast Pipeline_ (~3.5 sec/frame at the fastest usable step count, `steps=2`, without it; see the `⚠️ Fast Pipeline` note below) — and has the **lowest minimum hardware requirements**: **12 GB VRAM / 32 GB RAM** (14GB+ VRAM on the standard path). The other backends that also fit a 12 GB card are far slower — `qwen-2511_q3` at ~7 sec/frame, `longcat-gguf` at ~12 sec/frame — so at that VRAM class viggle is not just the fastest, it is in a different league. `nunchaku-qwen` runs at about **4 sec/frame** using its paired _Fast Pipeline_ (`steps=2`) and needs 16GB+ VRAM / 64GB+ RAM. **`gguf-qwen`** (Qwen-Image-Edit 2511) now also supports the cached-TE split: **~7.3 sec/frame** against ~10.5 sec/frame for the standard path (~1.4×, 17-frame test at 2 steps), on a 16 GB+ GPU / 48 GB+ RAM for the recommended `qwen-2511_int8` config (12 GB+ with `qwen-2511_q3`). **`qwen21-turbo`** is the rendition-maximizing option — **~4.5 sec/frame** on the single split, **~2.3** with the paired `fast_split_TE` one — richer colors than the viggle family, but noticeably less stable between similar frames (see the field verdict below). `longcat-gguf` remain the choice for VRAM-constrained setups where neither of the above fits, at a real speed cost (see the `⚠️ Experimental` note under GGUF below). **`flux2`** (2.6.0) adds the FLUX.2-dev family: 16 GB+ VRAM / 64 GB+ RAM, **~4.0 s/frame** on the int4 config with `"vram_headroom": 3` (~5.5 on fp8 mixed) — see its section below. **`qwen25-nunchaku`** (2.7.0) runs the same Qwen-Image-Edit models through the **ComfyUI-nunchaku node**: **~4.1–4.4 s/frame** on the paired `-fast` configs and ~7.4–9.2 on the single-frame ones, on an RTX 50 card with 16 GB+ VRAM — its **2509** config is the pick of the family, while for 2511 the reference stays `qwen-2511_int8` (see the field verdict in its section).
>
> ⚠️ **Fast Pipeline + `qwen21-viggle`** (2.4.0): this backend no longer uses paired inference — _Fast Pipeline_ runs a **cached text-encoder split**: each frame's text-encoder conditioning is computed once and cached, then the sampling runs with the UNet resident, in chunks of 200 frames (~**1.7 sec/frame**, roughly 2× the standard path). There is no merge boundary, nor the paired-mode resolution trade-off it required. A chunk's cache is deleted once its frames are colorized, and a cancelled run resumes from the first missing frame. In standard (non-Fast) mode the single-frame path runs at about **3.5 sec/frame**. On secondary, color-ambiguous details (e.g. a flower's petals) a run can still land on a noticeably different but plausible hue — the color-hedging behavior described above, not a defect. The [Viggle-Turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo) LoRA is still an experimental release: spot-check the output before a long batch run.
>
> **Color stability vs. variety**: based on real-world use across thousands of frames, `nunchaku-qwen` tends to show more color variability between similar frames — can look more vivid, but with weaker frame-to-frame consistency — while `qwen21-viggle` is more conservative in its color choices and more stable, likely a consequence of the Viggle-Turbo LoRA's aggressive step-distillation, which tends to narrow the range of plausible outputs toward "safe" choices. For video work, where flickering color between consecutive frames is a visible defect, this makes `qwen21-viggle`'s conservatism a practical advantage rather than just a stylistic difference — worth factoring in alongside the speed/hardware trade-offs above. The same pattern showed up in paired inference (which `qwen21-viggle` used before 2.4.0 and `nunchaku-qwen` still uses): when both frames of a pair shared an object, `qwen21-viggle` consistently colored it the same way in both halves, while `nunchaku-qwen` is less reliable at this — the exact cause (the LoRA itself vs. something more general about the two pipelines) is not established.

> **Color stability, qwen21-turbo vs qwen21-viggle** (field verdict, 2026-10-11): the turbo family colors *better* — richer, often more accurate hues — but with noticeably more variability between similar frames; over a whole film that reads as visible color flicker and outweighs the better rendition. Its paired variant (`qwen21_turbo-fast_int8`, `fast_split_TE`) is a middle ground, though some frames come out almost black-and-white. `qwen21-viggle` at **2 steps** therefore stays the nominal default — the best speed / quality / stability trade-off.

## Requirements by backend

Choose the backend that matches your hardware:

### nunchaku-qwen : 4 sec/frame (FP4/INT4)

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/1_Flags_qwen-nunchaku.jpg" alt="nunchaku-qwen result" width="220"><br><sub>nunchaku-qwen</sub></td>
</tr>
</table>

| Requirement      | Details                            |
| ---------------- | ---------------------------------- |
| **GPU**          | NVIDIA RTX 30/40/50  (16 GB+ VRAM) |
| **RAM**          | 64 GB+                             |
| **CUDA**         | 13.0 or newer                      |
| **CUDA Toolkit** | Must match the PyTorch build       |

> **RTX 30/40-Series (Ampere / Ada)**: use `"model_precision": "int4"`. FP4 requires Blackwell (RTX 50).
> Requires Nunchaku 1.2.1 and `diffusers==0.37.0.dev0` (wheel published in the release assets).

### qwen-2511 (gguf-qwen) : ~7.3 sec/frame with Fast Pipeline, ~10.5 without (int8 ConvRot 16 GB+ / Q3_K_S 12 GB+)

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/2_Flags_qwen2511_int8.jpg" alt="qwen-2511 int8 result" width="220"><br><sub>qwen-2511 (int8 ConvRot)</sub></td>
</tr>
</table>

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

### qwen25-nunchaku : ~4.1–4.4 sec/frame paired, ~8.7 with the split, ~9.2 without (Qwen-Image-Edit 2509/2511 on the Nunchaku node)

The same Qwen-Image-Edit models as `nunchaku-qwen` and `gguf-qwen`, run
through the **ComfyUI-nunchaku node** (SVDQuant) instead of a diffusers
pipeline or the GGUF dequantizer — the exact graph ComfyUI executes
(`TextEncodeQwenImageEditPlus` → `AuraFlow shift 3` → `CFGNorm` →
`KSampler`, 4 steps at cfg 1). Four configs shipped — the two checkpoints, each
with a plain and a `-fast` (paired split) variant:

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/7_qwen-2509-nunchaku_fp4.jpg" alt="qwen-2509-nunchaku result" width="220"><br><sub>qwen-2509-nunchaku (FP4)</sub></td>
<td align="center"><img src="../assets/8_qwen-2511-nunchaku_fp4.jpg" alt="qwen-2511-nunchaku result" width="220"><br><sub>qwen-2511-nunchaku (FP4 + Lightning)</sub></td>
</tr>
</table>

| Config                       | Checkpoint                                   | LoRA                | Fast Pipeline |
| ---------------------------- | -------------------------------------------- | ------------------- | ------------- |
| `qwen-2509-nunchaku_fp4`     | official nunchaku-ai 2509 FP4 (r32)          | fused (none)        | per-frame TE cache |
| `qwen-2511-nunchaku_fp4`     | QuantFunc 2511 FP4 `balance` (r128)          | Lightning 4-step    | per-frame TE cache |
| `qwen-2509-nunchaku-fast_fp4`| same as above                                | fused (none)        | **paired** (`fast_split_TE`) |
| `qwen-2511-nunchaku-fast_fp4`| same as above                                | Lightning 4-step    | **paired** (`fast_split_TE`) |
| `qwen-2509-nunchaku_int4`    | official nunchaku-ai 2509 **INT4** (r32)     | fused (none)        | per-frame TE cache |
| `qwen-2509-nunchaku-fast_int4`| same as above                               | fused (none)        | **paired** (`fast_split_TE`) |

| Requirement | Details |
| ----------- | ------- |
| **GPU**     | RTX 50-Series for the **fp4** configs; **RTX 30/40-Series for the int4 ones** (nunchaku's gate: int4 on SM 75/80/86/89, fp4 on SM 120/121 — each refuses the other). **12 GB+ for `qwen-2509-nunchaku-fast_int4`** (field-tested on an RTX 3060); 16 GB+ for the rest — the 2511 checkpoint is 13 GB, the 2509 one 12 GB |
| **RAM**     | 32 GB+ |
| **CUDA**    | 13.0 or newer |

> **When to pick it**: it is the only path to **Qwen-Image-Edit 2511 with
> SVDQuant weights** (there is no official 2511 release), and it runs the
> **Lightning LoRA on quantized weights** (the QuantFunc checkpoints do not
> have it fused). The diffusers `nunchaku-qwen` family stays the reference for
> the official 2509 Lightning checkpoint.
>
> **Field verdict, 2026-10-17**: **`qwen-2509-nunchaku_fp4` is the pick** —
> fastest to load (12 GB, Lightning fused, no LoRA composition), fastest in
> absolute terms and with stable colors. **`qwen-2511-nunchaku_fp4` works but
> does not beat `qwen-2511_int8`** (the `gguf-qwen` config) on quality, and
> pays a 13 GB load plus the LoRA composition: it is worth it only if you want
> 2511 on the Nunchaku node specifically — for 2511, `qwen-2511_int8` remains
> the reference.
>
> **Measured** (RTX 5070 Ti 16 GB, 2026-10-17, one 1184×880 frame at the
> 1 Mpx budget, `steps=4`, warm-up excluded): **2511 ~9.2 s/frame** live and
> **~8.7 s/frame** on the split (1.8 s conditioning + 6.9 s sampling);
> **2509 ~7.4 s/frame**. Sampling itself runs at **~1.5–1.7 s/step**; the
> first step of a fresh model costs 4–5 s more (initialization), and the
> first load of a cold checkpoint ~4–5 minutes from an HDD (one-time, per
> server session).
>
> **The `-fast` configs** pair consecutive frames: **4.4 s/frame** for 2511
> and **4.1 s/frame** for 2509 (two 1480×1080 frames per 8.9 s / 8.3 s unit) —
> about twice the throughput, at half the working area per frame, since the
> pair canvas shares the same 1 Mpx budget. Output stays clean and coherent
> in the frames inspected; it is visibly softer than the single-frame path.
> Use them for long video runs; keep the plain configs when detail matters
> more than speed.
>
> **`qwen-2509-nunchaku_int4` / `-fast_int4`** are the same 2509 checkpoint
> re-quantized to **int4** (11.5 GB, r32) — the variant that loads on
> **RTX 30/40**. The int4 kernel is the one those architectures have tensor
> cores for; on a Blackwell card nunchaku refuses to load it (use fp4 there).
> These configs ship `num_blocks_on_gpu: 8` instead of 20: on the fp4 sibling
> the peak measured 14.1 GB at 20 blocks and 12.1 GB at 8, with no speed loss.
>
> **Field test, 2026-10-18 — RTX 3060, 12 GB VRAM / 32 GB RAM, models on an
> HDD**: `qwen-2509-nunchaku-fast_int4` runs at **~4.3 s/frame** on the paired
> split (4.9 s/image averaged over a 9-frame batch, which ends on a single
> full-area frame). `num_blocks_on_gpu` **8 or 4 made no difference** (0.7%),
> and 8 blocks fit without OOM — **12 GB is verified for this config**. The
> **single-frame live path** (`Fix Image`) needs the text encoder and the
> transformer one after the other; with 32 GB of RAM they do not fit in the
> pinned pool together (40% of RAM ≈ 13 GB vs 7.9 + 11.5 GB), so it
> **re-streams the encoder from disk for every image** — ~65 s/image on an HDD
> after the first. Use the split configs for batches, and keep the model
> folder on an SSD (the first load also takes 4–5 min from an HDD).
>
> **`cpu_offload`**: the Nunchaku transformer streams its blocks from host
> RAM; the shipped configs force `enable` because upstream's `auto` disables
> offload on a 16 GB card (it reports 15 GiB) — measured on the RTX 5070 Ti
> that costs **~1.9×** (10.5 s vs 5.4 s per frame at 2 steps). On 24 GB+
> cards `disable` can be tried; `enable` remains the safe default.

> Launch with `start_server.cmd qwen-2511-nunchaku_fp4` (or the 2509 name) —
> see [Server Usage](server_usage.md).

### longcat-gguf : 12 sec/frame (Q3–Q4) — Best Quality

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/5_Flags_longcat_q3.jpg" alt="longcat-gguf Q3 result" width="220"><br><sub>longcat-gguf (Q3_K_S)</sub></td>
</tr>
</table>

| Requirement | Details                            |
| ----------- | ---------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (12 GB+ VRAM) |
| **RAM**     | 32 GB+                             |
| **CUDA**    | 13.0+                              |

> LongCat-Image-Edit-Turbo delivers noticeably better colorization than the
> gguf-qwen model — richer colors, more natural skin tones, and better
> detail preservation — at the same ~12 s/frame speed.
> 
> Uses a GGUF quantized UNet (**Q3_K_M** or **Q4_K_M**) + CLIP Q4_K_M. Two
> quantization levels ship — Q3 for the 12 GB class, Q4 as the default: the
> family is only worth its download when it fits, and above Q4 there is no
> point in it (Q5/Q6 were retired: anyone with the RAM for them is better off
> with another backend; below Q3 the quant starts to show).
> All files are auto-downloaded on first run.
>
> **Fast Pipeline is supported since 2026-10-18** (cached EditPlus
> conditioning, `ref_te_edit/`): phase A runs the text encoder + VAE over the
> batch, phase B samples with the UNet + VAE resident — and the split drops
> the negative text-encoder pass the live path computed for a `cfg=1.0`
> sampler that never reads it. Measured on an RTX 5070 Ti 16 GB, Q4_K_M,
> 8 steps, ~1 Mpx frames, steady state: **13.0 → 11.9 s/frame** (~**1.09×**)
> with the single split, and the output is **bit-identical** to the live one.
> The gain is small, and the arithmetic says why: at 8 steps the sampling is
> **82%** of the frame (10.5 s), the two text-encoder passes 15% together and
> only the negative one (7.5%) can go — unlike the qwen21/flux families, whose
> live path also paid per-frame model movement and whose sampling is 2 steps.
> The split does separate the models (phase A: text encoder + VAE, phase B:
> UNet + VAE), but on a 16 GB card the live path already keeps **all three
> resident** (13.4 GB of 15.9), so there is no movement to save. The separation
> starts paying when they no longer coexist: with the model manager's budget
> cut (`comfy --reserve-vram`, a simulation of a smaller card, not a smaller
> allocator) the live path degrades to **14.8 s/frame** at 3 GB reserved and
> **17.5** at 6 GB — it streams weights — while the split stays at
> **~11.6–11.9**. That is ~**1.1×** on 16 GB, ~**1.3–1.5×** on a tighter card.
> Add `"fast_split_TE": true` to pair consecutive frames: the pair shares the
> sampling pass, so **~6.3 s/frame** (~**2.0×**), two frames per pass.
> 
> See `config/longcat_gguf_q3.json` / `longcat_gguf_q4.json` — the general
> rule: lower quant = less VRAM. Two **`-fast`** variants
> (`longcat_gguf-fast_q3`, `longcat_gguf-fast_q4`) ship the same checkpoints
> with `"fast_split_TE": true` and the **same prompt**, so a paired run and a
> single run differ only in the pairing. **Field verdict, 2026-10-18**: the
> paired variants are faster but the colors come out **less accurate and less
> stable** than the single split — the pair works at half the area per frame.
> They make sense on low-end machines, where throughput matters more than the
> last bit of color fidelity; on a capable card prefer the base configs.
>
> **When to pick this family at all**: only on **low-end hardware**. On a
> card that runs `qwen21-viggle` or `qwen25-nunchaku` comfortably, those are
> faster and cleaner; LongCat is the fallback for small VRAM / small RAM.
>
> Launch with `run_server_longcat.cmd` (Q4_K_M) or
> `start_server.cmd longcat|longcat-q3`; the `-fast` configs by name:
> `start_server.cmd longcat_gguf-fast_q3`.

### qwen21-viggle : ~1.7 sec/frame with Fast Pipeline, ~3.5 without (Qwen-Image-2.1 int8 ConvRot)

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/3_Flags_qwen21-viggle.jpg" alt="qwen21-viggle result" width="220"><br><sub>qwen21-viggle</sub></td>
</tr>
</table>

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
> Launch with `start_server.cmd qwen21_viggle-soft_int8`.

### qwen21-turbo : ~4.5 sec/frame single split, ~2.3 with the paired split (Qwen-Image-2.1-Turbo int8 ConvRot)

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/4_Flags_qwen21-turbo.jpg" alt="qwen21-turbo result" width="220"><br><sub>qwen21-turbo</sub></td>
</tr>
</table>

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

### flux2 : ~4.0 sec/frame paired (FLUX.2-dev int4 ConvRot), ~5.5 (fp8 mixed) — FLUX-family colors

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/6_Flags_Flux2_dev.jpg" alt="flux2 result" width="220"><br><sub>flux2 (FLUX.2-dev)</sub></td>
</tr>
</table>

| Requirement | Details                            |
| ----------- | ---------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50  (16 GB+ VRAM) |
| **RAM**     | 64 GB+                             |
| **CUDA**    | 13.0+                              |

> **FLUX.2-dev** (Black Forest Labs): the FLUX.2-dev transformer with the
> **Mistral-3 small** text encoder, the **FLUX.2 small-decoder** VAE (the
> family default since 2.6.0 — same encode as the full VAE, ~1.55× faster
> decode, PSNR 42.1 dB against it) and the **Flux.2 Turbo LoRA**, applied at
> load time. The family is entirely ComfyUI-native, like the qwen21 line.
> The text encoder never sees the frame — the B&W frame reaches the
> transformer as a VAE **reference latent**, so the TE pass is prompt-only
> and the paired split gains a whole sampling pass (plus a VAE encode) per
> two frames.

Three configs ship, all with `steps: 2` (the Turbo LoRA's distilled step
count), `guidance: 4.0` and the **paired split** on (`fast_split_TE`):

| Config                          | UNet                              | Size    | Notes                                                        |
| ------------------------------- | --------------------------------- | ------- | ------------------------------------------------------------ |
| `flux2_dev_int4.json`           | int4 ConvRot `.safetensors` (community repack) | 18.3 GB | **recommended on 16 GB** with `vram_headroom: 3` — see below   |
| `flux2_dev_fp8.json`            | fp8-mixed `.safetensors` (Comfy-Org) | 33 GB   | streams from RAM/disk; the 64 GB of RAM is the real requirement |
| `flux2_dev_q3.json`             | GGUF `Q3_K_M`                     | 15.8 GB | lighter, GGUF path (no native kernels: slower)               |

> **Measured** (RTX 5070 Ti 16 GB, pairs of frames, 2 steps, 1024 area
> budget, warm-up excluded): **int4 with `vram_headroom: 3` → ~4.0 s/frame**
> steady (3.98–4.09 s/frame across three runs; the two 3 GB runs 0.4% apart)
> — **~1.35× the fp8 config** (~5.5 s/frame) and as stable;
> `Q3_K_M` not yet measured. Single-frame (non-paired) runs cost about
> twice as much per frame. On an 8-frame run the first frame pays the
> one-time warm-up (~3 min) on every config.

#### `vram_headroom` — the int4 checkpoint's setting per VRAM size

`"vram_headroom": N` tells aimdo's DynamicVRAM to keep N GB of VRAM free
and unused on purpose (the same knob as ComfyUI's `--vram-headroom`; 0, the
default, means no extra reservation). Only `flux2_dev_int4.json` sets it,
because only there it pays off — the int4 checkpoint is the one that *almost*
fits a 16 GB card:

| VRAM    | `vram_headroom` | Why                                                                                          |
| ------- | --------------- | -------------------------------------------------------------------------------------------- |
| 12 GB   | `0`             | the checkpoint (18.3 GB) cannot fill the card anyway: it already streams continuously, and a reservation would only shrink an already-tight residency |
| **16 GB** | **`3`**       | **the measured case**: without the reservation aimdo fills the card to the brim (~9.2–10.2 GB resident, ~300 of 508 pages, driver free under 2 GB) and leaves nothing for the activations, so the per-frame cost swings (6.8 up to 49.9 s/unit against 7.3 s with the setting) — the reservation forces even streaming, which is *faster* than the marginal regime |
| 24 GB+  | `0`             | the checkpoint fits: reserving 3 GB would only push part of it out for nothing                |

> The key is read from the config by `parse_pipeline_config` and applied
> once, when the first model is loaded — the server is restarted on every
> config change anyway, so it behaves as a per-server setting. It is
> accepted by every aimdo-backed backend, but **only the int4 flux2 config
> sets it**: on the fp8 config it measurably costs ~2%. Full mechanics:
> [Pipeline Configuration](configuration.md).

> Launch with `start_server.cmd flux2_dev_int4` (or any of the four config
> names) — see [Server Usage](server_usage.md).

### All backends

| Requirement | Details                |
| ----------- | ---------------------- |
| **OS**      | Windows 10/11 or Linux |
| **Python**  | 3.12                   |
