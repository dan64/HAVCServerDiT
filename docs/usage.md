# Usage

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

# GGUF (any quantization)
python dit_rpc_server.py --load-pipeline --pipeline-config config/qwen_gguf_q3.json
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
start_server.cmd [q3|q4|q5|q6|q8|fp4|int4|longcat]
```

| Argument  | Backend  | Quantization | VRAM  |
| --------- | -------- | ------------ | ----- |
| _(none)_  | GGUF     | Q4_K_S       | 12 GB |
| `q3`      | GGUF     | Q3_K_S       | 12 GB |
| `q4`      | GGUF     | Q4_K_S       | 12 GB |
| `q5`      | GGUF     | Q5_K_M       | 16 GB |
| `q6`      | GGUF     | Q6_K         | 18 GB |
| `q8`      | GGUF     | Q8_0         | 22 GB |
| `fp4`     | Nunchaku | FP4          | 16 GB |
| `int4`    | Nunchaku | INT4         | 16 GB |
| `longcat` | LongCat  | Q4_K_M       | 12 GB |

If no argument is passed it defaults to `q4` (Q4_K_S). Use `int4` for RTX 30 / 40-Series Nunchaku:

```
start_server.cmd int4
```

**Convenience wrappers** — double-click or run from terminal without arguments:

| File                     | Equivalent command         | Backend        |
| ------------------------ | --------------------------- | -------------- |
| `run_server_q3.cmd`      | `start_server.cmd q3`      | GGUF Q3_K_S    |
| `run_server_fp4.cmd`     | `start_server.cmd fp4`     | Nunchaku FP4   |
| `run_server_int4.cmd`    | `start_server.cmd int4`    | Nunchaku INT4  |
| `run_server_longcat.cmd` | `start_server.cmd longcat` | LongCat Q4_K_M |

`run_server_qwen21.cmd` is a **separate, standalone launcher** for
`qwen21-viggle` — it does not take an argument (`start_server.cmd
qwen21-viggle` is not a thing), it always launches with
`config/qwen21_viggle.json` (the only config available for this backend).

> **GUI shortcut**: From the desktop GUI, go to Tab 2 (Colorization), pick a Model + Precision, and click **Run Server** — the GUI starts the server itself, with live output in the **Server Log** tab and auto-connect once it's ready (see [What's New, 2026-09-30](whats-new.md)). Tick **External console** first to instead open a plain terminal window with the correct `.cmd` file/arguments for the selected Model Name (`run_server_qwen21.cmd` when `qwen21-viggle` is selected, `start_server.cmd` with the right arguments otherwise).

---

## 🎯 Suggested Inference Steps

| Model Family             | Recommended Steps | Notes                                                                                  |
| ------------------------ | ----------------- | -------------------------------------------------------------------------------------- |
| Qwen (nunchaku fp4/int4) | **2**             | Good results with 2 steps when using lightning LoRA                                    |
| Qwen (gguf q3–q8)        | **2**             | Default in config files; 4 steps possible but slower                                   |
| LongCat (longcat-gguf)   | **8**             | Calibrated for 8 steps; best quality at 8 steps; 4 steps possible but colors are faded |
| Qwen-Image-2.1 (qwen21-viggle) | **6**       | LoRA's native step count. `2`/`4`/`8` are experimental alternate schedules — `2` in particular trades a little brightness accuracy for ~25% less time, worth trying |

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
