# RPC API reference

Connect from any Python client using `xmlrpc.client`:

```python
import xmlrpc.client
proxy = xmlrpc.client.ServerProxy("http://127.0.0.1:8765/", use_builtin_types=True)
```

All methods return a `dict` with at least `{"ok": bool, "msg": str}`.

### Health

| Method   | Returns  | Description        |
| -------- | -------- | ------------------ |
| `ping()` | `"pong"` | Connectivity check |

### Pipeline management

| Method                                                                                                                                                              | Returns         | Description                   |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- | ------------------------------ |
| `load_pipeline(model_name, model_precision, model_rank, model_inference_steps, cache_dir="", full_model_path="", vae_name="", hf_unet="", hf_clip="", hf_vae="", hf_lora="", clip_mmproj="", clip_mmproj_hf_name="", unet_hf_name="")` | `{"ok", "msg"}` | Load the model into VRAM. The `vae_name`/`hf_*` arguments are only meaningful for `gguf-qwen`/`longcat-gguf`/`qwen21-viggle` — omit for `nunchaku-qwen`. `clip_mmproj`/`clip_mmproj_hf_name`/`unet_hf_name` are the remote-filename overrides used by `qwen21-viggle` auto-download |
| `load_pipeline_from_config(config_name, cache_dir="")`                                                                                                            | `{"ok", "msg"}` | Load the pipeline from `config/<config_name>.json` on the server (file name with or without the `.json` extension; path separators are not accepted). The `config/` folder is the source of truth for the supported models — adding a config file there makes a new model available |
| `is_pipeline_loaded()`                                                                                                                                            | `bool`          | True if the pipeline is ready |
| `unload_pipeline()`                                                                                                                                                | `{"ok", "msg"}` | Release VRAM                  |

### Stop control

| Method                | Returns | Description                                     |
| --------------------- | ------- | ----------------------------------------------- |
| `request_stop()`      | `bool`  | Ask the server to refuse new colorization calls |
| `clear_stop()`        | `bool`  | Reset the stop flag before a new batch          |
| `is_stop_requested()` | `bool`  | Check the current stop flag                     |

### Colorization : filesystem-based

| Method                                                                                                | Returns                               | Description                                  |
| ------------------------------------------------------------------------------------------------------- | -------------------------------------- | -------------------------------------------- |
| `colorize_image(in_path, out_path, prompt, img_size=0, steps=2, enhance_prompt=False)`                | `{"ok", "elapsed", "skipped", "msg"}` | Single image, paths on the server filesystem |
| `colorize_image_pair(img1_path, img2_path, out_dir, prompt, gap_px=8, steps=2, enhance_prompt=False)` | `{"ok", "elapsed", "msg"}`            | Two images, single inference pass            |
| `colorize_single_image(img_path, out_dir, prompt, steps=2, enhance_prompt=False)`                     | `{"ok", "elapsed", "msg"}`            | Single image fallback (odd batch end)        |

### Colorization : in-memory (PNG bytes over RPC)

| Method                                                                                    | Returns                                                              | Description                       |
| -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------- |
| `colorize_frame(img_data, prompt, img_size=0, steps=2, seed=42, skip_bw=False, enhance_prompt=False)`                | `{"ok", "data", "elapsed", "skipped", "msg"}`                        | Single frame as raw PNG bytes     |
| `colorize_frame_pair(img1_data, img2_data, prompt, gap_px=8, steps=2, enhance_prompt=False)` | `{"ok", "data1", "data2", "elapsed", "skipped1", "skipped2", "msg"}` | Two frames, single inference pass |

> `skipped=True` means the frame was too dark to colorize (average brightness < 9/255).
> The returned `data` field contains the unchanged input in that case.

### Colorization : shared memory (same-host only, zero-copy)

| Method                                                                                                                         | Returns                                            | Description                                         |
| ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------- |
| `colorize_frame_shm(shm_in, shm_out, h, w, prompt, img_size=0, steps=2, seed=42, skip_bw=False, enhance_prompt=False)`             | `{"ok", "elapsed", "skipped", "msg"}`              | Single frame via shared memory                      |
| `colorize_frame_pair_shm(shm_in1, shm_out1, h1, w1, shm_in2, shm_out2, h2, w2, prompt, gap_px=8, steps=4, enhance_prompt=False)`    | `{"ok", "elapsed", "skipped1", "skipped2", "msg"}` | Two frames via shared memory, single inference pass |

