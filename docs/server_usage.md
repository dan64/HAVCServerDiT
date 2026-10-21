# Server Usage

> **Note** — In an installation created by the installer, the server is normally
> started and managed **automatically by the GUI**: the **Run Server** button
> (Tab 2) launches it, streams its output into the **Server Log** tab and
> connects the client as soon as it is ready (see the [GUI guide](gui_usage.md)).
> This page documents how to run and manage the server **manually** — for
> custom setups, a server on a different machine, or debugging.

## Start the server (no preload : pipeline loaded later via RPC)

```bash
python dit_rpc_server.py
```

## Start the server with pipeline preloaded at boot

```bash
# RTX 50-Series
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen_nunchaku_fp4.json

# RTX 30 / 40-Series
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen_nunchaku_int4.json

# Qwen-Image-Edit 2511 (native int8 ConvRot recommended; GGUF Q3_K_S for 12 GB GPUs)
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen-2511_int8.json

# FLUX.2-dev (int4 ConvRot on 16 GB; see the vram_headroom note in docs/backends.md)
python dit_rpc_server.py --load-pipeline --pipeline-config config/flux2_dev_int4.json
```

On Windows you can also use the provided `start_server.cmd` (see [Windows launch script](#-windows-launch-script)).

## Full list of CLI arguments

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

## 🪟 Windows Launch Script

`start_server.cmd` is a ready-to-use launcher for Windows.
Edit the variables at the top of the file to match your setup, then double-click it or run it from a terminal.
In installations created by the installer everything is already configured: the same launchers live in the HAVC folder (`HAVC.vbs`, `HAVC-Server.cmd`, `start_server.cmd`, `run_server_*.cmd`) and run the bundled Python — just double-click them.

```
start_server.cmd [q3|int8|fp4|int4|longcat|<config-name>]
```

| Argument  | Backend  | Model                        | VRAM  |
| --------- | -------- | ---------------------------- | ----- |
| _(none)_  | 2511     | int8 ConvRot                 | 16 GB |
| `q3`      | 2511     | Q3_K_S (GGUF)                | 12 GB |
| `int8`    | 2511     | int8 ConvRot (native)        | 16 GB |
| `fp4`     | Nunchaku | FP4                          | 16 GB |
| `int4`    | Nunchaku | INT4                         | 16 GB |
| `longcat` | LongCat  | Q4_K_M                       | 12 GB |

If no argument is passed it defaults to `int8` (Qwen-Image-Edit 2511 int8 ConvRot). Use `int4` for RTX 30 / 40-Series Nunchaku:

```
start_server.cmd int4
```

The FLUX.2-dev family has no shortcut alias (the shortcuts above are
historical); select its configs by name:

```
start_server.cmd flux2_dev_int4    # FLUX.2-dev int4 ConvRot, 16 GB (recommended)
start_server.cmd flux2_dev_fp8     # FLUX.2-dev fp8-mixed, 33 GB streamed
start_server.cmd flux2_dev_q3      # FLUX.2-dev GGUF Q3_K_M
start_server.cmd flux2_klein_9b_int8  # Flux.2 Klein 9B INT8 ConvRot (Qwen3 8B fp4 TE)
start_server.cmd flux2_klein_4b_int8  # Flux.2 Klein 4B INT8 ConvRot — the fastest model
start_server.cmd flux3_klein_6b_int8  # FLUX.3 Image Klein INT8 ConvRot + Qwen3.5-9B prompt upsampler (gated repo)
```

The Qwen-Image-Edit family on the Nunchaku node follows the same rule:

```
start_server.cmd qwen-2511-nunchaku_fp4   # 2511 QuantFunc FP4 + Lightning LoRA
start_server.cmd qwen-2509-nunchaku_fp4   # 2509 official FP4 (Lightning fused)
start_server.cmd qwen-2511-nunchaku-fast_fp4   # same, paired split (Fast Pipeline)
start_server.cmd qwen-2509-nunchaku-fast_fp4   # same, paired split (Fast Pipeline)
```

Any file in the `config/` folder can also be selected directly by its name
(a name matching a file there wins over the shortcuts above):

```
start_server.cmd longcat_gguf_q3     # same as "longcat-q3"
start_server.cmd my_new_model        # -> config/my_new_model.json
```

So adding a model = adding a config file; no script changes needed. The
same list is what the GUI shows as **Model Config** (Tab 2).

**Convenience wrappers** — double-click or run from terminal without arguments:

| File                     | Equivalent command         | Backend                        |
| ------------------------ | --------------------------- | ------------------------------ |
| `run_server_int8.cmd`    | `start_server.cmd int8`    | 2511 int8 ConvRot              |
| `run_server_q3.cmd`      | `start_server.cmd q3`      | 2511 Q3_K_S (GGUF)             |
| `run_server_fp4.cmd`     | `start_server.cmd fp4`     | Nunchaku FP4                   |
| `run_server_int4.cmd`    | `start_server.cmd int4`    | Nunchaku INT4                  |
| `run_server_longcat.cmd` | `start_server.cmd longcat` | LongCat Q4_K_M                 |
| `run_server_qwen2511n.cmd` | `start_server.cmd qwen-2511-nunchaku_fp4` | Qwen-Image-Edit 2511, Nunchaku node |
| `run_server_qwen2509n.cmd` | `start_server.cmd qwen-2509-nunchaku_fp4` | Qwen-Image-Edit 2509, Nunchaku node |

`run_server_qwen21.cmd` is a **standalone launcher** for the shipped default
(`qwen21_viggle-soft_int8`) — it does not take an argument and always launches
with `config/qwen21_viggle-soft_int8.json` (the same config as
`HAVC-Server.cmd qwen21`). Other configs are one command away, by name:
`start_server.cmd qwen21_viggle-soft_q4`, `start_server.cmd qwen21_turbo_int8`, …

`HAVC-Server.cmd` (the installer's console launcher) accepts the same kind
of argument: `HAVC-Server.cmd qwen21` starts the shipped default config
(`qwen21_viggle-soft_int8.json`), any config name works as well, and with no
argument it starts `int4`.

> **GUI shortcut**: From the desktop GUI, go to Tab 2 (Colorization), pick a **Model Config**, and click **Run Server** — the GUI starts the server itself, with live output in the **Server Log** tab and auto-connect once it's ready (see [What's New, 2026-10-02](whats-new.md)). Tick **External console** first to instead open a plain terminal window running `start_server.cmd <config-name>` for the selected config.

---

## 🎯 Suggested Inference Steps

| Model Family             | Recommended Steps | Notes                                                                                  |
| ------------------------ | ----------------- | -------------------------------------------------------------------------------------- |
| Qwen (nunchaku fp4/int4) | **2**             | Good results with 2 steps when using lightning LoRA                                    |
| Qwen-Image-Edit 2511     | **2**             | `qwen-2511_int8` / `qwen-2511_q3` — GUI default (fastest); the config files ship `steps: 4`, the LoRA's distilled step count |
| LongCat (longcat-gguf)   | **8**             | Calibrated for 8 steps; best quality at 8 steps; 4 steps possible but colors are faded |
| Qwen-Image-2.1 (qwen21-viggle) | **6**       | LoRA step schedules: `2`/`4`/`6`/`8` — `6` (the LoRA's native step count) gives the most accurate colors, `2` is the fastest |
| Qwen-Image-2.1-Turbo (qwen21-turbo) | **8**  | Fixed by the checkpoint's own sigma table (its `sample_sigmas`); the GUI steps setting does not apply. `config/qwen21_turbo_int8.json` sets `fast_split_TE` — Fast Pipeline pairs consecutive frames |
| FLUX.2-dev (flux2)       | **2**             | The Flux.2 Turbo LoRA's distilled step count (all four configs ship `steps: 2`); the panel's setting applies. Paired split on by default, `guidance` 4.0 |
| Flux.2 Klein (flux2)     | **4**             | `flux2_klein_9b_int8` / `_4b_int8` — Klein's own distilled schedule (the configs ship `steps: 4`); no LoRA, no FluxGuidance (`guidance: 0`), Qwen3 text encoder. The 4B is the fastest config in the stack (author's field test, 2026-10-20) |
| FLUX.3 Image Klein (flux3) | **4-8**         | `flux3_klein_6b_int8` — the config ships `steps: 8` and the panel's setting applies (the reference workflow uses 16); **4-6 steps are field-verified** and cost little: in the paired split the transformer is only 1.4 s of the 7.2 s pair, the rest is the upsampler. No LoRA, no guidance node, constant timestep shift. The **Qwen3.5-9B upsampler** rewrites your prompt once per image (once per pair canvas) from the frame itself |
| Qwen-Image-Edit, Nunchaku node (qwen25-nunchaku) | **4** | `qwen-2511-nunchaku_fp4` / `qwen-2509-nunchaku_fp4` — the Lightning distilled step count (2509 fused, 2511 via LoRA); the config files ship `steps: 4` |

> **Prompt tip (qwen21-viggle)**: on subjects with a strong color convention
> (e.g. a well-known costume), the model can leave the color ambiguous and
> resolve it inconsistently between runs. Before reaching for
> `enhance_prompt` (which adds ~15-20s/frame), try a direct,
> explicitly anti-hedging prompt — it solves the same problem for free in
> most cases:
> > "Add color to this black-and-white image without hesitation regarding
> > the appropriate colors. For any subject, garment, object, or setting
> > where the color is common knowledge or established by convention,
> > confidently apply the expected color; otherwise use natural colors.
> > Color the image by strictly preserving all shapes, outlines, and
> > background details."
>
> Avoid naming specific example subjects in this prompt (e.g. "like a stop
> sign") — the model may render that literal example into the scene instead
> of just using it as a color reference.
>
> **Prompt tip (qwen21-turbo)**: same rule as qwen21-viggle — it wants a
> detailed, explicit prompt (the shipped default fits it well). Keep the
> short-and-direct style for qwen-2511 only.
>
> **Prompt tip (qwen-2511)**: keep it short and direct — the opposite of the
> detail-heavy wording `qwen21-viggle` likes. A good default: *"Colorize
> this image, natural colors. Strictly preserve all shapes, edges and
> background details."* — the wording every Qwen-Image-Edit and FLUX.2 config
> ships, and the GUI's protected preset #1, so Tab 2's **Enable Prompt
> Config** sends it as-is. Longer or more emphatic prompts
> can steer it the wrong way (a "vibrant colors" variant colored some
> subjects noticeably wrong in a side-by-side test), so start simple and only
> add words when the output calls for it. The sensitivity is per-wording and
> not monotonic:
> some very terse prompts (*"Color this image, natural colors."*) can make
> it duplicate the subject on portrait frames — see
> [Troubleshooting](troubleshooting.md). In the 2026-10 side-by-side test, a
> wording that stayed clean on such frames: *"Colorize this image, natural
> skin tones, vibrant environment. Maintain consistency and details."*
