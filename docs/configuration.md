# Pipeline configuration

Ready-to-use config files for both backends are in the `config/` folder.
Pick the one that matches your hardware and pass it to `--pipeline-config`.
The GUI lists every `.json` file in `config/` as a **Model Config** entry
(Tab 2) and loads the selected file, so adding a model only means adding a
config file here.

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

### Qwen-Image-Edit 2511 Backend : `config/qwen-2511_int8.json` / `config/qwen-2511_q3.json`

The Qwen-Image-Edit 2511 configs share the same structure
(`model_name: "gguf-qwen"`); the UNet entry selects the checkpoint format:

| Config file           | UNet                                     | Class                     |
| --------------------- | ---------------------------------------- | ------------------------- |
| `qwen-2511_int8.json` | native `…_2511_int8_convrot.safetensors` | 16 GB+ VRAM — recommended |
| `qwen-2511_q3.json`   | `…2511-Q3_K_S.gguf`                      | 12 GB+ VRAM               |

> **`qwen-2511_int8` is the recommended config**: it loads the official
> Comfy-Org int8 ConvRot checkpoint through the native UNet loader (not the
> GGUF dequantizer) and runs measurably faster per frame than the GGUF
> quants. `qwen-2511_q3` (GGUF Q3_K_S) remains the choice for 12 GB-class
> GPUs, with one caveat measured in a side-by-side run: at Q3 fine details
> can shift (the character's expression changed — a smile appeared), so
> prefer `qwen-2511_int8` whenever 16 GB of VRAM is available. Both share
> the same VAE, mmproj and LoRA files (auto-downloaded from HuggingFace);
> the CLIP stays GGUF in both.

> **⚠️ The GGUF backend is experimental.** In some cases the frames colors may be faded or little colored. For production use, prefer `nunchaku-qwen` (FP4/INT4) or `qwen21-viggle`, which are not affected by such problems — see the recommendation note at the top of this README.

Config example (`config/qwen-2511_int8.json`):

```json
{
    "model_name":       "gguf-qwen",
    "quant":            "int8",
    "unet_gguf":        "models/unet/qwen_image_edit_2511_int8_convrot.safetensors",
    "unet_hf_name":     "split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors",
    "clip_gguf":        "models/clip/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
    "clip_mmproj":      "models/clip/Qwen2.5-VL-7B-Instruct-mmproj-BF16.gguf",
    "clip_mmproj_hf_name": "mmproj-BF16.gguf",
    "vae_name":         "qwen_image_vae.safetensors",
    "lora_path":        "models/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
    "steps":            4,
    "hf_unet":          "Comfy-Org/Qwen-Image-Edit_ComfyUI",
    "hf_clip":          "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
    "hf_vae":           "Comfy-Org/Qwen-Image_ComfyUI",
    "hf_lora":          "lightx2v/Qwen-Image-Edit-2511-Lightning"
}
```

> `unet_gguf` also accepts a `.safetensors` UNet (loaded natively instead of
> through the GGUF dequantizer); `unet_hf_name` is the remote filename to
> fetch when it differs from the local basename — Comfy-Org keeps this
> checkpoint under `split_files/diffusion_models/`.

> `clip_mmproj_hf_name` exists because the mmproj file's name on HuggingFace
> (a generic `mmproj-BF16.gguf`, shared across many unrelated repos) rarely
> matches the locally-prefixed name you actually want on disk — it tells
> the downloader what to fetch, `clip_mmproj` is where it ends up and what
> the loader looks for locally. Omit it and the downloader falls back to
> using `clip_mmproj`'s own filename as the remote name too, which only
> works if they happen to match.

#### LoRA (Lightning 4-step)

The LoRA file `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` enables **4-step inference** (down from 20-50 steps without LoRA). It is a ComfyUI-format LoRA that gets merged directly into the transformer at load time.

- **With LoRA**: call `colorize_image(..., steps=4)`  :  fast, same quality
- **Without LoRA**: set `full_model_path` to `""` and use `steps=20` or higher

The LoRA is merged statically (not applied as an adapter), so there is no runtime overhead.

### qwen21-viggle Backend : `config/qwen21_viggle.json` & `qwen21_viggle-{soft,sharp}_{int8,q4}.json`

The default config uses the int8 ConvRot UNet with the Viggle-Turbo LoRA
applied at load time; **merged-LoRA variants** are also provided
(`soft_*`/`sharp_*` — see the subsection below). The CLIP, unlike the UNet,
can be either a `.safetensors` file or a GGUF+mmproj pair — the default
uses GGUF+mmproj (see [What's New](whats-new.md)):

```json
{
    "model_name":          "qwen21-viggle",
    "unet_name":           "models/unet/qwen_image_2.1_int8_convrot.safetensors",
    "clip_name":           "models/clip/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
    "clip_mmproj":         "models/clip/Qwen3-VL-8B-Instruct-mmproj-BF16.gguf",
    "clip_mmproj_hf_name": "mmproj-BF16.gguf",
    "vae_name":            "qwen_image_2.1_vae_bf16.safetensors",
    "lora_path":           "models/loras/Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors",
    "steps":               6,
    "hf_unet":             "Comfy-Org/Qwen-Image-2.1",
    "hf_clip":             "unsloth/Qwen3-VL-8B-Instruct-GGUF",
    "hf_vae":              "Comfy-Org/Qwen-Image-2.1",
    "hf_lora":             "Viggle/Qwen-Image-2.1-viggle-turbo"
}
```

> Note the different key names from the GGUF-backend format above: `unet_name`/
> `clip_name` (not `unet_gguf`/`clip_gguf`) — but unlike the GGUF backend,
> `clip_name` here can point to *either* a `.safetensors` file *or* a
> `.gguf` file (the loader picks the right code path from the extension).
> `clip_mmproj`/`clip_mmproj_hf_name` only apply when `clip_name` is a
> `.gguf` file — omit both to use a `.safetensors` CLIP instead:
>
> ```json
>     "clip_name":   "models/text_encoders/qwen3vl_8b_int8_convrot.safetensors",
> ```
>
> `steps: 6` here only documents the LoRA's native
> step count for anyone reading the file; the actual number of steps used
> at inference time is the `steps` argument passed per-call to the
> colorization RPC methods (see [Suggested Inference Steps](server_usage.md#-suggested-inference-steps)
> and [RPC API Reference](rpc-api.md)), same as every other backend.

> **Merged-LoRA checkpoints** (e.g. the `v0.2.1-6step-*` / `v0.3-6step-*`
> files in the
> [Viggle repo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo),
> which already contain the LoRA) simply omit `lora_path` (or leave it
> empty); when such a file lives at the *root* of its HuggingFace repo, add
> `unet_hf_name` with its filename as it exists upstream — the next
> subsection shows ready-to-use examples.

#### Merged-LoRA variants : `config/qwen21_viggle-{soft,sharp}_{int8,q4}.json`

The [Viggle repo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo)
also publishes checkpoints that **already contain the Viggle-Turbo LoRA**.
Four configs ship them, in two model generations — **v0.3** (`soft_*`) and
**v0.2.1** (`sharp_*`) — and two formats: **int8 ConvRot** (`.safetensors`,
~6.75 GB) and **GGUF `Q4_K_M`** (~4 GB). No LoRA is applied at runtime.
Example (`qwen21_viggle-soft_int8.json`):

```json
{
    "model_name":          "qwen21-viggle",
    "unet_name":           "models/unet/Qwen-Image-2.1-viggle-turbo-v0.3-6step-int8_convrot.safetensors",
    "unet_hf_name":        "Qwen-Image-2.1-viggle-turbo-v0.3-6step-int8_convrot.safetensors",
    "clip_name":           "models/clip/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
    "clip_mmproj":         "models/clip/Qwen3-VL-8B-Instruct-mmproj-BF16.gguf",
    "clip_mmproj_hf_name": "mmproj-BF16.gguf",
    "vae_name":            "qwen_image_2.1_vae_bf16.safetensors",
    "lora_path":           "",
    "steps":               6,
    "hf_unet":             "Viggle/Qwen-Image-2.1-viggle-turbo",
    "hf_clip":             "unsloth/Qwen3-VL-8B-Instruct-GGUF",
    "hf_vae":              "Comfy-Org/Qwen-Image-2.1",
    "hf_lora":             ""
}
```

Differences from the default config above:

- `unet_name` points at the merged checkpoint (downloaded to
  `comfy_bridge/models/unet/` on first use, like every other model file);
  the `*_q4` variants point at a `.gguf` file instead — the loader detects
  the extension and uses the ComfyUI-GGUF recipe;
- `lora_path` is empty — the checkpoint is loaded as-is, the loader skips
  the runtime LoRA hook;
- `unet_hf_name` gives the filename as it exists on the Viggle repo: the
  merged files sit at the **repo root**, where the loader's default
  auto-download path would be the Comfy-Org-style
  `diffusion_models/<local filename>` (which does not exist there → 404);
- `hf_lora` is unused (empty) — nothing to download for a LoRA;
- `steps: 6` matches the checkpoints' native step count.

> **Field notes** (author's tests, RTX 5070 Ti, 2026-10-07): prefer
> `int8_convrot` — best output quality and the fastest of the tested
> variants. The GGUF `Q4_K_M` download is the smallest but in practice did
> not reduce VRAM nor run faster, with quality below int8 — use it when the
> download size matters.

> The GUI lists each file in **Model Config** by its file name (e.g.
> `qwen21_turbo_int8`), next to the shipped default `qwen21_viggle-soft_int8`.

### qwen21-turbo Backend : `config/qwen21_turbo_int8.json` & `qwen21_turbo-fast_int8.json`

The official Qwen-Image-2.1-Turbo repack (Comfy-Org): the base
Qwen-Image-2.1 architecture with the turbo distillation baked into the
checkpoint (no LoRA, no prompt enhancer). Two configs ship, identical but
for the paired-split flag:

| Config file                    | Fast Pipeline mode                  |
| ------------------------------ | ----------------------------------- |
| `qwen21_turbo_int8.json`       | standard split (one frame per pass) |
| `qwen21_turbo-fast_int8.json`  | **paired split** (`fast_split_TE`)  |

> Not the shipped default: the turbo family colors better than the viggle
> family but less stably (field verdict 2026-10-11), so the default stayed on
> `qwen21_viggle-soft_int8`. Both turbo configs ship for the manual pick.

Same key set as `qwen21-viggle` minus the LoRA keys:

```json
{
    "model_name":          "qwen21-turbo",
    "unet_name":           "models/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors",
    "clip_name":           "models/text_encoders/qwen3vl_8b_int8_convrot.safetensors",
    "vae_name":            "qwen_image_2.1_vae_bf16.safetensors",
    "lora_path":           "",
    "steps":               8,
    "fast_split_TE":       true,
    "split_TE_resolution": 1024,
    "hf_unet":             "Comfy-Org/Qwen-Image-2.1",
    "hf_clip":             "Comfy-Org/Qwen-Image-2.1",
    "hf_vae":              "Comfy-Org/Qwen-Image-2.1"
}
```

> Pick the config in the GUI's **Model Config** combo to switch modes: the
> two variants write to **separate caches** (`ref_te/` vs `ref_te_pair/`), so
> switching never mixes a single-flow cache with a paired one.

> The checkpoint carries its **own 8-step sigma schedule** (the same table
> published as `sample_sigmas` in `Qwen/Qwen-Image-2.1-Turbo`), so the step
> count is fixed at 8 for this family: the GUI's *Colorization Steps*
> setting does not apply (a notice is logged). It has no image-aware prompt
> enhancer -- and, like qwen21-viggle, it wants a **detailed prompt**.

#### Paired split (`fast_split_TE`)

`"fast_split_TE": true` (string forms `"on"` / `"1"` / `"yes"` also work)
makes the Fast Pipeline pair consecutive frames inside the split flow: the
two frames are merged side by side *before* the text encoder and the decoded
canvas is split back *after* the transformer -- one TE pass and one sampling
pass per two frames instead of one of each per frame. The pair shares the
single flow's area budget, so each frame is colorized at about half that
budget's resolution. It applies to every split-TE family (`qwen21-viggle`,
`qwen21-turbo`, `gguf-qwen`); models without split-TE support never see the
option, because the flag only lives in the configs of the families that use
it.

#### Split-TE working resolution (`split_TE_resolution`)

`"split_TE_resolution"` (default `1024`) is the area budget the split-TE
flows work at: per frame in the single flow, per merged canvas in the paired
one. Raising it keeps more spatial detail, at a cost roughly proportional to
the area increase (clamped to `256`–`2048`, snapped to multiples of 32). It
applies to `qwen21-viggle` / `qwen21-turbo`; for `gguf-qwen` the working size
comes from the edit node's own image scale, so the key is ignored there.
Changing it invalidates the conditioning cache automatically (the value is
part of the cache key), so the next run re-encodes and does not mix
resolutions.

> **Field note** (paired turbo, 4 frames, RTX 5070 Ti): the pair splits its
> budget between the two frames, so `1024` gives each frame ~0.5 Mpx while
> the single flow gets the full ~1.0 Mpx — the source of the pair's slightly
> softer look. Measured pair cost: `1024` → **2.27 s/frame**, `1280` →
> **3.88**, `1536` → **6.49** (single flow at `1024`: 4.49). The color
> rendition also shifts with the budget (of the three, `1280` rendered the
> most neutral/coolest and `1536` the warmest), so tune it against your own
> material — sample sheets in `dist/turbo_bench/`.

### Key reference

| Key                                       | Required | Description                                                                                  |
| ----------------------------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `model_name`                              | ✅        | `"nunchaku-qwen"`, `"gguf-qwen"`, `"longcat-gguf"`, `"qwen21-viggle"`, or `"qwen21-turbo"`                     |
| `quant`                                   |          | **GGUF only**: quantization level (`"q3"`, `"q4"`, `"q5"`, `"q6"`, `"q8"`). Default: `"q4"`  |
| `model_precision`                         | ✅        | **Nunchaku**: `"fp4"` (RTX 50) or `"int4"` (RTX 30/40). **GGUF/qwen21-viggle**: not used     |
| `unet_gguf` / `clip_gguf`                 | ✅        | **GGUF only**: local paths to the GGUF model files                                           |
| `unet_name` / `clip_name`                 | ✅        | **qwen21-viggle / qwen21-turbo**: local paths to the model files — `unet_name` can be `.safetensors` or `.gguf` (GGUF quants load through the same ComfyUI-GGUF recipe as the gguf backends), `clip_name` can be `.safetensors` or `.gguf` |
| `clip_mmproj` / `clip_mmproj_hf_name`     |          | **GGUF/qwen21-viggle-with-GGUF-CLIP**: local path to the mmproj (vision tower) file / its filename on HuggingFace if different from the local one. Required for a GGUF CLIP to see images at all — without it the vision tower silently isn't loaded |
| `unet_hf_name`                            |          | **qwen21-viggle / qwen21-turbo**: UNet filename on HuggingFace when it differs from the default download path (`diffusion_models/<local filename>`, the Comfy-Org layout) — e.g. merged checkpoints kept at the repo root. Only used by auto-download |
| `model_rank`                              |          | **Nunchaku**: SVD rank (`"32"`). **GGUF/qwen21-viggle**: not used                            |
| `model_inference_steps`                   |          | **Nunchaku**: diffusion steps (`"4"`). **GGUF/qwen21-viggle**: not used at load time          |
| `cache_dir`                               |          | HuggingFace cache directory. Leave empty to use the default `~/.cache/huggingface`           |
| `full_model_path`                         |          | **Nunchaku**: local path to the transformer checkpoint. **GGUF**: not used                   |
| `lora_path`                               |          | **GGUF/qwen21-viggle**: path to the LoRA (`.safetensors`). Omit (or empty) to skip LoRA merging — e.g. GGUF, or a qwen21-viggle checkpoint with the LoRA already merged in |
| `steps`                                   |          | **GGUF**: inference steps (`4` with LoRA, `20` without). **qwen21-viggle**: documents the native step count only, not consumed at load time. **qwen21-turbo**: fixed at 8 by the checkpoint's own schedule |
| `vae_name`                                |          | **GGUF / qwen21-viggle / qwen21-turbo**: VAE filename                                                    |
| `hf_*`                                    |          | **GGUF / qwen21-viggle / qwen21-turbo**: HuggingFace repo names for auto-download                        |
| `fast_split_TE`                           |          | **Split-TE families** (`qwen21-viggle` / `qwen21-turbo` / `gguf-qwen`): `true` (or `"on"`/`"1"`/`"yes"`) makes the Fast Pipeline pair consecutive frames -- merged before the text encoder, split back after the transformer. Default off |
| `split_TE_resolution`                     |          | **qwen21-viggle / qwen21-turbo**: area budget of the split-TE flow (default `1024`; per frame in the single flow, per merged canvas in the paired one). Clamped to 256–2048, snapped to 32 |
