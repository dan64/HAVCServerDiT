# Backends

Eight backends, one API — pick the one that fits your hardware.

Each backend below shows a side-by-side comparison on the **same frame**: the ground-truth (color) source on the left, and that backend's colorization of it on the right — a quick way to judge how well each model colors known objects.

> ¹ Measured with **Fast Pipeline** — for `qwen21-viggle`, `qwen21-turbo`, `gguf-qwen`, `qwen25-nunchaku`, `longcat-gguf`, `flux2` and `flux3` the cached text-encoder split (paired for `qwen21-turbo`'s fast variant, for `flux2` and `flux3`, for the `qwen25-nunchaku` `-fast` configs and for `longcat-gguf` with `fast_split_TE`), for `nunchaku-qwen` paired inference (two frames per forward pass) — at the backend's fastest recommended step count, warm-up excluded. ² `longcat-gguf`'s figure is its single-image live time: with Fast Pipeline it drops to ~12 s/frame (and ~7.5 paired, see its section).

> **Recommended**: **qwen21-viggle** and **nunchaku-qwen** are both recommended for production use. Thanks to recent code optimizations — Dynamic VRAM and the text-encoder (TE) split — **qwen21-viggle** is the fastest backend **in the 12 GB class**: **2.9 sec/frame** at the fastest usable step count (`steps=2`), or **2.65** with _Fast Pipeline_ (re-measured 2026-10-21; the older 1.7 / 3.5 pair predates DynamicVRAM — see the `⚠️ Fast Pipeline` note below). Faster configs exist above that VRAM class — see the field comparison below — and it has the **lowest minimum requirements of the backends that run at a usable speed**: **12 GB VRAM / 32 GB RAM** (14GB+ VRAM on the standard path). The other backends that also fit a 12 GB card are far slower — `qwen-2511_q3` at ~7 sec/frame, `longcat-gguf` at ~12 sec/frame — so at that VRAM class viggle is not just the fastest, it is in a different league. Only `longcat-gguf` goes lower (8 GB / 16 GB — see its section), at a much higher per-frame cost; it is what the installer picks when the machine cannot run the Qwen families (see its section). `nunchaku-qwen` runs at about **4 sec/frame** using its paired _Fast Pipeline_ (`steps=2`) and needs 16GB+ VRAM / 64GB+ RAM. **`gguf-qwen`** (Qwen-Image-Edit 2511) now also supports the cached-TE split: **~7.3 sec/frame** against ~10.5 sec/frame for the standard path (~1.4×, 17-frame test at 2 steps), on a 16 GB+ GPU / 48 GB+ RAM for the recommended `qwen-2511_int8` config (12 GB+ with `qwen-2511_q3`). **`qwen21-turbo`** is the rendition-maximizing option — **~4.5 sec/frame** on the single split, **~2.3** with the paired `fast_split_TE` one — richer colors than the viggle family, but noticeably less stable between similar frames (see the field verdict below). `longcat-gguf` remain the choice for VRAM-constrained setups where neither of the above fits, at a real speed cost (see the `⚠️ Experimental` note under GGUF below). **`flux2`** (2.6.0) adds the FLUX.2-dev family: 16 GB+ VRAM / 64 GB+ RAM, **~4.0 s/frame** on the int4 config with `"vram_headroom": 3` (~5.5 on fp8 mixed) — see its section below. **`qwen25-nunchaku`** (2.7.0) runs the same Qwen-Image-Edit models through the **ComfyUI-nunchaku node**: **~4.1–4.4 s/frame** on the paired `-fast` configs and ~7.4–9.2 on the single-frame ones, on an RTX 50 card with 16 GB+ VRAM — its **2509** config is the pick of the family, while for 2511 the reference stays `qwen-2511_int8` (see the field verdict in its section). **`flux3`** (2026-10-21) adds **FLUX.3 Image Klein** with its **Qwen3.5-9B prompt upsampler** — the encoder reads the frame and expands the request, which is what makes the family recognize conventionally-colored subjects (a Santa suit is red, not "natural"); **~4.9-5.3 s/image** end to end, paired (see its section).
>
> ⚠️ **Fast Pipeline + `qwen21-viggle`** (2.4.0): this backend no longer uses paired inference — _Fast Pipeline_ runs a **cached text-encoder split**: each frame's text-encoder conditioning is computed once and cached, then the sampling runs with the UNet resident, in chunks of 200 frames (~**2.65 sec/frame** at `steps=2`, about **1.09×** the standard path — measured 2026-10-21, see the note below). (The paired `fast_split_TE` flows chunk by *pairs* instead: 100 pairs for the `te` families, 50 for the edit ones — see [GUI usage](gui_usage.md#step-3-colorize-frames-ai).) There is no merge boundary, nor the paired-mode resolution trade-off it required. A chunk's cache is deleted once its frames are colorized, and a cancelled run resumes from the first missing frame. In standard (non-Fast) mode the single-frame path runs at about **2.9 sec/frame** at `steps=2`. On secondary, color-ambiguous details (e.g. a flower's petals) a run can still land on a noticeably different but plausible hue — the color-hedging behavior described above, not a defect. The [Viggle-Turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo) LoRA is still an experimental release: spot-check the output before a long batch run.
>
> **Color stability vs. variety**: based on real-world use across thousands of frames, `nunchaku-qwen` tends to show more color variability between similar frames — can look more vivid, but with weaker frame-to-frame consistency — while `qwen21-viggle` is more conservative in its color choices and more stable, likely a consequence of the Viggle-Turbo LoRA's aggressive step-distillation, which tends to narrow the range of plausible outputs toward "safe" choices. For video work, where flickering color between consecutive frames is a visible defect, this makes `qwen21-viggle`'s conservatism a practical advantage rather than just a stylistic difference — worth factoring in alongside the speed/hardware trade-offs above. The same pattern showed up in paired inference (which `qwen21-viggle` used before 2.4.0 and `nunchaku-qwen` still uses): when both frames of a pair shared an object, `qwen21-viggle` consistently colored it the same way in both halves, while `nunchaku-qwen` is less reliable at this — the exact cause (the LoRA itself vs. something more general about the two pipelines) is not established.

> **Color stability, qwen21-turbo vs qwen21-viggle** (field verdict, 2026-10-11): the turbo family colors *better* — richer, often more accurate hues — but with noticeably more variability between similar frames; over a whole film that reads as visible color flicker and outweighs the better rendition. Its paired variant (`qwen21_turbo-fast_int8`, `fast_split_TE`) is a middle ground, though some frames come out almost black-and-white. `qwen21-viggle` at **2 steps** therefore stays the nominal default — the best speed / quality / stability trade-off.

## Field comparison

Every shipped config timed on the same 15-frame clip (920x672, 0.62 Mpx), end to
end, all sessions from 2026-10-15 onward. The full table, its method and its
caveats live in **[Benchmarks](benchmarks.md)**; what matters here is the shape:

- the **paired `-fast` configs** and **`flux2_klein_4b_int8`** (1.67 s/image)
  are at the top;
- **`qwen21-viggle` is the fastest option that fits 12 GB** (3.07 s/image, 2.80
  with `fast_split_TE`) — not the fastest overall;
- **`flux3` lands mid-field** at 4.87-5.33 s/image;
- the single-split edit families sit in the middle, the retired Q2/Q3 extremes
  at the bottom.

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
| **GPU**     | RTX 50-Series for the **fp4** configs; **RTX 30/40-Series for the int4 ones** (nunchaku's gate: int4 on SM 75/80/86/89, fp4 on SM 120/121 — each refuses the other). **12 GB+ for the int4 configs** (field-tested with `qwen-2509-nunchaku-fast_int4` on an RTX 3060; `qwen-2509-nunchaku_int4` is the installer's default on RTX 30/40) and **16 GB+ for the fp4 configs** — the 2511 checkpoint is 13 GB, the 2509 one 12 GB |
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
| **GPU**     | NVIDIA RTX 30/40/50  (**8 GB+ VRAM** with the Q3 checkpoint — field-tested) |
| **RAM**     | **16 GB+** (field-tested)          |
| **CUDA**    | 13.0+                              |

> **The lowest hardware requirement in the stack**: the family runs on a
> machine with **8 GB of VRAM and 16 GB of RAM** (author's field test,
> 2026-10-18, `longcat_gguf_q3`). That test is the proof that the **8 GB / 16 GB
> class works at all**, and since 2026-10-20 the installer sends that class to
> `flux2_klein_4b_int8` instead — smaller in weights (7.60 GB against 8.83 GB)
> and faster — keeping LongCat Q3 available in the GUI for anyone who prefers
> it. The rule is unchanged: below **less than 12 GB of VRAM**, or **up to
> 16 GB of VRAM with less than 24 GB of RAM**, the installer picks the light
> model; above those thresholds it picks `qwen-2509-nunchaku`. LongCat is the
> slowest backend of the stack, so use it when nothing else fits rather than by
> preference.
>
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

### qwen21-viggle : ~2.65 sec/frame with Fast Pipeline, ~2.9 without (Qwen-Image-2.1 int8 ConvRot)

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
> `comfy-kitchen==0.2.35` and `comfy-aimdo==0.5.6` exactly (pinned, not a
> minimum — both are compiled packages and an untested newer build is not
> assumed safe). A fresh `install.cmd` run sets these; an **existing**
> `.venv` needs an explicit upgrade, see [Quick Update](installation.md#-quick-update-existing-installation).
> All files are auto-downloaded on first run — see [What's New](whats-new.md).
> Launch with `start_server.cmd qwen21_viggle-soft_int8`.

> **Speed, re-measured 2026-10-21** (`dist/scripts/bench_viggle_live_vs_split.py`,
> RTX 5070 Ti 16 GB, the 15 frames in `gui\samples\ref_tht10`, same session,
> back to back, steady state with the first frame excluded):
>
> | Path | `steps=2` | `steps=6` |
> | ---- | --------- | --------- |
> | live — one call per frame | **2.88 s** | **4.45 s** |
> | Fast Pipeline — phase A (TE) | 1.06 s | 1.06 s |
> | Fast Pipeline — phase B (sample) | 1.59 s | 3.19 s |
> | **Fast Pipeline — total** | **2.65 s** | **4.25 s** |
> | speed-up | **1.09×** | **1.05×** |
>
> Phase A does not depend on the step count (it is the text encoder + VAE), and
> the split reproduces the live output **byte for byte** (15/15 at 6 steps); an
> order control re-ran the live path last and got the same 4.44 s, so the
> comparison is not an artefact of warm-up.
>
> **The older 1.7 s/frame (≈2× the standard path) predates DynamicVRAM.** Until
> 2026-10-14 the live path had to re-stage the models between sampling and the
> text encoder on every frame, and that is what the split removed. With aimdo's
> DynamicVRAM streaming in place the live path dropped from ~3.5 to ~2.9 s/frame
> and the split's advantage mostly disappeared. Fast Pipeline is still worth
> keeping for its **resume** (cached conditioning, chunked progress), but it is
> no longer a 2× speed-up on this family.


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

#### Flux.2 Klein 9B / 4B — the same family, no guidance, no LoRA

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/9_Flux2_klein-9b_int8.jpg" alt="Flux.2 Klein 9B INT8 result" width="220"><br><sub>Flux.2 Klein 9B (INT8)</sub></td>
<td align="center"><img src="../assets/10_Flux2_klein-4b_int8.jpg" alt="Flux.2 Klein 4B INT8 result" width="220"><br><sub>Flux.2 Klein 4B (INT8)</sub></td>
</tr>
</table>

> Both samples are the author's field run of the shipped INT8 configs at
> **2 steps with the paired split** — the output is already vividly colored at
> that setting, which is why the GUI ships saturation at `1.0`.

Two **Flux.2 Klein** checkpoints (Black Forest Labs) ship as extra configs of
the same `flux2` family — so they get the same split and paired flows, the same
VAE and the same GUI wiring without a new backend:

| Config                     | UNet                           | Size   | Text encoder     | Steps |
| -------------------------- | ------------------------------ | ------ | ---------------- | ----- |
| `flux2_klein_9b_int8.json` | `flux-2-klein-9b` INT8 ConvRot | 8.8 GB | Qwen3 8B **fp4** | 4     |
| `flux2_klein_4b_int8.json` | `flux-2-klein-4b` INT8 ConvRot | 3.8 GB | Qwen3 4B **fp4** | 4     |

> **INT8 ConvRot is ComfyUI's native int8 format** (`int8_tensorwise` +
> `convrot` in the per-layer `comfy_quant` blobs), so the stock `UNETLoader`
> takes it exactly like `qwen21_turbo_int8`: no custom node, no conversion step.
> Upstream [metrics](https://github.com/BobJohnson24/ComfyUI-INT8-Fast/blob/main/Metrics.md)
> rank `BF16 > INT8 ConvRot > MXFP8 > FP8 >= INT8 Row > INT8 Tensorwise`, and on
> FLUX.2 Klein 9B specifically INT8 ConvRot scored *above* GGUF Q8 — at the same
> file size as the fp8 checkpoint, which is why the fp8 twins were dropped
> (2026-10-20). Requires a ComfyUI core ≥ 0.27.0 for the quantization format;
> the core embedded in the shipped `comfy_bridge` is newer.
>
> **The text encoders are the fp4 builds Comfy-Org publishes for Klein**
> (`qwen_3_8b_fp4mixed`, 6.34 GB, and `qwen_3_4b_fp4_flux2`, 3.58 GB). The
> encoder is **prompt-only** in this family and runs once per frame in phase A,
> so the smaller file costs no sampling quality and saves ~1.7 GB (9B) /
> ~3.9 GB (4B) of resident memory during phase A. They are ordinary ComfyUI
> quants (per-layer `comfy_quant`, fp8 scales plus `nvfp4`/`float8` layers),
> loaded by the same `CLIPLoader type="flux2"`. `nvfp4` matmul is native on
> Blackwell; on RTX 30/40 those layers dequantize instead, which for a
> once-per-frame encoder is noise.
>
> **Provenance**: the 9B comes from the community repo
> `obsxrver/ComfyUI-Native-INT8_ConvRot` (file under `diffusion_models/`), the
> 4B from `wraps/FLUX.2-klein-4B-INT8-ConvRot-ComfyUI` (file at the repo root).
> Both are plain downloads — no gate, no HF account needed.
>
> **Already vivid: no saturation boost needed.** Klein produces saturated
> frames out of the box — the author's field test ran it at **2 steps with the
> paired split** and the output was already very colourful, which is why the
> shipped GUI default went back to **`saturation: 1.0`** (the slider's off
> position) instead of 1.4.
>
> **2 steps are enough.** The configs ship `steps: 4` (Klein's distilled
> count) but for `flux2` the GUI's *Colorization Steps* wins, and the author's
> field run at **2 steps with the paired split** already gives vivid, stable
> color — halving the sampling cost. Try 2 first; raise it only if a frame
> comes out flat.
>
> **Field verdict (author, 2026-10-20)**: **the 4B is the fastest model in the
> stack** and it is the installer's pick for small machines since 2026-10-20
> (the rule moved off `longcat_gguf_q3`). It is smaller too: **7.60 GB of
> weights** (3.79 UNet + 3.58 text encoder + 0.23 VAE) against LongCat Q3's
> 8.83 GB, and **3.8 GB against 5.8 GB in phase A**, where the text encoder is
> the only model resident. The 9B was not measured against the dev configs.
>
> Klein differs from Flux.2-dev in exactly three config keys: the **Qwen3**
> text encoder, **no Turbo LoRA** (`lora_path: ""`) and **`guidance: 0`**,
> which skips the FluxGuidance node — Klein's reference workflow samples
> through `CFGGuider(cfg=1.0)`, i.e. with no guidance at all. `vram_headroom`
> stays `0`: every Klein checkpoint fits a 16 GB card.

Launch with `start_server.cmd flux2_klein_4b_int8` (or `_9b_int8`).

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

### flux3 : ~4.9-5.3 sec/image paired (FLUX.3 Image Klein + Qwen3.5-9B prompt upsampler)

<table>
<tr>
<td align="center"><img src="../assets/0_Flags_Ground_Truth.jpg" alt="Ground truth" width="220"><br><sub>Ground truth</sub></td>
<td align="center"><img src="../assets/11_Flux3_klein-6b_int8.jpg" alt="FLUX.3 Klein 6B INT8 result" width="220"><br><sub>FLUX.3 Klein 6B (INT8)</sub></td>
</tr>
</table>

> The author's field run of the shipped config, paired split.
> **13 of the 20 flags come out with their real colors** — against 6-7 for the
> two Flux.2 Klein configs on the same frame, and 18 of 20 for
> `qwen-2509-nunchaku` / `qwen-2511_int8`. The upsampler does what it was
> brought in for (it names the flags it recognizes instead of guessing
> "natural" colors), but it does **not** close the gap with the Qwen-Image-Edit
> family: use `flux3` when its FLUX look is what you want, not as a
> higher-accuracy replacement for `qwen-2509-nunchaku`.
>
> The counts are not an impression: each of the 20 cells is scored on a fixed
> criterion — the hue distribution of its colored pixels must match the ground
> truth (36-bin histogram, intersection >= 0.40) **and** its mean CIELAB color
> must not drift (dE <= 25) — and a cell counts only when both hold. On this
> frame the criterion reproduces the visual counts of `qwen-nunchaku` (18),
> `qwen-2511-nunchaku` (18), `flux3` (13) and Flux.2 Klein 4B (7) exactly.

| Requirement | Details                            |
| ----------- | ---------------------------------- |
| **GPU**     | NVIDIA RTX 30/40/50 (**12 GB+ with Fast Pipeline** — see the note below) |
| **RAM**     | 32 GB+ (with Fast Pipeline)        |
| **CUDA**    | 13.0+                              |

> **FLUX.3 Image Klein** (Black Forest Labs) is the newest FLUX image-editing
> model, and the reason it is here is specific: it is the only FLUX that
> **recognizes what it is looking at** — a Santa suit comes out red, a police
> uniform blue, a tomato red — instead of hedging towards "natural" colors.
> It gets that from a second, much larger text encoder that reads the frame
> before the diffusion model runs.

The family is ComfyUI-native end to end, like `flux2`, and shares that
family's graph: the B&W frame reaches the transformer as a VAE **reference
latent** (the small text encoder is prompt-only), so the cached-TE split and
the paired split apply unchanged. Three things are FLUX.3's own:

* **the prompt upsampler** — a **Qwen3.5-9B w4a8** encoder runs
  `TextGenerate` against the reference image(s) with BFL's image-edit system
  prompt and expands your request into the detailed instruction the
  transformer receives. It runs **once per image** (once per merged canvas in
  the paired flow) and, in the Fast Pipeline, **inside phase A**, so the
  expanded instruction is what gets cached: phase B reproduces the same
  sampling without re-running the 9B model.
* **a constant timestep shift** — the reference workflow patches
  `ModelSamplingFlux` with `max_shift = base_shift = ln(16)`, which is a
  plain shift (the resolution term cancels), unlike the Flux.2 schedule.
* **cfg 1 with no guidance node** — like Klein, the negative branch is never
  evaluated, so the sampler reuses the positive conditioning.

| Config                     | UNet                              | Size   | Text encoders                                   | Steps |
| -------------------------- | --------------------------------- | ------ | ----------------------------------------------- | ----- |
| `flux3_klein_6b_int8.json` | `flux3-image-klein` INT8 ConvRot  | 5.8 GB | Qwen3-VL-4B int8 (6B: 4.9 GB) + Qwen3.5-9B upsampler (6.7 GB) | 8 |

> **Measured** (RTX 5070 Ti 16 GB, paired split, 15 frames = 8 units, the same
> clip twice with only the step count changed):
>
> | Steps | Phase A (per pair) | Phase B (per pair) | End to end |
> | ----- | ------------------ | ------------------ | ---------- |
> | 6     | 48 s → **6.0 s**   | 25 s → **3.1 s**   | 73 s → **4.9 s/image** |
> | 8 (shipped) | 48 s → **6.0 s** | 32 s → **4.0 s** | 80 s → **5.3 s/image** |
>
> Phase A is **identical at both step counts**: it is the upsampler (≈5.3 s per
> pair, ~55-60% of the total), which does not depend on the sampler. Going from
> 6 to 8 steps adds ~0.9 s per pair (~0.45 s/image), so **6 steps is the cheap
> setting** and 8 only buys a little more detail.
>
> These per-image figures are **end to end** (phase A + phase B, wall clock on a
> 15-frame run). The GUI's own *Done! … (x s/image, infer only)* line reports
> **phase B only** — it reads 1.5-2.1 s/image, which is not the cost of
> producing a frame.
>
> That puts the family in the **4-5 s/image class** with `flux2` (~4.0) and
> `qwen25-nunchaku` (~4.1-4.4) -- behind them, not ahead, and well behind
> `qwen21-viggle` (1.7). It is a speed/character trade-off, not a speed win.
> The split is what makes those numbers possible: one upsampler pass per
> *pair* instead of two,
> and the 9B stays resident for the whole chunk instead of being re-staged per
> image (the live path measured **23.8 s** of upsampler for a single frame).

> **Weights: 17.7 GB in total** (5.8 UNet + 4.9 text encoder + 6.7 upsampler
> + 0.3 VAE), all from one repo,
> [`black-forest-labs/flux-3-image-klein-comfy`](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy),
> which is **gated** (`gated: auto`): accept the licence on its page with the
> account your HuggingFace token belongs to, then the first run downloads
> them. A 401 with the licence instructions is what you get otherwise — see
> [Troubleshooting](troubleshooting.md).
>
> **VRAM: Fast Pipeline is what brings it to 12 GB.** The four models are
> **16.7 GB** staged in total (the field run measured 6411 MB upsampler +
> 4632 MB text encoder + 5557 MB transformer + 160 MB VAE), so a **single live
> call** — `colorize_frame_shm`, Fix Image, or the standard (non-Fast) flow —
> needs all four at once: on a 16 GB card it works but streams and re-stages,
> and that frame cost **31.9 s** (23.8 of them the upsampler). The **Fast
> Pipeline separates the phases**, so neither one needs the whole stack:
>
> | Phase | Resident | Staged |
> | ----- | -------- | ------ |
> | A — upsampler + text encoder + VAE | 6411 + 4632 + 160 | **~11.2 GB** |
> | B — transformer + VAE | 5557 + 160 | **~5.7 GB** |
>
> Phase A is the heavy one; on a 12 GB card it fits with ~0.8 GB to spare, so
> the staging is tight but real — **12 GB VRAM / 32 GB RAM are field-confirmed
> with Fast Pipeline**. The transformer is not touched until phase B (5.7 GB,
> comfortable at that size). The upsampler also stays resident for the whole
> chunk (`first=True` only on the chunk's first frame), instead of being
> re-staged per image as the live path does.
>
> On 16 GB the same phases leave ~5 GB of headroom in phase A; the live path
> also becomes usable there, at the streaming cost above. Below 12 GB the
> family does not fit.
>
> **Steps**: the config ships **8**, and the GUI's *Colorization Steps* wins
> (the reference workflow uses 16). Start at 8 and raise it only if a frame
> comes out flat.
>
> **Upsampler cost**: the 9B encoder is what buys the recognition, and it is
> not free — one extra pass per image. In the paired flow it is amortized over
> two frames, which is where this family gains the most.

> Launch with `start_server.cmd flux3_klein_6b_int8`.

### All backends

| Requirement | Details                |
| ----------- | ---------------------- |
| **OS**      | Windows 10/11 or Linux |
| **Python**  | 3.12                   |