> `enhance_prompt` (all methods above, default `False`) rewrites the prompt
> via Qwen3-VL before colorizing — only meaningful for `qwen21-viggle`;
> silently has no effect on the other backends. See [What's New](whats-new.md).
> See [Shared Memory Transport](#-shared-memory-transport-same-host-only) for usage details.

---

## 🧪 Example Clients

Both clients support two transport modes selectable via `--use-shm`:

| Mode          | Flag        | When to use                                 | Measured speed (1480×1080 px pair) |
| ------------- | ----------- | ------------------------------------------- | ---------------------------------- |
| Standard RPC  | _(default)_ | Any deployment, including remote server     | ~5.25s/image                       |
| Shared memory | `--use-shm` | Server and client on the **same host** only | ~4.06s/image (**~23% faster**)     |

> The pipeline must be loaded on the server before running the clients.
> Start the server with `--load-pipeline --pipeline-config CONFIG.json`.

### Single frame : `dit_client_example.py`

Colorizes `assets/santa_bw.png` and saves the result as `assets/santa_colorized.png`.

```bash
# standard RPC : works with local and remote server
python dit_client_example.py

# shared memory : same-host only, lower latency
python dit_client_example.py --use-shm
```

Windows: `run_client_example.cmd`
To enable shared memory edit `run_client_example.cmd` and set `USE_SHM=1`.

---

### Paired inference : `dit_client_pair_example.py`

Colorizes `assets/sample1_bw.jpg` and `assets/sample2_bw.jpg` in a **single forward
pass**, saving `assets/sample1_colorized.jpg` and `assets/sample2_colorized.jpg`.

Paired inference places the two images side-by-side and runs one inference instead of
two, roughly halving the per-image cost (~5.25s/image vs ~11s standalone).
Combined with shared memory transport this reaches ~4.06s/image.

```bash
# standard RPC
python dit_client_pair_example.py

# shared memory : same-host only
python dit_client_pair_example.py --use-shm
```

Windows: `run_client_pair_example.cmd`
To enable shared memory edit `run_client_pair_example.cmd` and set `USE_SHM=1`.

### Full list of arguments (both clients)

```
  --host HOST                  Server host (default: 127.0.0.1)
  --port PORT                  Server port (default: 8765)
  --prompt PROMPT              Text prompt for the model
  --steps N                    Number of steps for inference (default:4)
  --use-shm                    Use shared memory transport (same-host only)
```

Additional argument for the paired client:

```
  --gap-px N                   Separator width in pixels between the two
                               images in the merged input (default: 8)
```

---

## 🚀 Shared Memory Transport (same-host only)

### What it is

The standard RPC transport serializes each image as a PNG byte stream, encodes it in
Base64, sends it over a TCP socket, and decodes it on the other side. For a 1480×1080
frame this is roughly 4–5 MB per round trip.

The shared memory transport bypasses the network entirely. The client writes the raw
pixel array directly into a shared memory segment; the server attaches to the same
segment and reads the pixels without any copy. Only the metadata (segment name,
dimensions, prompt) travels over the XML-RPC socket.

### When you can use it

**Requirement: server and client must run on the same machine.**

If the server is on a dedicated GPU machine and the client is on a separate workstation,
shared memory is not available : use the standard RPC transport instead (default).
The clients detect this automatically: passing `--use-shm` when the host is not
`127.0.0.1` / `localhost` prints a warning and falls back to standard RPC.

### Performance

Measured on a 1480×1080 pixel pair (RTX 5070 Ti, FP4, paired inference):

| Transport          | Per-image time  | Round-trip overhead   |
| ------------------ | --------------- | --------------------- |
| Standard RPC (PNG) | ~5.25s          | ~1.1s                 |
| Shared memory      | ~4.06s          | ~0.16s                |
| **Gain**           | **~23% faster** | **~7× less overhead** |

The round-trip overhead with shared memory is essentially zero : the 0.16s gap between
inference time and wall-clock time is just Python function call and numpy overhead.

On a 100k-frame video processed as pairs (50k inference calls) the cumulative saving is:

```
(5.25 - 4.06) × 50,000 ≈ 16.5 hours
```

### How the protocol works

The **client** owns and manages all shared memory segments. The server is fully
stateless with respect to shared memory : it only attaches, reads/writes, and detaches.

```
Client                                     Server
  │                                           │
  │  create shm_in  (h × w × 3 bytes)         │
  │  create shm_out (h × w × 3 bytes)         │
  │  write raw RGB pixels → shm_in            │
  │                                           │
  │  RPC(shm_in_name, shm_out_name, h, w, …) ─►│
  │                                           │  attach shm_in  → PIL Image
  │                                           │  inference
  │                                           │  result → shm_out
  │◄─ return {elapsed, skipped, …} ───────────│
  │                                           │  detach both segments
  │  read shm_out → PIL Image                 │
  │  unlink shm_in + shm_out                  │
```

### Enabling shared memory

**From the command line:**

```bash
python dit_client_pair_example.py --use-shm
python dit_client_example.py      --use-shm
```

**From the Windows `.cmd` launchers**, edit the user configuration block and set:

```batch
set USE_SHM=1
```

The banner will confirm the active transport:

```
Transport   : 1 (0=RPC 1=shared memory)
```

And the Python client will print:

```
[INFO] Transport: shared memory
```

### Implementing shared memory in your own client

```python
import uuid
import numpy as np
from multiprocessing.shared_memory import SharedMemory
from PIL import Image

def colorize_pair_shm(proxy, img1: Image.Image, img2: Image.Image, prompt: str):
    arr1, arr2 = np.array(img1), np.array(img2)
    h1, w1 = arr1.shape[:2]
    h2, w2 = arr2.shape[:2]
    uid = uuid.uuid4().hex[:12]

    # Create all four segments (client owns them)
    segs = {
        tag: SharedMemory(name=f"dit_{tag}_{uid}", create=True, size=h*w*3)
        for tag, h, w in [("in1",h1,w1),("out1",h1,w1),("in2",h2,w2),("out2",h2,w2)]
    }
    try:
        np.ndarray((h1,w1,3), dtype=np.uint8, buffer=segs["in1"].buf)[:] = arr1
        np.ndarray((h2,w2,3), dtype=np.uint8, buffer=segs["in2"].buf)[:] = arr2

        result = proxy.colorize_frame_pair_shm(
            segs["in1"].name, segs["out1"].name, h1, w1,
            segs["in2"].name, segs["out2"].name, h2, w2,
            prompt, 8,  # gap_px
        )

        out1 = Image.fromarray(
            np.ndarray((h1,w1,3), dtype=np.uint8, buffer=segs["out1"].buf).copy())
        out2 = Image.fromarray(
            np.ndarray((h2,w2,3), dtype=np.uint8, buffer=segs["out2"].buf).copy())
        return result, out1, out2
    finally:
        for shm in segs.values():
            shm.close(); shm.unlink()
```
