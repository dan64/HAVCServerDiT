"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2026-05-10
-------------------------------------------------------------------------------
DiT Colorize RPC Client — paired inference example
Connects to a running dit_rpc_server instance and colorizes two B&W frames
in a single inference pass using colorize_frame_pair() or
colorize_frame_pair_shm() (with --use-shm).

Input  : assets/sample1_bw.jpg  +  assets/sample2_bw.jpg
Output : assets/sample1_colorized.jpg  +  assets/sample2_colorized.jpg

Usage:
    python dit_client_pair_example.py [--host HOST] [--port PORT]
                                      [--pipeline-config CONFIG.json]
                                      [--prompt "..."]
                                      [--gap-px N]
                                      [--use-shm]
-------------------------------------------------------------------------------
"""

import argparse
import io
import json
import sys
import time
import uuid
import xmlrpc.client
from pathlib import Path

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers — standard RPC
# ---------------------------------------------------------------------------

def _pil_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bytes_to_pil(data) -> Image.Image:
    raw = data.data if hasattr(data, "data") else data
    return Image.open(io.BytesIO(raw)).convert("RGB")


# ---------------------------------------------------------------------------
# Helpers — shared memory transport (same-host only)
# ---------------------------------------------------------------------------

def _colorize_pair_shm(proxy, img1: Image.Image, img2: Image.Image,
                        prompt: str, gap_px: int) -> dict:
    """
    Colorize two frames via shared memory in a single inference pass.
    Returns the same dict as colorize_frame_pair() plus 'image1' and 'image2'
    keys containing the result PIL Images.
    """
    from multiprocessing.shared_memory import SharedMemory

    arr1 = np.array(img1); h1, w1 = arr1.shape[:2]
    arr2 = np.array(img2); h2, w2 = arr2.shape[:2]
    uid = uuid.uuid4().hex[:12]

    segs = {}
    for tag, h, w in [("in1", h1, w1), ("out1", h1, w1),
                       ("in2", h2, w2), ("out2", h2, w2)]:
        segs[tag] = SharedMemory(name=f"dit_{tag}_{uid}",
                                  create=True, size=h * w * 3)
    try:
        np.ndarray((h1, w1, 3), dtype=np.uint8,
                   buffer=segs["in1"].buf)[:] = arr1
        np.ndarray((h2, w2, 3), dtype=np.uint8,
                   buffer=segs["in2"].buf)[:] = arr2

        result = proxy.colorize_frame_pair_shm(
            segs["in1"].name,  segs["out1"].name, h1, w1,
            segs["in2"].name,  segs["out2"].name, h2, w2,
            prompt, gap_px,
        )

        if result["ok"]:
            out1 = np.ndarray((h1, w1, 3), dtype=np.uint8,
                               buffer=segs["out1"].buf)
            out2 = np.ndarray((h2, w2, 3), dtype=np.uint8,
                               buffer=segs["out2"].buf)
            result["image1"] = Image.fromarray(out1.copy(), mode="RGB")
            result["image2"] = Image.fromarray(out2.copy(), mode="RGB")
        else:
            result["image1"] = img1
            result["image2"] = img2
        return result
    finally:
        for shm in segs.values():
            shm.close(); shm.unlink()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DiT Colorize RPC Client — paired inference example",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--pipeline-config", default="", metavar="CONFIG.json")
    parser.add_argument("--prompt",
                        default="Colorize this photo, natural skin tones, "
                                "vibrant environment. Maintain consistency and details.")
    parser.add_argument("--gap-px", type=int, default=8)
    parser.add_argument("--use-shm", action="store_true",
                        help="Use shared memory transport (same-host only, lower latency)")
    args = parser.parse_args()

    script_dir = Path(__file__).parent.resolve()
    assets_dir = script_dir / "assets"
    input1  = assets_dir / "sample1_bw.jpg"
    input2  = assets_dir / "sample2_bw.jpg"
    output1 = assets_dir / "sample1_colorized.jpg"
    output2 = assets_dir / "sample2_colorized.jpg"

    for p in (input1, input2):
        if not p.exists():
            print(f"[ERROR] Input image not found: {p}")
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

    if args.pipeline_config:
        config_path = Path(args.pipeline_config)
        if not config_path.is_file():
            print(f"[ERROR] Config file not found: {config_path}")
            sys.exit(1)
        with config_path.open(encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not proxy.is_pipeline_loaded():
            print(f"[INFO] Loading pipeline from: {config_path.name} ...")
            result = proxy.load_pipeline(
                cfg["model_name"], cfg["model_precision"], cfg["model_rank"],
                cfg["model_inference_steps"],
                cfg.get("cache_dir", ""), cfg.get("full_model_path", ""),
            )
            if not result["ok"]:
                print(f"[ERROR] load_pipeline failed: {result['msg']}")
                sys.exit(1)
            print("[INFO] Pipeline loaded successfully.")
        else:
            print("[INFO] Pipeline already loaded on server.")
    elif not proxy.is_pipeline_loaded():
        print("[ERROR] Pipeline not loaded. Pass --pipeline-config or start "
              "server with --load-pipeline.")
        sys.exit(1)

    img1 = Image.open(input1).convert("RGB")
    img2 = Image.open(input2).convert("RGB")
    print(f"[INFO] Image 1: {input1.name}  ({img1.width}x{img1.height} px)")
    print(f"[INFO] Image 2: {input2.name}  ({img2.width}x{img2.height} px)")
    print(f"[INFO] Running paired inference (gap={args.gap_px}px) ...")

    t0 = time.perf_counter()
    if use_shm:
        result = _colorize_pair_shm(proxy, img1, img2, args.prompt, args.gap_px)
        out1, out2 = result["image1"], result["image2"]
    else:
        result = proxy.colorize_frame_pair(
            _pil_to_bytes(img1), _pil_to_bytes(img2), args.prompt, args.gap_px)
        out1 = _bytes_to_pil(result["data1"])
        out2 = _bytes_to_pil(result["data2"])
    wall_time = time.perf_counter() - t0

    if not result["ok"]:
        print(f"[ERROR] colorize_frame_pair failed: {result['msg']}")
        sys.exit(1)

    elapsed = result["elapsed"]
    print(f"[INFO] Inference time : {elapsed:.2f}s total  ({elapsed/2:.2f}s per image)")
    print(f"[INFO] Round-trip time: {wall_time:.2f}s")

    if result["skipped1"]: print("[WARN] Image 1 was too dark — output is unchanged.")
    if result["skipped2"]: print("[WARN] Image 2 was too dark — output is unchanged.")

    assets_dir.mkdir(parents=True, exist_ok=True)
    out1.save(output1, quality=95)
    out2.save(output2, quality=95)
    print(f"[INFO] Saved: {output1.name}")
    print(f"[INFO] Saved: {output2.name}")


if __name__ == "__main__":
    main()

