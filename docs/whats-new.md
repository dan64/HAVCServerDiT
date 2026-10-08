# What's New

### 2026-10-08 — Model Config: pick the model from the `config/` folder (GUI)

Tab 2 (**Colorization**) no longer has separate **Model Name** and **Precision**
fields: a single **Model Config** dropdown (in the **Model Technical Details**
frame) lists every `.json` file found in the `config/` folder, shown by file
name. The selected file *is* the model — its `model_name` and paths decide
backend and quantization — so adding a new model now only means dropping a
config file in there: no code or GUI changes needed.

**Run Server** (and the Dashboard shortcut) start the server for the selected
config; the launch scripts accept the same names, so
`start_server.cmd <config-name>` starts any file in `config/` directly — the
historical short aliases (`q3`, `fp4`, `longcat`, …) still work, and a config
file *wins* on name collisions (see
[Windows Launch Script](usage.md#-windows-launch-script)).

Existing settings files are migrated automatically on next load (the saved
`model_name` / `model_precision` values are folded into `model_config`); no
manual action is needed. See [GUI — Tab 2, Colorization](gui.md#tab-2--colorization)
and [Pipeline Configuration](configuration.md).

### 2026-10-08 — qwen21-viggle: merged-LoRA variants (soft/sharp × int8/q4) and GGUF UNet support

The [Viggle repository](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo)
also publishes checkpoints that **already contain the Viggle-Turbo LoRA**.
Four new configs ship them — two model generations (**v0.3**, `soft_*`, and
**v0.2.1**, `sharp_*`) and two formats, **int8 ConvRot** (`.safetensors`,
~6.75 GB) and **GGUF `Q4_K_M`** (~4 GB, the `*_q4` files) — all selectable
through the new **Model Config** dropdown:

- `qwen21_viggle-soft_int8` / `qwen21_viggle-soft_q4`
- `qwen21_viggle-sharp_int8` / `qwen21_viggle-sharp_q4`

The qwen21-viggle backend now also loads a **`.gguf` UNet** through the same
ComfyUI-GGUF recipe used by the other GGUF backends, and the new optional
`unet_hf_name` key lets auto-download find checkpoints that upstream keep
outside the regular `diffusion_models/` layout (e.g. at the repository root).
No LoRA is applied at runtime — the merged weights are loaded as they are.

> Field notes (author's tests, RTX 5070 Ti): prefer **int8**_convrot_ — best
> output quality and the fastest of the tested variants. The GGUF `Q4_K_M`
> quants download smaller but did not reduce VRAM nor run faster, with
> quality below int8; use them when the download size matters.

See [Pipeline Configuration → Merged-LoRA variants](configuration.md).

### 2026-10-07 — "Mux all streams" option (GUI)

A new **Mux all streams** checkbox in the **Encode/Merge** tab makes the
final `mkvmerge` step copy **all the remaining tracks of the source video**
— audio, subtitles and chapters — into the output `.mkv`, alongside the
freshly encoded video. The source's *video* track is excluded (the encoded
one always wins) and chapters are carried over at their original timecodes.

It applies to every final mux the tool produces: the **x265** / **x264** /
**Nvenc** encodes, the **Merge** step, and the **Fix Video** recolor output.
It is **off** by default — exactly the previous behavior — and saved with
the rest of the GUI settings (`mux_all_streams`). If the source video can't
be found when the mux runs, a warning is logged and the output stays
video-only.

See [GUI — Tab 3, Encode / Merge](gui.md#tab-3--encode--merge).

### 2026-10-04 — new version vs-cmnet2 v1.2.1

**vs-cmnet2:** fixed bug in vs-cmnet2 not allowing _vs_cmnet2_recolor()_ to properly load the reference frames. Due to the bug, the recolored clip had washed out colors in the recolored range. 

### 2026-10-02 — Run Server managed by the GUI, with a live Server Log (GUI)

**Run Server** (Tab 2, Colorization) now starts and stops the RPC server
itself instead of just launching a `.cmd` file in its own terminal window:
the server runs as a hidden child process controlled by the GUI, and its
full output streams live into a new **Server Log** tab — right next to the
existing log, now labeled **App Log** — in the Dashboard. The button
becomes **Stop Server** while it's running, and a status line next to it
tracks the sequence: *Starting server on ...* → *running on ...* (once the
server actually reports it's listening) → *stopped*.

Once the server reports it's ready, the GUI **connects automatically** —
no need to also click **Connect** on Tab 2. Closing the GUI (or clicking
**Stop Server**) always shuts the process down cleanly; the RPC connection
indicator resets to *Disconnected* at the same time, since the server it
was talking to is gone.

A new **External console** checkbox next to the button restores the
previous behavior exactly (a separate visible console window, started and
left running independently of the GUI) for anyone who prefers it or needs
to keep an eye on the raw console.

A **Local DiT Server** frame on the Dashboard mirrors the **Run Server**
button and its status text, so the server can be started/stopped without
switching to Tab 2.

**START PIPELINE** also uses this: if the **3. Colorize Frames (AI)** task
is enabled and the client isn't connected yet, the GUI starts the DiT
server automatically (same as clicking **Run Server**) and holds the
pipeline start until it reports it's actually online, instead of just
failing with "not connected". This only applies when **Run Server** is
GUI-managed (**External console** unchecked) — with an external console
there's no way for the GUI to know when that separate process is ready, so
the previous behavior (an error asking to connect manually) still applies
there.

### 2026-10-01 — Select Reference Frames task (GUI)

A new optional Dashboard task, **2. Select Reference Frames**, has been added
between **Extract** and **Colorize** — every task after it, is renumbered
(Colorize/Encode/Merge become tasks 3/4/5). It deduplicates the reference
frames extracted in Step 1 by semantic similarity (DINOv3-based, via
`vscmnet2.vs_select_reference_frames()`), reducing redundant near-identical
candidates before they reach colorization — useful for long or slow-changing
scenes where scene-change detection alone still produces many visually
similar frames.

The task renames `ref_tht10/` (produced by Extraction) to `ref_tht10_temp/`,
then writes the deduplicated representative frames back to a freshly created
`ref_tht10/` — the same folder Colorize already reads from, so no other step
changes. `ref_tht10_temp/` is kept as a full backup of every extracted
candidate unless **Move Files** is checked. If `ref_tht10/` is missing/empty,
or `ref_tht10_temp/` already exists from an interrupted previous run, the
task stops the entire pipeline with an error rather than guessing or
overwriting anything.

New **Selection Settings** frame in the GUI's Extraction tab exposes
`similarity_threshold`, `select_window`, and the `Dry Run`/`Debug HTML`/
`Move Files` options.  If `Debug HTML` is checked, in the output folder is written the file cluster_debug.html. This files contains all the reference clusters as shown in the image below

![Reference Selection](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/ref-frames_selection_debug-view.jpg)

for example in the Cluster 2, the reference frame #000145 was selected to represent all the references included in the Cluster 2. If the parameter similarity threshold is set above 0.95 will be selected smaller clusters, vice-versa if the threshold is set below 0.95 the similarity clusters will be bigger (will be available less reference frame to colorize). 

This _deduplication_ of keyframes will improve color consistency and _accelerate_ the coloring process, as fewer images will need to be colored.    

See [GUI README: Tab 1](gui.md#tab-1--extraction)
for the full workflow and recovery steps if a run is interrupted.

> Existing `gui_cmnet2_settings.json` files are migrated automatically on
> next load — no manual action needed.

### 2026-09-30 — Fix Colors: Backbone selection (GUI)

The **Fix Colors** tab (Tab 5) now exposes a **Backbone** combo (`dinov3` /
`dinov2`), passed as the `backbone` parameter of `vscmnet2.pil_cmnet2_colorize()`
— the same choice already available in **Encode/Merge** (Tab 3) and **Fix
Video** (Tab 6), now consistent across all three tabs that drive CMNET2.
Previously the tab always used the `vscmnet2` default (`dinov3`) with no way
to select the legacy DINOv2 backbone. Applies in both single-image and batch
mode. Persisted in `gui_cmnet2_settings.json` as `fixc_backbone`.

### 2026-09-29 — qwen21-viggle: GGUF+mmproj CLIP as new default, `clip_mmproj` generalized, known limitation documented

**New default CLIP for `qwen21-viggle`**: `Qwen3-VL-8B-Instruct-UD`
(GGUF+mmproj, `unsloth/Qwen3-VL-8B-Instruct-GGUF`), loaded through a
vendored `ComfyUI-GGUF-Reboot` custom node (the standard `ComfyUI-GGUF`
does not support merging a separate mmproj file for the `qwen3vl`
architecture — only `qwen2vl`, used by `gguf-qwen`/`longcat-gguf`).
Replaces the `.safetensors` CLIP options evaluated (`int8_convrot`,
`fp8_scaled`, `w4a8`) as the default: same disk footprint as the lightest
of those (`w4a8`, ~5.9GB) but without a chromatic-drift issue found on
subjects with a strong color convention (`w4a8` occasionally converged on
the wrong hue where the other options didn't). The `int8_convrot`/`w4a8`
files remain valid alternatives — see [Pipeline Configuration](configuration.md).

**`clip_mmproj`/`clip_mmproj_hf_name`** (config fields) generalized from
`qwen21-viggle` to `gguf-qwen`/`longcat-gguf` too, replacing the old
`mmproj_gguf` key (which was never actually read by any code — dead
documentation only). This also closed a real gap: `longcat-gguf` never had
*any* mechanism to auto-download its own mmproj file — it only worked
because the file was already present from `gguf-qwen` sharing the same
folder. A from-scratch `longcat-gguf`-only installation would have loaded
its CLIP without a working vision tower.

**Known limitation, extensively investigated**: on some frames, a human
body part near a visually similar background (e.g. a hand close to
foliage) can be rendered with the wrong color (blended into the
background) instead of a natural skin tone — confirmed across the entire
Qwen-Image-2.1/Viggle-Turbo family, including Viggle's own official demo
app and `longcat-gguf`, and independent of which CLIP quantization/variant
is used (`int8`, `fp8`, `w4a8`, and several GGUF text-encoder builds were
tested). This appears to be a genuine limitation of the underlying models
for this kind of ambiguous content, not a bug in this integration. If a
frame is affected, `nunchaku-qwen`/`gguf-qwen` are unaffected by the same
issue and can be used as a fallback.

### 2026-09-28 — qwen21-viggle: higher working resolution for Fast Pipeline

Paired inference (_Fast Pipeline_) for `qwen21-viggle` now uses a working
resolution of **1280** instead of the usual 1024 (single-image and every
other backend are unaffected). This fixes a color artifact found on frames
with fine detail near the merge boundary — a hand, held up close to the
camera, could be rendered in tones nearly indistinguishable from the
background foliage instead of a natural skin tone. The cause was the
reduced working resolution from paired inference combined with
Viggle-Turbo's own limits on fine detail; raising it to 1280 resolves the
artifact in every case tested, at a real but modest speed cost (~6
sec/frame instead of 4 — see the recommendation note near the top of this
README). 1536 was
tested too and fixes the same artifact slightly more completely, at
roughly double the extra cost; 1280 was chosen as the better trade-off
after validation on thousands of real frames.

### 2026-09-27 — vscmnet2 1.1.0 (proximity bias now a per-call parameter)

Updated to `vscmnet2` 1.1.0. The _proximity-weighted memory matching_ feature added in 1.0.9 (see below) is no longer installation-wide only: `vs_cmnet2` now accepts `enable_proximity_bias`/`proximity_bias_alpha` directly, taking precedence over `vsslib/models.json` when passed explicitly for a single call.

```python
clip = vs_cmnet2(
    clip,
    clip_ref=ref_clip,
    method=0,
    enable_proximity_bias=True,
    proximity_bias_alpha=0.5,
)
```

`vs_cmnet2_recolor`/`vs_cmnet2dit` are unchanged — they still only pick up the installation-wide default from `vsslib/models.json`. Exposed in the GUI's **Encode/Merge** tab only (the tab backed by `vs_cmnet2`), in a new **CMNET2 Backbone** frame grouping **Backbone**, **Proximity Bias** and **Alpha** together: the latter two are automatically disabled when **Backbone = dinov2** (DINOv3-only feature) and re-enabled on switching back to **dinov3**. Unchecked always forces `enable_proximity_bias=False` for that run (an explicit override, not "leave it to `models.json`"). Not added to **Fix Video** (backed by `vs_cmnet2_recolor`, which doesn't accept these parameters).

> **Existing installations, action needed**: the shipped DINOv3 checkpoint was renamed
> `DINOv3FeatureV6_LocalAtten_p372402.pth` → `DINOv3FeatureV6_LocalAtten_p374099.pth`
> (default `proximity_bias_alpha` also changed 0.7 → 0.5). Re-download the checkpoint
> under the new name — see [DINOv3 backbone weights](gui.md#dinov3-backbone-weights-required-default-since-108).
> If the old file is left in place, `vscmnet2` fails fast at init with a clear error
> listing the files actually present in the weights directory.

### 2026-09-26 — qwen21-viggle Backend

A fourth model backend has been added: **qwen21-viggle** (Qwen-Image-2.1
native ComfyUI weights + [Viggle-Turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo)
LoRA). Uses native **int8 ConvRot** quantized weights (not GGUF) — GGUF
quantization was evaluated and works, but is ~2× slower for this model, so
it was not adopted. Runs on 14GB+ VRAM GPUs, ~8-11 sec/frame (the time
scales little with the number of steps — a fixed text-encoding/VAE-decode
cost dominates over sampling).

> **To use this backend on an existing installation**: `git pull` then run
> `quick_update.cmd` — this pulls in the required `comfy-kitchen==0.2.35`/
> `comfy-aimdo==0.5.5` versions (see [Quick Update](installation.md#-quick-update-existing-installation))
> alongside the rest of the qwen21-viggle code.

Four model files are required (*auto-downloaded on first run*):

| File                                                                | Size    | Source                                                                                             |
| -------------------------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------- |
| `unet/qwen_image_2.1_int8_convrot.safetensors`                      | ~6.8 GB | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)                          |
| `clip/qwen3vl_8b_int8_convrot.safetensors`                          | ~8.7 GB | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)                          |
| `vae/qwen_image_2.1_vae_bf16.safetensors`                           | ~0.7 GB | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)                          |
| `loras/Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors` | ~0.7 GB | [Viggle/Qwen-Image-2.1-viggle-turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo)      |

Launch via `run_server_qwen21.cmd` (no arguments needed — a single config
is available). Config: `config/qwen21_viggle.json`.

**Steps**: the Viggle-Turbo LoRA is distilled for 6-step inference (its
native step count). Four precomputed sigma schedules are available —
`2`, `4`, `6` (native), `8` — selected via the usual `steps` parameter; any
other value falls back to the 6-step schedule with a warning in the logs.
2/4/8 are experimental (the LoRA author only documents 5-7 step schedules).

**`enhance_prompt`** (optional, default `False`, all colorization RPC
methods): rewrites the prompt using Qwen3-VL as an image-aware "observer"
before colorizing — useful when the plain prompt leaves color ambiguous on
recognizable subjects (e.g. a costume with a well-known color) and the
model resolves the ambiguity inconsistently. Adds ~15-20s per frame (a
second Qwen3-VL generation pass). A direct, explicitly anti-hedging prompt
often achieves the same result without the extra cost — see the
[suggested prompt](usage.md#-suggested-inference-steps) below before reaching for
`enhance_prompt` by default.

> **Prerequisite**: 12 GB+ VRAM and 32GB+ RAM. Uses `comfy_bridge`'s
> native ComfyUI runtime (no external ComfyUI checkout needed) — the same
> as `gguf-qwen`/`longcat-gguf`, extended with native Qwen-Image-2.1/Qwen3-VL
> support.

The GUI Tab 2 (Colorization) supports this backend: selecting
**qwen21-viggle** from Model Name auto-disables the (unused) Precision
combo and reads model paths from `config/qwen21_viggle.json`. **Run
Server** manages the equivalent of `run_server_qwen21.cmd` directly (see
[What's New, 2026-10-02](#2026-10-02--run-server-managed-by-the-gui-with-a-live-server-log-gui)) — or launches that same `.cmd` file
in its own console when the **External console** checkbox is ticked.
An **Enhance Prompt** checkbox is available in Tab 2 and Tab 4 (Fix Image).

### 2026-09-25 — x264 encoder option (GUI)

Added **x264** as a third software encoder choice in the GUI's Encode/Merge tab, alongside the existing `x265` (software, 10-bit) and `Nvenc` (GPU hardware, H.265). `x264` is an 8-bit H.264 CPU encoder — useful when H.265 decoding/compatibility is a constraint. The `x264.exe` binary is located next to `x265.exe`, same convention already used for `NVEncC64.exe` — no extra path field needed in the GUI. Now included in the Release 1.0.0 `tools.zip` alongside `x265.exe`/`mkvmerge.exe`. See [GUI README: install external tools](gui.md#5-install-external-tools).

### 2026-09-24 — vscmnet2 1.0.9 (proximity-weighted memory matching)

Updated to `vscmnet2` 1.0.9, which add _proximity-weighted memory matching_. By default, permanent-memory candidates are ranked purely by content similarity, with no notion of *when* in the video a reference frame was captured relative to the frame being colorized — with a wide `max_memory_frames` window holding several visually similar but differently-colored references, this can wash the result toward gray. Unlike `backbone`, this is **not** exposed as a filter parameter on `vs_cmnet2`: it is configured once for the whole installation via the `enable_proximity_bias`/`proximity_bias_alpha` keys in `vsslib/models.json` (see above). Off by default. To permanently enable it (useful for permanent memory window size > 50) it is necessary to set `enable_proximity_bias=true` in the configuration file stored in: `vsslib/models.json` as shown in the example below:

```json
{
  "cmnet2": {
    "dinov3": {
      "checkpoint": "DINOv3FeatureV6_LocalAtten_p374099.pth",
      "weights_dir": "dinov3-vitb16",
      "enable_proximity_bias": true,
      "proximity_bias_alpha": 0.5
    },
    "dinov2": {
      "checkpoint": "DINOv2FeatureV6_LocalAtten_s2_154000.pth"
    }
  }
}
```

### 2026-09-17 — vscmnet2 1.0.8 (DINOv3 Backbone)

Updated to `vscmnet2` 1.0.8, which switches CMNET2 to a **DINOv3 ViT-B/16** key-encoder backbone by default (previously DINOv2 ViT-S/14), improving colorization quality. The legacy DINOv2 backbone remains available via a `backbone` parameter.

A new **Backbone** combo (`dinov3` / `dinov2`) has been added to the GUI in both tabs that drive CMNET2 through VapourSynth:

- **Encode/Merge (Tab 3)** — `GUI/scripts/encode_cmnet2.vpy`
- **Fix Video (Tab 6)** — `GUI/scripts/encode_cmnet2_recolor.vpy`

Both scripts now pass the selected backbone to `vs_cmnet2()` / `vs_cmnet2_recolor()` via a `Backbone` VapourSynth argument, alongside the existing `RenderSpeed` and `MemoryFrames` parameters.

> **Prerequisite**: the DINOv3 backbone requires new weight files — see [GUI README: DINOv3 backbone weights](gui.md#dinov3-backbone-weights-required-default-since-108) for download links and install steps. The `dinov2` option remains available for installations that only have the legacy DINOv2 weights.

### 2026-07-10 — LongCat GGUF Backend

A third model backend has been added: **longcat-gguf** (LongCat-Image-Edit-Turbo GGUF).
Uses quantized UNet (Q4_K_M) and CLIP GGUF files — runs on 12 GB VRAM GPUs.
It achieves excellent colorization quality (~12 s/frame via the RPC server) — richer colors, more natural skin tones, and better detail preservation than the gguf-qwen model — and is accessible from all existing tabs and RPC endpoints.

Three new model files are required (*auto-downloaded on first run*):

| File                                        | Size    | Source                                                                                                                    |
| ------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------- |
| `unet/LongCat-Image-Edit-Turbo-Q4_K_M.gguf` | ~5.4 GB | [vantagewithai/LongCat-Image-Edit-Turbo-GGUF](https://huggingface.co/vantagewithai/LongCat-Image-Edit-Turbo-GGUF)         |
| `clip/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`   | ~4.6 GB | [unsloth/Qwen2.5-VL-7B-Instruct-GGUF](https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF)                         |
| `vae/lct_vae.safetensors`                   | ~160 MB | [meituan-longcat/LongCat-Image-Edit-Turbo](https://huggingface.co/meituan-longcat/LongCat-Image-Edit-Turbo/tree/main/vae) |

Launch via `run_server_longcat.cmd` (Q4_K_M) or `start_server.cmd longcat` (Q4), `longcat-q3`, `longcat-q5`, `longcat-q6`, `longcat-q8`. Pre-made configs for all quantizations are in the `config/` folder.

> **Prerequisite**: 12 GB+ VRAM and 32GB+ RAM. Uses GGUF quantized models.
> The pipeline uses the comfy_bridge runtime (no external ComfyUI checkout needed).
> Custom nodes `CFGNorm`, `FluxKontextMultiReferenceLatentMethod`, and
> `TextEncodeQwenImageEditPlus` are included in `comfy_bridge/comfy_extras/`.

The GUI Tab 2 (Colorization) now includes a **Run Server** button that manages
the server for the selected Model Name + Precision directly — see
[What's New, 2026-10-02](#2026-10-02--run-server-managed-by-the-gui-with-a-live-server-log-gui) for how it's started/stopped/logged, and
the **External console** checkbox for opening a plain terminal window instead.
This replaces the need to manually find and run the right `.cmd` file.

### 2026-07-01 — Batch Processing for Fix Image & Fix Colors (GUI)

The **Fix Image** (Tab 4) and **Fix Colors** (Tab 5) tabs now support batch
processing of multiple images:

**Fix Image (Tab 4):**

- New **Enable batch processing** checkbox — toggles between single-image and batch mode
- The image field is now a **ComboBox** showing all loaded images (drag & drop / Browse appends)
- **Colorize** processes all images sequentially against the DiT RPC server
- **Overwrite** overwrites all originals; **Save As** proposes a `*_colorized` wildcard mask
- Outputs are kept in memory until explicitly saved; errors on single images are skipped
- **Swap Output** is automatically disabled in batch mode

**Fix Colors (Tab 5):**

- Same batch logic on the **Target Image** field — multiple targets against one color reference
- ComboBox, Clear, sequential colorization via local CMNET2, wildcard save
- **Copy → Fix Image** disabled in batch mode

Both tabs share the same interaction pattern for batch mode — ComboBox list,
sequential processing with progress counter, wildcard `*` save mask, memory-only
outputs until explicit save — while each tab uses its own backend (DiT RPC for
Fix Image, local CMNET2 for Fix Colors).

### 2026-06-20 — Fix Colors Tab (GUI)

A standalone **Fix Colors** tab (`Tab 5`) has been added to the desktop GUI (`GUI/CMNET2_colorize_client_GUI.py`).

![GUI Tab #5](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page6.jpg)

It colorizes a B&W or colorized target image using a color reference image via the local **CMNET2** model
(exemplar-based color propagation) — no RPC server required:

1. **Load** a color reference image (drag & drop or Browse)
2. **Load** a B&W target image (drag & drop or Browse)
3. **Colorize** — runs `vscmnet2.pil_cmnet2_colorize()` in a background thread. It allows to propagate the reference colors to target image.

Key features:

- **Three preview panels**: reference, target, and output side‑by‑side
- **Copy → Fix Image**: sends the output directly to Tab 4 (Fix Image) for a two‑stage pipeline (CMNET2 → DiT RPC)
- **Save / Overwrite**: save the colorized result as PNG/JPG or overwrite the original target file
- **Full-resolution preservation**: images are always kept at original resolution in memory; resizing only applies to previews
- **Delayed import**: `vscmnet2` is imported only when Colorize is clicked (does not block GUI startup)
- **Backbone selection** (`dinov3` / `dinov2`, since 2026-09-28): passed to `vscmnet2.pil_cmnet2_colorize()` — same combo already available in Encode/Merge (Tab 3) and Fix Video (Tab 6)

> **Prerequisite**: `vscmnet2` must be installed with model weights and checkpoints present (see [GUI README](gui.md#3-install-vscmnet2)). No RPC connection needed.

The tab order has been updated: **1.** Extraction → **2.** Colorization → **3.** Encode/Merge → **4.** Fix Image → **5.** Fix Colors → **6.** Fix Video.

### 2026-06-17 — Fix Video Tab (GUI)

A standalone **Fix Video** tab (`Tab 6`) has been added to the desktop GUI (`GUI/CMNET2_colorize_client_GUI.py`).
It runs a VapourSynth + NVEnc pipeline to recolor a video using two reference images:

![GUI Tab #6](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page7.jpg)

1. **Select** a video and an encode VPY script
2. **Load** two reference images (First / Last) via drag-and-drop or Browse
3. **Recolor** — runs the VapourSynth → NVEnc pipeline and produces `_dt-recolor.mkv`

Key features:

- **NVEnc-only**: uses GPU hardware encoding (NVEncC64.exe required)
- **RefStart / RefEnd**: reference images passed to the VapourSynth script as parameters
- **RefDir auto-detection**: set to the folder of the first reference image
- **Configurable**: FPS, VBR Quality, Memory Frames, Render Speed, Backbone
- **MKV output**: `.h265` intermediate automatically muxed to `.mkv` and deleted
- **Pre-flight check**: verifies NVEncC64.exe exists before starting

The Fix Video tab is independent of the batch pipeline and does not require the RPC server.
Only the frames between **RefStart / RefEnd** will be recolored. 

> **Prerequisite**: NVEncC must be installed in `tools\NVEncC\` (see [GUI README](gui.md#5-install-external-tools)).

### 2026-06-12 — Fix Image Tab (GUI)

A standalone **Fix Image** tab (`Tab 4`) has been added to the desktop GUI (`GUI/CMNET2_colorize_client_GUI.py`).
It allows single-image colorization with seed control, drag-and-drop file loading, and preview:

![GUI Tab #4](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page5.jpg)

1. **Load** a B&W image via drag-and-drop (`GUI/load_image_DtD_GUI.py`) or the Browse button
2. **Colorize** with fixed seed (42) or random seed for variation
3. **Save** the colorized result as PNG / JPG

The Fix Image tab is independent of the batch video pipeline and does not require VapourSynth.

> If you already created the `.venv` with a previous version
> install the package tkinterDnD2 to add drag-and-drop support to tkinter

```bash
# Windows
.venv\Scripts\activate
(.venv) pip install tkinterDnD2
```

### 2026-06-09 — Improved GGUF

Changed the GGUF configuration files. The pipeline Qwen-Image-Edit-2511 + Qwen-Image-Edit-2511-Lightning-4steps has substituted by the pipeline with  Qwen-Image-Edit-2509 + Qwen-Image-Edit-2511-Lightning-4steps. This change has removed the artifacts problem which affected the colored images with the GGUF models and improved the overall quality of the colored images. It should be noted that, despite these improvements, the Nunchaku model remains the best and is the one recommended for production use (*for systems with limited hardware resources, it is recommended to use the GGUFs of LongCat-Image-Edit-Turbo added on July 10th, 2027*). 

### 2026-06-07 — Desktop GUI for Batch Video Processing

A **FreeSimpleGUI desktop client** (`GUI/CMNET2_colorize_client_GUI.py`) has been added to the project.
It orchestrates the full video colorization pipeline from a single graphical interface:

1. **Extract** reference frames via VapourSynth + scene-change detection
2. **Colorize** frames via the HAVC DiT Server (standard or paired inference)
3. **Encode** the result as H.265 (x265 or NVEnc) or H.264 (x264)
4. **Merge** the AI output with an existing color clip (optional, luminance-guided chroma blend)

![GUI Tab #2](https://github.com/dan64/HAVCServerDiT/blob/main/GUI/assets/gui_page3.jpg)

See [GUI guide](gui.md) for installation, setup, and usage instructions.

> **Prerequisite**: the HAVC DiT Server must be running before the GUI can colorize frames.
