"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2026-01-14
-------------------------------------------------------------------------------
HAVC DiT Client  :  example
Connects to a running dit_rpc_server instance and colorizes the sample image
assets/santa_bw.png, saving the result as assets/santa_colorized.png.

The pipeline must already be loaded on the server (start the server with
--load-pipeline --pipeline-config CONFIG.json).

Usage:
    python dit_client_example.py [--host HOST] [--port PORT]
                                 [--prompt "..."]
                                 [--use-shm]
-------------------------------------------------------------------------------
"""

import argparse
import io
import sys
import time
import uuid
import xmlrpc.client
from pathlib import Path

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers  :  standard RPC (PNG bytes over XML-RPC)
# ---------------------------------------------------------------------------

def _pil_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bytes_to_pil(data) -> Image.Image:
    raw = data.data if hasattr(data, "data") else data
    return Image.open(io.BytesIO(raw)).convert("RGB")


# ---------------------------------------------------------------------------
# Helpers  :  shared memory transport (same-host only)
# ---------------------------------------------------------------------------

def _colorize_shm(proxy, img: Image.Image, prompt: str,
                  img_size: int, steps: int) -> dict:
    """
    Colorize a single frame via shared memory.
    Returns the same dict as colorize_frame() plus an 'image' key
    with the result PIL Image.
    """
    from multiprocessing.shared_memory import SharedMemory

    arr  = np.array(img)
    h, w = arr.shape[:2]
    uid      = uuid.uuid4().hex[:12]
    name_in  = f"dit_in_{uid}"
    name_out = f"dit_out_{uid}"

    shm_in  = SharedMemory(name=name_in,  create=True, size=h * w * 3)
    shm_out = SharedMemory(name=name_out, create=True, size=h * w * 3)
    try:
        np.ndarray((h, w, 3), dtype=np.uint8, buffer=shm_in.buf)[:] = arr
        result = proxy.colorize_frame_shm(
            name_in, name_out, h, w, prompt, img_size, steps)
        if result["ok"]:
            out_arr = np.ndarray((h, w, 3), dtype=np.uint8, buffer=shm_out.buf)
            result["image"] = Image.fromarray(out_arr.copy(), mode="RGB")
        else:
            result["image"] = img
        return result
    finally:
        shm_in.close();  shm_in.unlink()
        shm_out.close(); shm_out.unlink()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DiT Colorize RPC Client  :  example",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--prompt",
                        default="Colorize this photo, natural skin tones, "
                                "vibrant environment. Maintain consistency and details.")
    parser.add_argument("--img-size", type=int, default=0)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--use-shm", action="store_true",
                        help="Use shared memory transport (same-host only, lower latency)")
    args = parser.parse_args()

    script_dir  = Path(__file__).parent.resolve()
    input_path  = script_dir / "assets" / "santa_bw.png"
    output_path = script_dir / "assets" / "santa_colorized.png"

    if not input_path.exists():
        print(f"[ERROR] Input image not found: {input_path}")
        sys.exit(1)

    server_url = f"http://{args.host}:{args.port}/"
    print(f"[INFO] Connecting to {server_url} ...")
    proxy = xmlrpc.client.ServerProxy(server_url, use_builtin_types=True)

    try:
        proxy.ping()
    except ConnectionRefusedError:
        print(f"[ERROR] Could not reach the server at {server_url}.")
        sys.exit(1)

    print("[INFO] Server is reachable.")

    use_shm = args.use_shm
    if use_shm and args.host not in ("127.0.0.1", "localhost", "::1"):
        print("[WARN] --use-shm requires same-host server. Falling back to standard RPC.")
        use_shm = False
    print(f"[INFO] Transport: {'shared memory' if use_shm else 'standard RPC (PNG)'}")

    if not proxy.is_pipeline_loaded():
        print("[ERROR] Pipeline not loaded on server. "
              "Start the server with --load-pipeline --pipeline-config CONFIG.json.")
        sys.exit(1)
    print("[INFO] Pipeline is loaded on server.")

    print(f"[INFO] Reading input image: {input_path}")
    img_in = Image.open(input_path).convert("RGB")
    print(f"[INFO] Colorizing ({img_in.width}x{img_in.height} px) ...")

    t0 = time.perf_counter()
    if use_shm:
        result  = _colorize_shm(proxy, img_in, args.prompt, args.img_size, args.steps)
        img_out = result["image"]
    else:
        result  = proxy.colorize_frame(
            _pil_to_bytes(img_in), args.prompt, args.img_size, args.steps)
        img_out = _bytes_to_pil(result["data"])
    wall_time = time.perf_counter() - t0

    if not result["ok"]:
        print(f"[ERROR] colorize_frame failed: {result['msg']}")
        sys.exit(1)

    if result["skipped"]:
        print("[WARN] Image was too dark  :  output is unchanged.")
    else:
        print(f"[INFO] Inference time : {result['elapsed']:.2f}s")
        print(f"[INFO] Round-trip time: {wall_time:.2f}s")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img_out.save(output_path)
    print(f"[INFO] Saved: {output_path}")


if __name__ == "__main__":
    main()
