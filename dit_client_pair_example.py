"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2026-05-10
-------------------------------------------------------------------------------
DiT Colorize RPC Client — paired inference example
Connects to a running dit_rpc_server instance and colorizes two B&W frames
in a single inference pass using colorize_frame_pair().

Input  : assets/sample1_bw.jpg  +  assets/sample2_bw.jpg
Output : assets/sample1_colorized.jpg  +  assets/sample2_colorized.jpg

Paired inference processes two images side-by-side in one forward pass,
roughly halving the per-image cost (~4.5s/image vs ~11s/image standalone).

Usage:
    python dit_client_pair_example.py [--host HOST] [--port PORT]
                                      [--pipeline-config CONFIG.json]
                                      [--prompt "..."]
                                      [--gap-px N]
-------------------------------------------------------------------------------
"""

import argparse
import io
import json
import sys
import time
import xmlrpc.client
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Helpers — same convention as the server
# ---------------------------------------------------------------------------

def _pil_to_bytes(img: Image.Image) -> bytes:
    """Serialize a PIL Image to raw PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bytes_to_pil(data) -> Image.Image:
    """Deserialize raw PNG bytes (or xmlrpc.client.Binary) into a PIL Image."""
    raw = data.data if hasattr(data, "data") else data
    return Image.open(io.BytesIO(raw)).convert("RGB")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DiT Colorize RPC Client — paired inference example",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Server host")
    parser.add_argument("--port", type=int, default=8765,
                        help="Server port")
    parser.add_argument("--pipeline-config", default="",
                        metavar="CONFIG.json",
                        help="Path to a JSON pipeline config file. "
                             "When provided the client calls load_pipeline() "
                             "before colorizing; omit if the server already "
                             "has the pipeline loaded.")
    parser.add_argument("--prompt",
                        default="Colorize this photo, natural skin tones, "
                                "vibrant environment. Maintain consistency "
                                "and details.",
                        help="Text prompt sent to the colorization model")
    parser.add_argument("--gap-px", type=int, default=8,
                        help="Neutral separator width (pixels) between the "
                             "two images in the merged input")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------
    server_url = f"http://{args.host}:{args.port}/"
    print(f"[INFO] Connecting to {server_url} ...")
    proxy = xmlrpc.client.ServerProxy(server_url, use_builtin_types=True)

    try:
        response = proxy.ping()
    except ConnectionRefusedError:
        print(f"[ERROR] Could not reach the server at {server_url}.")
        print("        Make sure dit_rpc_server.py is running.")
        sys.exit(1)

    if response != "pong":
        print(f"[ERROR] Unexpected ping response: {response!r}")
        sys.exit(1)

    print("[INFO] Server is reachable.")

    # ------------------------------------------------------------------
    # Optional: load pipeline from config file
    # ------------------------------------------------------------------
    if args.pipeline_config:
        config_path = Path(args.pipeline_config)
        if not config_path.is_file():
            print(f"[ERROR] Config file not found: {config_path}")
            sys.exit(1)

        with config_path.open(encoding="utf-8") as fh:
            cfg = json.load(fh)

        print(f"[INFO] Loading pipeline from: {config_path.name} ...")
        result = proxy.load_pipeline(
            cfg["model_name"],
            cfg["model_precision"],
            cfg["model_rank"],
            cfg["model_inference_steps"],
            cfg.get("cache_dir", ""),
            cfg.get("full_model_path", ""),
        )
        if not result["ok"]:
            print(f"[ERROR] load_pipeline failed: {result['msg']}")
            sys.exit(1)
        print("[INFO] Pipeline loaded successfully.")

    elif not proxy.is_pipeline_loaded():
        print("[ERROR] The pipeline is not loaded on the server.")
        print("        Either pass --pipeline-config or start the server")
        print("        with --load-pipeline --pipeline-config CONFIG.json.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Read both input images
    # ------------------------------------------------------------------
    img1 = Image.open(input1).convert("RGB")
    img2 = Image.open(input2).convert("RGB")

    print(f"[INFO] Image 1: {input1.name}  ({img1.width}x{img1.height} px)")
    print(f"[INFO] Image 2: {input2.name}  ({img2.width}x{img2.height} px)")
    print(f"[INFO] Running paired inference (gap={args.gap_px}px) ...")

    # ------------------------------------------------------------------
    # Paired colorization
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    result = proxy.colorize_frame_pair(
        _pil_to_bytes(img1),
        _pil_to_bytes(img2),
        args.prompt,
        args.gap_px,
    )
    wall_time = time.perf_counter() - t0

    if not result["ok"]:
        print(f"[ERROR] colorize_frame_pair failed: {result['msg']}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Report timing
    # ------------------------------------------------------------------
    elapsed   = result["elapsed"]
    skipped1  = result["skipped1"]
    skipped2  = result["skipped2"]

    print(f"[INFO] Inference time : {elapsed:.2f}s total  "
          f"({elapsed / 2:.2f}s per image)")
    print(f"[INFO] Round-trip time: {wall_time:.2f}s")

    if skipped1:
        print(f"[WARN] Image 1 was too dark — output is unchanged.")
    if skipped2:
        print(f"[WARN] Image 2 was too dark — output is unchanged.")

    # ------------------------------------------------------------------
    # Save results
    # ------------------------------------------------------------------
    assets_dir.mkdir(parents=True, exist_ok=True)

    out1 = _bytes_to_pil(result["data1"])
    out2 = _bytes_to_pil(result["data2"])

    out1.save(output1, quality=95)
    out2.save(output2, quality=95)

    print(f"[INFO] Saved: {output1.name}")
    print(f"[INFO] Saved: {output2.name}")


if __name__ == "__main__":
    main()
