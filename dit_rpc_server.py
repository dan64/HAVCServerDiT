"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2024-12-26
LastEditTime: 2026-01-14
-------------------------------------------------------------------------------
HAVC Colorize RPC Server
Exposes the colorization pipeline via XML-RPC.

Start on the GPU machine:
    python dit_rpc_server.py [--host HOST] [--port PORT]
                             [--load-pipeline --pipeline-config CONFIG.json]

Default: localhost:8765

Pipeline config file (JSON) — required only with --load-pipeline:
{
    "model_name":            "...",
    "model_precision":       "...",
    "model_rank":            "...",
    "model_inference_steps": "...",
    "cache_dir":             "...",
    "full_model_path":       ""       // optional, may be omitted
}
-------------------------------------------------------------------------------
"""

import argparse
import io
import json
import os
import sys
import time
import threading
import logging
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from socketserver import ThreadingMixIn
from PIL import Image, ImageEnhance, ImageOps

# Add the script directory to sys.path so that dit_colorize_main.py is
# discoverable regardless of how the process is launched (pythonw.exe, start, …).
_script_dir = str(Path(__file__).parent.resolve())
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# ---------------------------------------------------------------------------
# Import the colorization module — same pattern as the original GUI:
# sys.path is already updated above, so dit_colorize_main.py will be found
# if it lives in the same directory.  The try/except lets the server start
# even when the module is missing (every RPC method will return an error).
# ---------------------------------------------------------------------------
try:
    from dit_colorize_main import (
        load_nunchaku_pipeline,
        process_image,
        process_image_pair,
        process_single_image,
        is_image_dark,
        resize_long_side,
        colorize_image    as _colorize_image,
        upscale_with_lanczos,
        merge_two_images_with_gap,
        split_merged_output,
    )
    _DIT_MAIN_AVAILABLE = True
except ImportError as _e:
    load_nunchaku_pipeline    = None
    process_image             = None
    process_image_pair        = None
    process_single_image      = None
    is_image_dark             = None
    resize_long_side          = None
    _colorize_image           = None
    upscale_with_lanczos      = None
    merge_two_images_with_gap = None
    split_merged_output       = None
    _DIT_MAIN_AVAILABLE       = False
    import warnings
    warnings.warn(
        f"dit_colorize_main not found ({_e}). "
        "All colorization methods will return an error."
    )


# ---------------------------------------------------------------------------
# Image conversion helpers
#
# Same convention as colormnet2_client.py / colormnet2_utils.py:
#   PIL Image  →  bytes (PNG lossless)  →  xmlrpc.client.Binary (base64)
#
# PNG is preferred over JPEG because:
#   - lossless: avoids artefacts on the B&W luminance channel used as input
#   - faithful round-trip: the server receives exactly the pixels that were sent
# Decompression happens entirely in RAM without touching the filesystem.
# ---------------------------------------------------------------------------

def _pil_to_bytes(img) -> bytes:
    """Serialize a PIL Image to raw PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bytes_to_pil(data: bytes):
    """Deserialize raw PNG bytes into a PIL Image (RGB)."""
    # With use_builtin_types=True xmlrpc delivers plain bytes;
    # without it, xmlrpc.client.Binary arrives and .data extracts the bytes.
    raw = data.data if hasattr(data, "data") else data
    return Image.open(io.BytesIO(raw)).convert("RGB")


# ---------------------------------------------------------------------------
# Multi-threaded server: every RPC call is served in a dedicated thread.
# daemon_threads=True ensures the process exits even if threads are still
# alive at shutdown time.
# ---------------------------------------------------------------------------
class ColorizeRequestHandler(SimpleXMLRPCRequestHandler):
    """
    HTTP/1.1 request handler with keep-alive support.

    SimpleXMLRPCRequestHandler inherits from BaseHTTPRequestHandler which
    defaults to HTTP/1.0 (connection-per-request). With HTTP/1.1 the TCP
    connection is reused across calls, preventing ephemeral port exhaustion
    on long video sequences (100k+ frames → 100k+ RPC calls).
    """
    protocol_version = "HTTP/1.1"


class ThreadedXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    daemon_threads = True


# ---------------------------------------------------------------------------
# RPC service — all public methods (no leading underscore) are exposed
# ---------------------------------------------------------------------------
class ColorizeService:
    """
    RPC interface exposed to the GUI client.

    Return convention:
        Every method returns a dict containing at least:
            {"ok": bool, "msg": str}
        Colorization methods also include:
            {"elapsed": float, "skipped": bool}
    """

    def __init__(self):
        self._pipeline = None
        self._pipeline_lock = threading.Lock()   # guards pipeline loading
        self._stop_event = threading.Event()     # signals stop to the client

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def ping(self) -> str:
        return "pong"

    # ------------------------------------------------------------------
    # Pipeline management
    # ------------------------------------------------------------------
    def load_pipeline(
        self,
        model_name: str,
        model_precision: str,
        model_rank: str,
        model_inference_steps: str,
        cache_dir: str = "",
        full_model_path: str = "",
    ) -> dict:
        """
        Load the Nunchaku/Qwen pipeline.
        Thread-safe: if two clients call this concurrently the second one
        waits for the first to finish.

        cache_dir is optional: when empty or omitted it is not forwarded to
        load_nunchaku_pipeline, which will then use the HuggingFace default
        (~/.cache/huggingface).
        """
        with self._pipeline_lock:
            try:
                logging.info(
                    f"Loading pipeline: {model_name} {model_precision} "
                    f"r{model_rank} steps={model_inference_steps}"
                )
                kwargs = dict(
                    model_name=model_name,
                    model_precision=model_precision,
                    model_rank=model_rank,
                    model_inference_steps=model_inference_steps,
                    full_model_path=full_model_path,
                )
                if cache_dir and cache_dir.strip():
                    kwargs["cache_dir"] = cache_dir.strip()
                pipe = load_nunchaku_pipeline(**kwargs)
                if pipe is None:
                    msg = f"Model '{model_name}' is not supported"
                    logging.warning(msg)
                    return {"ok": False, "msg": msg}

                self._pipeline = pipe
                logging.info("Pipeline loaded successfully.")
                return {"ok": True, "msg": "Pipeline loaded successfully"}

            except Exception as e:
                logging.exception("Error while loading the pipeline")
                return {"ok": False, "msg": str(e)}

    def is_pipeline_loaded(self) -> bool:
        """Return True if the pipeline is already in memory."""
        return self._pipeline is not None

    def unload_pipeline(self) -> dict:
        """Release the pipeline from VRAM (useful for debugging / reset)."""
        with self._pipeline_lock:
            self._pipeline = None
            logging.info("Pipeline unloaded from memory.")
            return {"ok": True, "msg": "Pipeline unloaded"}

    # ------------------------------------------------------------------
    # Stop control
    # ------------------------------------------------------------------
    def request_stop(self) -> bool:
        """
        Signal the server to reject new colorization requests.
        Note: any RPC call already in progress (atomic) will still complete.
        The client is responsible for not sending further requests.
        """
        self._stop_event.set()
        logging.info("Stop requested by client.")
        return True

    def clear_stop(self) -> bool:
        """Reset the stop flag before starting a new batch."""
        self._stop_event.clear()
        logging.info("Stop flag cleared.")
        return True

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    # ------------------------------------------------------------------
    # Colorization: single image (filesystem-based)
    # ------------------------------------------------------------------
    def colorize_image(
        self,
        in_path: str,
        out_path: str,
        prompt: str,
        img_size: int = 0,
        steps: int = 2,
    ) -> dict:
        """
        Corresponds to process_image() in dit_colorize_main.py.

        Parameters
        ----------
        in_path   : absolute path of the B&W input image
        out_path  : absolute path where the colorized image will be saved
        prompt    : text prompt for the model
        img_size  : 0 = original size, otherwise maximum long side in pixels
        steps     : inference steps (default 2)

        Returns
        -------
        {"ok": bool, "elapsed": float, "skipped": bool, "msg": str}
        skipped=True if the image was too dark or was already colorized
        """
        if self._pipeline is None:
            return {"ok": False, "elapsed": 0.0, "skipped": False,
                    "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "elapsed": 0.0, "skipped": True,
                    "msg": "Stop requested"}
        try:
            elapsed = process_image(
                input_path=Path(in_path),
                output_path=Path(out_path),
                pipe=self._pipeline,
                prompt=prompt,
                img_size=img_size,
                steps=steps,
            )
            skipped = (elapsed == 0.0)
            logging.info(f"colorize_image: {Path(in_path).name} -> {elapsed:.2f}s"
                         + (" [skipped]" if skipped else ""))
            return {"ok": True, "elapsed": float(elapsed), "skipped": skipped, "msg": ""}
        except Exception as e:
            logging.exception(f"colorize_image failed on {in_path}")
            return {"ok": False, "elapsed": 0.0, "skipped": False, "msg": str(e)}

    # ------------------------------------------------------------------
    # Colorization: image pair (fast/paired mode, filesystem-based)
    # ------------------------------------------------------------------
    def colorize_image_pair(
        self,
        img1_path: str,
        img2_path: str,
        out_dir: str,
        prompt: str,
        gap_px: int = 8,
    ) -> dict:
        """
        Corresponds to process_image_pair() in dit_colorize_main.py.
        Runs a single inference pass on two side-by-side images.

        Returns
        -------
        {"ok": bool, "elapsed": float, "msg": str}
        elapsed is the total time for the pair (divide by 2 for per-image time)
        """
        if self._pipeline is None:
            return {"ok": False, "elapsed": 0.0, "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "elapsed": 0.0, "msg": "Stop requested"}
        try:
            elapsed = process_image_pair(
                pipe=self._pipeline,
                img1_path=Path(img1_path),
                img2_path=Path(img2_path),
                output_dir=Path(out_dir),
                prompt=prompt,
                gap_px=gap_px,
            )
            logging.info(
                f"colorize_image_pair: {Path(img1_path).name} + "
                f"{Path(img2_path).name} -> {elapsed:.2f}s"
            )
            return {"ok": True, "elapsed": float(elapsed), "msg": ""}
        except Exception as e:
            logging.exception("colorize_image_pair failed")
            return {"ok": False, "elapsed": 0.0, "msg": str(e)}

    # ------------------------------------------------------------------
    # Colorization: single image fallback (filesystem-based)
    # ------------------------------------------------------------------
    def colorize_single_image(
        self,
        img_path: str,
        out_dir: str,
        prompt: str,
    ) -> dict:
        """
        Corresponds to process_single_image() in dit_colorize_main.py.
        Used as fallback for the odd image at the end of a batch.

        Returns
        -------
        {"ok": bool, "elapsed": float, "msg": str}
        """
        if self._pipeline is None:
            return {"ok": False, "elapsed": 0.0, "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "elapsed": 0.0, "msg": "Stop requested"}
        try:
            elapsed = process_single_image(
                pipe=self._pipeline,
                img_path=Path(img_path),
                output_dir=Path(out_dir),
                prompt=prompt,
            )
            logging.info(
                f"colorize_single_image: {Path(img_path).name} -> {elapsed:.2f}s"
            )
            return {"ok": True, "elapsed": float(elapsed), "msg": ""}
        except Exception as e:
            logging.exception("colorize_single_image failed")
            return {"ok": False, "elapsed": 0.0, "msg": str(e)}

    # ------------------------------------------------------------------
    # In-memory colorization: single frame (data transferred via RPC)
    # ------------------------------------------------------------------
    def colorize_frame(
        self,
        img_data: bytes,
        prompt: str,
        img_size: int = 0,
        steps: int = 2,
    ) -> dict:
        """
        Colorize a single B&W frame passed as raw PNG bytes.
        In-memory equivalent of process_single_image(): no filesystem access,
        the image travels entirely over RPC.

        Parameters
        ----------
        img_data : bytes
            B&W frame serialized as PNG (use _pil_to_bytes on the client side).
        prompt   : str
            Text prompt for the model.
        img_size : int
            Maximum long side before inference. 0 = original size.
        steps    : int
            Inference steps (default 2).

        Returns
        -------
        {"ok": bool, "data": bytes, "elapsed": float, "skipped": bool, "msg": str}
            data    = colorized frame serialized as PNG.
            skipped = True if the image was too dark (data = unchanged input).
        """
        if self._pipeline is None:
            return {"ok": False, "data": b"", "elapsed": 0.0,
                    "skipped": False, "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "data": b"", "elapsed": 0.0,
                    "skipped": True, "msg": "Stop requested"}
        try:
            original = _bytes_to_pil(img_data)

            if is_image_dark(original, threshold=9):
                logging.info("colorize_frame: image too dark, skipped")
                return {"ok": True, "data": _pil_to_bytes(original),
                        "elapsed": 0.0, "skipped": True, "msg": ""}

            bw        = ImageEnhance.Color(original).enhance(0.0)
            orig_size = original.size
            bw_in     = resize_long_side(bw, img_size) if img_size > 0 else bw

            t0 = time.perf_counter()
            colorized_lowres = _colorize_image(self._pipeline, bw_in, prompt, steps)
            elapsed = time.perf_counter() - t0

            result = upscale_with_lanczos(colorized_lowres, orig_size)
            logging.info(f"colorize_frame: {elapsed:.2f}s")
            return {"ok": True, "data": _pil_to_bytes(result),
                    "elapsed": float(elapsed), "skipped": False, "msg": ""}

        except Exception as e:
            logging.exception("colorize_frame failed")
            return {"ok": False, "data": b"", "elapsed": 0.0,
                    "skipped": False, "msg": str(e)}

    # ------------------------------------------------------------------
    # In-memory colorization: frame pair (data transferred via RPC)
    # ------------------------------------------------------------------
    def colorize_frame_pair(
        self,
        img1_data: bytes,
        img2_data: bytes,
        prompt: str,
        gap_px: int = 8,
    ) -> dict:
        """
        Colorize a pair of B&W frames with a single inference pass.
        In-memory equivalent of process_image_pair(): the two images are
        placed side by side, processed in one forward pass, then split back —
        no filesystem access.

        Parameters
        ----------
        img1_data, img2_data : bytes
            B&W frames serialized as PNG (use _pil_to_bytes on the client side).
        prompt  : str
            Text prompt for the model.
        gap_px  : int
            Neutral separator pixels between the two images in the merged
            input (default 8).

        Returns
        -------
        {"ok": bool, "data1": bytes, "data2": bytes, "elapsed": float,
         "skipped1": bool, "skipped2": bool, "msg": str}
            data1/data2   = colorized frames serialized as PNG.
            skipped1/2    = True if the corresponding frame was too dark
                            (the returned data is the unchanged input).
        """
        if self._pipeline is None:
            return {"ok": False, "data1": b"", "data2": b"",
                    "elapsed": 0.0, "skipped1": False, "skipped2": False,
                    "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "data1": b"", "data2": b"",
                    "elapsed": 0.0, "skipped1": True, "skipped2": True,
                    "msg": "Stop requested"}
        try:
            orig1 = _bytes_to_pil(img1_data)
            orig2 = _bytes_to_pil(img2_data)
            orig_size1, orig_size2 = orig1.size, orig2.size

            dark1 = is_image_dark(orig1, threshold=9)
            dark2 = is_image_dark(orig2, threshold=9)

            # Both dark: nothing to do
            if dark1 and dark2:
                return {"ok": True,
                        "data1": _pil_to_bytes(orig1), "data2": _pil_to_bytes(orig2),
                        "elapsed": 0.0, "skipped1": True, "skipped2": True, "msg": ""}

            # Only one dark: process the other one individually
            if dark1:
                res = self.colorize_frame(img2_data, prompt, img_size=0, steps=2)
                return {"ok": res["ok"],
                        "data1": _pil_to_bytes(orig1), "data2": res["data"],
                        "elapsed": res["elapsed"],
                        "skipped1": True, "skipped2": res["skipped"], "msg": res["msg"]}
            if dark2:
                res = self.colorize_frame(img1_data, prompt, img_size=0, steps=2)
                return {"ok": res["ok"],
                        "data1": res["data"], "data2": _pil_to_bytes(orig2),
                        "elapsed": res["elapsed"],
                        "skipped1": res["skipped"], "skipped2": True, "msg": res["msg"]}

            # Both valid: convert to B&W, resize to 1024px long side
            bw1  = ImageEnhance.Color(orig1).enhance(0.0)
            bw2  = ImageEnhance.Color(orig2).enhance(0.0)
            low1 = resize_long_side(bw1, 1024)
            low2 = resize_long_side(bw2, 1024)

            # Align heights with neutral padding (grey 127) if they differ
            if low1.height != low2.height:
                target_h = max(low1.height, low2.height)
                low1 = ImageOps.pad(low1, (low1.width, target_h), color=(127, 127, 127))
                low2 = ImageOps.pad(low2, (low2.width, target_h), color=(127, 127, 127))

            # Single inference on the merged image
            merged_input = merge_two_images_with_gap(low1, low2, gap_px=gap_px)

            t0 = time.perf_counter()
            colorized_merged = _colorize_image(self._pipeline, merged_input, prompt)
            elapsed = time.perf_counter() - t0

            # Resize back to merged-input dimensions, then split and upscale
            resized = upscale_with_lanczos(colorized_merged, merged_input.size)
            left, right = split_merged_output(resized, low1.width, gap_px=gap_px)
            out1 = upscale_with_lanczos(left,  orig_size1)
            out2 = upscale_with_lanczos(right, orig_size2)

            logging.info(f"colorize_frame_pair: {elapsed:.2f}s ({elapsed/2:.2f}s/frame)")
            return {"ok": True,
                    "data1": _pil_to_bytes(out1), "data2": _pil_to_bytes(out2),
                    "elapsed": float(elapsed),
                    "skipped1": False, "skipped2": False, "msg": ""}

        except Exception as e:
            logging.exception("colorize_frame_pair failed")
            return {"ok": False, "data1": b"", "data2": b"",
                    "elapsed": 0.0, "skipped1": False, "skipped2": False, "msg": str(e)}

    # ------------------------------------------------------------------
    # Shared-memory colorization — same-host only, zero-copy transport
    #
    # The CLIENT owns and manages all SharedMemory segments (create/unlink).
    # The server only attaches and detaches — no cleanup responsibility.
    #
    # Protocol:
    #   1. Client creates shm_in  (h * w * 3 bytes, uint8 RGB)
    #   2. Client creates shm_out (same size)
    #   3. Client writes input pixels into shm_in
    #   4. Client calls RPC → server reads shm_in, writes result to shm_out
    #   5. Client reads shm_out, then unlinks both segments
    # ------------------------------------------------------------------

    def colorize_frame_shm(
        self,
        shm_in_name: str,
        shm_out_name: str,
        height: int,
        width: int,
        prompt: str,
        img_size: int = 0,
        steps: int = 2,
    ) -> dict:
        """
        Shared-memory variant of colorize_frame().
        Zero-copy transport: only metadata travels over RPC.
        Only usable when client and server run on the same host.

        Parameters
        ----------
        shm_in_name  : name of the input SharedMemory segment (client-created)
        shm_out_name : name of the output SharedMemory segment (client-created)
        height, width: image dimensions in pixels
        prompt       : text prompt for the model
        img_size     : max long side before inference (0 = original)
        steps        : inference steps

        Returns
        -------
        {"ok": bool, "elapsed": float, "skipped": bool, "msg": str}
        """
        if self._pipeline is None:
            return {"ok": False, "elapsed": 0.0, "skipped": False,
                    "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "elapsed": 0.0, "skipped": True,
                    "msg": "Stop requested"}

        try:
            import numpy as np
            from multiprocessing.shared_memory import SharedMemory

            nbytes = height * width * 3
            shm_in  = SharedMemory(name=shm_in_name,  create=False)
            shm_out = SharedMemory(name=shm_out_name, create=False)

            try:
                arr_in = np.ndarray((height, width, 3), dtype=np.uint8,
                                    buffer=shm_in.buf)
                original = Image.fromarray(arr_in, mode="RGB")

                if is_image_dark(original, threshold=9):
                    arr_out = np.ndarray((height, width, 3), dtype=np.uint8,
                                         buffer=shm_out.buf)
                    arr_out[:] = arr_in
                    logging.info("colorize_frame_shm: image too dark, skipped")
                    return {"ok": True, "elapsed": 0.0, "skipped": True, "msg": ""}

                bw        = ImageEnhance.Color(original).enhance(0.0)
                orig_size = original.size
                bw_in     = resize_long_side(bw, img_size) if img_size > 0 else bw

                t0 = time.perf_counter()
                colorized_lowres = _colorize_image(self._pipeline, bw_in, prompt, steps)
                elapsed = time.perf_counter() - t0

                result = upscale_with_lanczos(colorized_lowres, orig_size)
                arr_out = np.ndarray((height, width, 3), dtype=np.uint8,
                                     buffer=shm_out.buf)
                arr_out[:] = np.array(result)

                logging.info(f"colorize_frame_shm: {elapsed:.2f}s")
                return {"ok": True, "elapsed": float(elapsed),
                        "skipped": False, "msg": ""}
            finally:
                shm_in.close()
                shm_out.close()

        except Exception as e:
            logging.exception("colorize_frame_shm failed")
            return {"ok": False, "elapsed": 0.0, "skipped": False, "msg": str(e)}

    def colorize_frame_pair_shm(
        self,
        shm_in1_name: str,
        shm_out1_name: str,
        height1: int,
        width1: int,
        shm_in2_name: str,
        shm_out2_name: str,
        height2: int,
        width2: int,
        prompt: str,
        gap_px: int = 8,
    ) -> dict:
        """
        Shared-memory variant of colorize_frame_pair().
        Zero-copy transport: only metadata travels over RPC.
        Only usable when client and server run on the same host.

        Returns
        -------
        {"ok": bool, "elapsed": float, "skipped1": bool, "skipped2": bool, "msg": str}
        """
        if self._pipeline is None:
            return {"ok": False, "elapsed": 0.0, "skipped1": False,
                    "skipped2": False, "msg": "Pipeline not loaded"}
        if self._stop_event.is_set():
            return {"ok": False, "elapsed": 0.0, "skipped1": True,
                    "skipped2": True, "msg": "Stop requested"}

        try:
            import numpy as np
            from multiprocessing.shared_memory import SharedMemory

            shm_in1  = SharedMemory(name=shm_in1_name,  create=False)
            shm_out1 = SharedMemory(name=shm_out1_name, create=False)
            shm_in2  = SharedMemory(name=shm_in2_name,  create=False)
            shm_out2 = SharedMemory(name=shm_out2_name, create=False)

            try:
                arr_in1 = np.ndarray((height1, width1, 3), dtype=np.uint8,
                                     buffer=shm_in1.buf)
                arr_in2 = np.ndarray((height2, width2, 3), dtype=np.uint8,
                                     buffer=shm_in2.buf)
                orig1 = Image.fromarray(arr_in1, mode="RGB")
                orig2 = Image.fromarray(arr_in2, mode="RGB")
                orig_size1, orig_size2 = orig1.size, orig2.size

                dark1 = is_image_dark(orig1, threshold=9)
                dark2 = is_image_dark(orig2, threshold=9)

                def _write_out(arr_in, shm_out, h, w):
                    arr_out = np.ndarray((h, w, 3), dtype=np.uint8,
                                         buffer=shm_out.buf)
                    arr_out[:] = arr_in

                if dark1 and dark2:
                    _write_out(arr_in1, shm_out1, height1, width1)
                    _write_out(arr_in2, shm_out2, height2, width2)
                    return {"ok": True, "elapsed": 0.0,
                            "skipped1": True, "skipped2": True, "msg": ""}

                if dark1:
                    _write_out(arr_in1, shm_out1, height1, width1)
                    res = self.colorize_frame_shm(
                        shm_in2_name, shm_out2_name, height2, width2, prompt)
                    return {"ok": res["ok"], "elapsed": res["elapsed"],
                            "skipped1": True, "skipped2": res["skipped"],
                            "msg": res["msg"]}

                if dark2:
                    _write_out(arr_in2, shm_out2, height2, width2)
                    res = self.colorize_frame_shm(
                        shm_in1_name, shm_out1_name, height1, width1, prompt)
                    return {"ok": res["ok"], "elapsed": res["elapsed"],
                            "skipped1": res["skipped"], "skipped2": True,
                            "msg": res["msg"]}

                bw1  = ImageEnhance.Color(orig1).enhance(0.0)
                bw2  = ImageEnhance.Color(orig2).enhance(0.0)
                low1 = resize_long_side(bw1, 1024)
                low2 = resize_long_side(bw2, 1024)

                if low1.height != low2.height:
                    target_h = max(low1.height, low2.height)
                    low1 = ImageOps.pad(low1, (low1.width, target_h),
                                        color=(127, 127, 127))
                    low2 = ImageOps.pad(low2, (low2.width, target_h),
                                        color=(127, 127, 127))

                merged_input = merge_two_images_with_gap(low1, low2, gap_px=gap_px)

                t0 = time.perf_counter()
                colorized_merged = _colorize_image(self._pipeline, merged_input, prompt)
                elapsed = time.perf_counter() - t0

                resized = upscale_with_lanczos(colorized_merged, merged_input.size)
                left, right = split_merged_output(resized, low1.width, gap_px=gap_px)
                out1 = upscale_with_lanczos(left,  orig_size1)
                out2 = upscale_with_lanczos(right, orig_size2)

                arr_out1 = np.ndarray((height1, width1, 3), dtype=np.uint8,
                                       buffer=shm_out1.buf)
                arr_out2 = np.ndarray((height2, width2, 3), dtype=np.uint8,
                                       buffer=shm_out2.buf)
                arr_out1[:] = np.array(out1)
                arr_out2[:] = np.array(out2)

                logging.info(f"colorize_frame_pair_shm: {elapsed:.2f}s "
                             f"({elapsed/2:.2f}s/frame)")
                return {"ok": True, "elapsed": float(elapsed),
                        "skipped1": False, "skipped2": False, "msg": ""}

            finally:
                shm_in1.close();  shm_out1.close()
                shm_in2.close();  shm_out2.close()

        except Exception as e:
            logging.exception("colorize_frame_pair_shm failed")
            return {"ok": False, "elapsed": 0.0,
                    "skipped1": False, "skipped2": False, "msg": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _load_pipeline_config(config_path: str) -> dict:
    """
    Read and validate the JSON pipeline configuration file.

    Required keys: model_name, model_precision, model_rank, model_inference_steps
    Optional keys:
        cache_dir       — omit or set to "" to use the HuggingFace default cache
        full_model_path — omit or set to "" when not needed

    Returns the config dict on success; raises SystemExit on any error.
    """
    path = Path(config_path)
    if not path.is_file():
        logging.error(f"Pipeline config file not found: {config_path}")
        sys.exit(1)

    try:
        with path.open(encoding="utf-8") as fh:
            cfg = json.load(fh)
    except json.JSONDecodeError as exc:
        logging.error(f"Invalid JSON in pipeline config '{config_path}': {exc}")
        sys.exit(1)

    required_keys = {
        "model_name", "model_precision", "model_rank",
        "model_inference_steps",
    }
    missing = required_keys - cfg.keys()
    if missing:
        logging.error(
            f"Pipeline config is missing required keys: {', '.join(sorted(missing))}"
        )
        sys.exit(1)

    cfg.setdefault("cache_dir", "")
    cfg.setdefault("full_model_path", "")
    return cfg


def main():
    parser = argparse.ArgumentParser(
        description="HAVC Colorize RPC Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Address to listen on")
    parser.add_argument("--port", type=int, default=8765,
                        help="TCP port")
    parser.add_argument("--logfile", default="",
                        help="Optional path for a log file")
    parser.add_argument("--module-dir", default="",
                        help="Directory containing dit_colorize_main.py "
                             "(default: same directory as this script)")
    parser.add_argument("--load-pipeline", action="store_true",
                        help="Load the colorization pipeline at startup using "
                             "the parameters from --pipeline-config")
    parser.add_argument("--pipeline-config", default="",
                        metavar="CONFIG.json",
                        help="Path to the JSON file with pipeline parameters "
                             "(required when --load-pipeline is set)")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Validate --pipeline-config is provided when --load-pipeline is set
    # ------------------------------------------------------------------
    if args.load_pipeline and not args.pipeline_config.strip():
        parser.error("--pipeline-config is required when --load-pipeline is set")

    # ------------------------------------------------------------------
    # Logging setup
    # ------------------------------------------------------------------
    handlers = [logging.StreamHandler()]
    if args.logfile:
        handlers.append(logging.FileHandler(args.logfile, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )

    # ------------------------------------------------------------------
    # Module directory resolution: --module-dir takes precedence over
    # the script directory detected at import time
    # ------------------------------------------------------------------
    module_dir = args.module_dir.strip() if args.module_dir.strip() else _script_dir
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    main_module_path = os.path.join(module_dir, "dit_colorize_main.py")
    logging.info(f"module_dir             : {module_dir}")
    logging.info(f"dit_colorize_main.py   : {'found' if os.path.exists(main_module_path) else 'NOT FOUND'}")
    if not os.path.exists(main_module_path):
        logging.error(
            f"dit_colorize_main.py not found in '{module_dir}'. "
            "Use --module-dir to point to the correct directory."
        )
        logging.debug(f"Full sys.path: {sys.path}")

    # ------------------------------------------------------------------
    # Service + server setup
    # ------------------------------------------------------------------
    service = ColorizeService()

    # ------------------------------------------------------------------
    # Optional startup pipeline load
    # ------------------------------------------------------------------
    if args.load_pipeline:
        cfg = _load_pipeline_config(args.pipeline_config)
        logging.info(f"Loading pipeline from config: {args.pipeline_config}")
        result = service.load_pipeline(
            model_name=cfg["model_name"],
            model_precision=cfg["model_precision"],
            model_rank=cfg["model_rank"],
            model_inference_steps=cfg["model_inference_steps"],
            cache_dir=cfg["cache_dir"],
            full_model_path=cfg["full_model_path"],
        )
        if not result["ok"]:
            logging.error(f"Failed to load pipeline: {result['msg']}")
            sys.exit(1)

    server = ThreadedXMLRPCServer(
        addr=(args.host, args.port),
        requestHandler=ColorizeRequestHandler,
        allow_none=True,
        use_builtin_types=True,   # transparent bytes↔base64; required for colorize_frame*
        logRequests=False,
    )
    server.register_instance(service)
    server.register_introspection_functions()

    logging.info(f"HAVC Colorize RPC Server listening on {args.host}:{args.port}")
    logging.info("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
