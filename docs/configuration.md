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

### GGUF Backend : `config/qwen_gguf_q3.json` … `qwen_gguf_q8.json` / `config/longcat_gguf_q3.json` … `longcat_gguf_q8.json`

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

> **⚠️ The GGUF backend is experimental.** In some cases the frames colors may be faded or little colored. For production use, prefer `nunchaku-qwen` (FP4/INT4) or `qwen21-viggle`, which are not affected by such problems — see the recommendation note at the top of this README.

Config example (`config/qwen_gguf_q4.json`):

```json
{
    "model_name":       "gguf-qwen",
    "quant":            "q4",
    "unet_gguf":        "models/unet/qwen-image-edit-2511-Q4_K_S.gguf",
    "clip_gguf":        "models/clip/Qwen2.5-VL-7B-Instruct-Q4_K_S.gguf",
    "clip_mmproj":         "models/clip/Qwen2.5-VL-7B-Instruct-mmproj-BF16.gguf",
    "clip_mmproj_hf_name": "mmproj-BF16.gguf",
    "vae_name":         "qwen_image_vae.safetensors",
    "lora_path":        "models/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
    "steps":            4,
    "hf_unet":          "unsloth/Qwen-Image-Edit-2511-GGUF",
    "hf_clip":          "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
    "hf_vae":           "Comfy-Org/Qwen-Image_ComfyUI",
    "hf_lora":          "lightx2v/Qwen-Image-Edit-2511-Lightning"
}
```

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

### qwen21-viggle Backend : `config/qwen21_viggle.json` & `qwen21_viggle-soft_fp8.json`

The default config uses the int8 ConvRot UNet with the Viggle-Turbo LoRA
applied at load time; a **merged-LoRA fp8 variant** is also provided as a
separate config file (see the subsection below). The CLIP, unlike the UNet,
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
> colorization RPC methods (see [Suggested Inference Steps](usage.md#-suggested-inference-steps)
> and [RPC API Reference](rpc-api.md)), same as every other backend.

> **Merged-LoRA checkpoints** (e.g. the `v0.3-6step-*` files in the
> [Viggle repo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo),
> which already contain the LoRA) simply omit `lora_path` (or leave it
> empty); when such a file lives at the *root* of its HuggingFace repo, add
> `unet_hf_name` with its filename as it exists upstream — the next
> subsection shows a ready-to-use example.

#### Merged-LoRA variant : `config/qwen21_viggle-soft_fp8.json`

The [Viggle repo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo)
also publishes checkpoints that **already contain the Viggle-Turbo LoRA**
(the `v0.3-6step-*` files), including this fp8_e4m3fn safetensors (~6.75 GB).
This config uses it directly — no LoRA is applied at runtime:

```json
{
    "model_name":          "qwen21-viggle",
    "unet_name":           "models/unet/Qwen-Image-2.1-viggle-turbo-v0.3-6step-fp8_e4m3fn.safetensors",
    "unet_hf_name":        "Qwen-Image-2.1-viggle-turbo-v0.3-6step-fp8_e4m3fn.safetensors",
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

- `unet_name` points at the merged fp8 checkpoint (downloaded to
  `comfy_bridge/models/unet/` on first use, like every other model file);
- `lora_path` is empty — the checkpoint is loaded as-is, the loader skips
  the runtime LoRA hook;
- `unet_hf_name` gives the filename as it exists on the Viggle repo: the
  merged files sit at the **repo root**, where the loader's default
  auto-download path would be the Comfy-Org-style
  `diffusion_models/<local filename>` (which does not exist there → 404);
- `hf_lora` is unused (empty) — nothing to download for a LoRA;
- `steps: 6` matches the checkpoint's native step count.

> The GUI lists it in **Model Config** as `qwen21_viggle-soft_fp8`, next to
the default `qwen21_viggle`.

### Key reference

| Key                                       | Required | Description                                                                                  |
| ----------------------------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `model_name`                              | ✅        | `"nunchaku-qwen"`, `"gguf-qwen"`, `"longcat-gguf"`, or `"qwen21-viggle"`                     |
| `quant`                                   |          | **GGUF only**: quantization level (`"q3"`, `"q4"`, `"q5"`, `"q6"`, `"q8"`). Default: `"q4"`  |
| `model_precision`                         | ✅        | **Nunchaku**: `"fp4"` (RTX 50) or `"int4"` (RTX 30/40). **GGUF/qwen21-viggle**: not used     |
| `unet_gguf` / `clip_gguf`                 | ✅        | **GGUF only**: local paths to the GGUF model files                                           |
| `unet_name` / `clip_name`                 | ✅        | **qwen21-viggle only**: local paths to the model files — `unet_name` is always `.safetensors`, `clip_name` can be `.safetensors` or `.gguf` |
| `clip_mmproj` / `clip_mmproj_hf_name`     |          | **GGUF/qwen21-viggle-with-GGUF-CLIP**: local path to the mmproj (vision tower) file / its filename on HuggingFace if different from the local one. Required for a GGUF CLIP to see images at all — without it the vision tower silently isn't loaded |
| `unet_hf_name`                            |          | **qwen21-viggle only**: UNet filename on HuggingFace when it differs from the default download path (`diffusion_models/<local filename>`, the Comfy-Org layout) — e.g. merged checkpoints kept at the repo root. Only used by auto-download |
| `model_rank`                              |          | **Nunchaku**: SVD rank (`"32"`). **GGUF/qwen21-viggle**: not used                            |
| `model_inference_steps`                   |          | **Nunchaku**: diffusion steps (`"4"`). **GGUF/qwen21-viggle**: not used at load time          |
| `cache_dir`                               |          | HuggingFace cache directory. Leave empty to use the default `~/.cache/huggingface`           |
| `full_model_path`                         |          | **Nunchaku**: local path to the transformer checkpoint. **GGUF**: not used                   |
| `lora_path`                               |          | **GGUF/qwen21-viggle**: path to the LoRA (`.safetensors`). Omit (or empty) to skip LoRA merging — e.g. GGUF, or a qwen21-viggle checkpoint with the LoRA already merged in |
| `steps`                                   |          | **GGUF**: inference steps (`4` with LoRA, `20` without). **qwen21-viggle**: documents the native step count only, not consumed at load time |
| `vae_name`                                |          | **GGUF/qwen21-viggle only**: VAE filename                                                    |
| `hf_*`                                    |          | **GGUF/qwen21-viggle only**: HuggingFace repo names for auto-download                        |
