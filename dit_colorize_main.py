"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2024-12-26
version:
LastEditors: Dan64
LastEditTime: 2026-05-31
-------------------------------------------------------------------------------
Batch colorization supporting two model backends:

1. nunchaku-qwen  :  SVDQuant FP4 model (Nunchaku):
     svdq-fp4_r128-qwen-image-edit-2509-lightning-4steps-251115.safetensors
     - Optimized for RTX 50 (Blackwell)
     - Uses Nunchaku SVDQuant (4-bit) for the transformer
     - Maintains FP16/BF16 for peripheral layers

2. gguf-q3-qwen / gguf-q4-qwen  :  GGUF quantized models (CPU + GPU):
     UNet:  qwen-image-edit-2511-Q3_K_S.gguf
     CLIP:  Qwen2.5-VL-7B-Instruct-Q3_K_S.gguf  (q3) or Q4_K_S.gguf (q4)
     - Uses standalone GGUF loader (no ComfyUI dependency)
     - Dequantizes at load time, feeds into standard diffusers pipeline
-------------------------------------------------------------------------------
"""

import os
import sys
import time
import math
from pathlib import Path
from PIL import Image, ImageEnhance, ImageStat, ImageOps


def set_hf_cache_dir(hf_cache_dir: str):

    if os.path.isdir(hf_cache_dir):
        os.environ['HF_HOME'] = hf_cache_dir
        os.environ['HF_HUB_CACHE'] = os.path.join(hf_cache_dir, 'hub')
        from huggingface_hub import constants
        print(f"HF_HOME: {constants.HF_HOME}")
        print(f"HF_HUB_CACHE: {constants.HF_HUB_CACHE}")


# ----------------------------
# HuggingFace auto-download helper
# ----------------------------
def _ensure_models(files: dict):
    """Download missing model files from HuggingFace."""
    import logging
    from huggingface_hub import hf_hub_download
    _log = logging.getLogger(__name__)
    for name, (local_path, repo_id, hf_filename) in files.items():
        if local_path is None:
            continue
        if os.path.exists(local_path):
            continue
        _log.info(f"Downloading {name} from {repo_id}/{hf_filename} ...")
        try:
            downloaded = hf_hub_download(
                repo_id=repo_id,
                filename=hf_filename,
                local_dir=os.path.dirname(local_path),
                local_dir_use_symlinks=False,
            )
            # mmproj needs renaming
            if hf_filename != os.path.basename(local_path):
                os.rename(downloaded, local_path)
            _log.info(f"  -> {local_path}")
        except Exception as e:
            _log.warning(f"Failed to download {name}: {e}")


# ----------------------------
# Load GGUF Q3 pipeline
# ----------------------------
def load_gguf_pipeline(model_name: str, unet_gguf_path: str, clip_gguf_path: str,
                       cache_dir: str = "", lora_path: str = "",
                       torch_compile=False, device="cuda", vae_name="qwen_image_vae.safetensors",
                       hf_unet="unsloth/Qwen-Image-Edit-2511-GGUF",
                       hf_clip="unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
                       hf_vae="Comfy-Org/Qwen-Image_ComfyUI",
                       hf_lora="lightx2v/Qwen-Image-Edit-2511-Lightning"):
    """
    Load a GGUF-quantized Qwen Image Edit pipeline.

    The HuggingFace pipeline provides VAE, scheduler, tokenizer, and
    feature extractor (downloaded once, then cached).
    The GGUF files provide the quantized UNet (transformer) and CLIP
    (text_encoder) weights, dequantized at load time via gguf_loader.

    Optionally, a ComfyUI-format LoRA (Lightning 4-step) can be merged
    into the transformer to enable fast inference.

    Parameters
    ----------
    model_name      : "gguf-q3-qwen" or "gguf-q4-qwen"
    unet_gguf_path  : path to the UNet GGUF file
    clip_gguf_path  : path to the CLIP GGUF file
    cache_dir       : HuggingFace cache directory (optional)
    lora_path       : path to the LoRA safetensors file (optional)
    torch_compile   : enable torch.compile on the transformer
    device          : target device ("cuda" or "cpu")
    """
    if model_name not in ("gguf-qwen", "nunchaku-qwen"):
        return None

    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    # Resolve relative paths against comfy_bridge directory
    import os as _os
    _bridge_dir = _os.path.join(_os.path.dirname(__file__), "comfy_bridge")
    unet_gguf_path = _os.path.join(_bridge_dir, unet_gguf_path) if not _os.path.isabs(unet_gguf_path) else unet_gguf_path
    clip_gguf_path = _os.path.join(_bridge_dir, clip_gguf_path) if not _os.path.isabs(clip_gguf_path) else clip_gguf_path
    if lora_path and not _os.path.isabs(lora_path):
        lora_path = _os.path.join(_bridge_dir, lora_path)

    from comfy_bridge import load_gguf_pipeline as comfy_load_gguf

    # Auto-download missing files from HuggingFace
    _auto = _os.environ.get("COMFY_AUTO_DOWNLOAD", "1") == "1"
    _bridge = _bridge_dir
    _vae_local = _os.path.join(_bridge, "models", "vae", vae_name)
    _files = {
        "unet": (unet_gguf_path, hf_unet, _os.path.basename(unet_gguf_path)),
        "clip": (clip_gguf_path, hf_clip, _os.path.basename(clip_gguf_path)),
        "vae":  (_vae_local, hf_vae, "split_files/vae/" + vae_name),
        "lora": (lora_path, hf_lora, _os.path.basename(lora_path)) if lora_path else None,
    }
    # mmproj  :  special handling: downloaded as mmproj-BF16.gguf, renamed locally
    _mmproj_src = _os.path.join(_bridge, "models", "clip", "Qwen2.5-VL-7B-Instruct-mmproj-BF16.gguf")
    if not _os.path.exists(_mmproj_src):
        _files["mmproj"] = (_mmproj_src, hf_clip, "mmproj-BF16.gguf")

    if _auto:
        _ensure_models(_files)

    pipeline = comfy_load_gguf(unet_gguf_path, clip_gguf_path, lora_path=lora_path, vae_name=vae_name)
    return pipeline


# ----------------------------
# Load SVDQuant FP4 pipeline
# ----------------------------
def load_nunchaku_pipeline(model_name: str, model_precision: str, model_rank, model_inference_steps,
                           cache_dir: str = "", base_model_path: str = "", full_model_path: str = "",
                           torch_compile=False, device="cuda", vae_name="qwen_image_vae.safetensors",
                           hf_unet="", hf_clip="", hf_vae="", hf_lora=""):

    if model_name not in ('nunchaku-qwen'):
        return None

    set_hf_cache_dir(cache_dir)

    if full_model_path != "":
        return load_qwen_pipeline(full_model_path, cache_dir, model_precision, torch_compile, device)

    if base_model_path == "":
        base_model_path = "nunchaku-ai/nunchaku-qwen-image-edit-2509/lightning-251115"

    model_path = f"{base_model_path}/svdq-{model_precision}_r{model_rank}-qwen-image-edit-2509-lightning-{model_inference_steps}steps-251115.safetensors"

    return load_qwen_pipeline(model_path, cache_dir, model_precision, torch_compile, device)

def load_qwen_pipeline(model_path: str, cache_dir: str, model_precision: str = "fp4", torch_compile=False, device="cuda"):
    print(f"Loading SVDQuant {model_precision.upper()} transformer from: {model_path}")

    import torch
    # Nunchaku (SVDQuant transformer)
    from nunchaku.models import NunchakuQwenImageTransformer2DModel

    # Hugging Face
    from diffusers import (
        QwenImageEditPlusPipeline,
        FlowMatchEulerDiscreteScheduler,
    )

    # Global CUDA flags
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.set_float32_matmul_precision("high")

    # SDPA flags (necessari per Flash2)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(False)

    # 1. Setup Scheduler exactly as the sample code does
    scheduler_config = {
        "base_image_seq_len": 256,
        "base_shift": math.log(3),
        "num_train_timesteps": 1000,
        "shift": 1.0,
        "use_dynamic_shifting": True,
    }
    scheduler = FlowMatchEulerDiscreteScheduler.from_config(scheduler_config)

    # 2. Initialize the Transformer
    #
    # For int4: nunchaku always initializes wscales with fp4 group-size (16) regardless
    # of the precision argument, then load_state_dict fails because int4 checkpoints use
    # group-size 64 (4× fewer scale rows).  The fix temporarily patches load_state_dict
    # to resize every wscales parameter to match the checkpoint shape before loading.
    if model_precision == "int4":
        _original_load_sd = NunchakuQwenImageTransformer2DModel.load_state_dict

        def _int4_load_state_dict(self, state_dict, strict=True, **kwargs):
            for name, ckpt_tensor in state_dict.items():
                if "wscales" not in name:
                    continue
                parts = name.split(".")
                module = self
                try:
                    for part in parts[:-1]:
                        module = getattr(module, part)
                    param_name = parts[-1]
                    current = getattr(module, param_name)
                    if current.shape != ckpt_tensor.shape:
                        setattr(module, param_name, torch.nn.Parameter(
                            torch.zeros(ckpt_tensor.shape,
                                        dtype=current.dtype,
                                        device=current.device)
                        ))
                except AttributeError:
                    pass

            return _original_load_sd(self, state_dict, strict=strict, **kwargs)

        NunchakuQwenImageTransformer2DModel.load_state_dict = _int4_load_state_dict

    try:
        transformer = NunchakuQwenImageTransformer2DModel.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device=device,
        )
    finally:
        if model_precision == "int4":
            NunchakuQwenImageTransformer2DModel.load_state_dict = _original_load_sd

    # 3. Load the Pipeline
    # This will automatically download the correct VAE and VL Encoder
    # from Hugging Face and plug in your local transformer.
    pipe = QwenImageEditPlusPipeline.from_pretrained(
        "Qwen/Qwen-Image-Edit-2509",
        transformer=transformer,
        scheduler=scheduler,
        torch_dtype=torch.bfloat16,
    )

    # 4. VRAM Optimization for 16GB (RTX 5070 Ti)
    # The sample uses a custom offload if memory is low
    if torch.cuda.get_device_properties(0).total_memory / (1024 ** 3) < 48:
        print("Optimizing VRAM ...")
        transformer.set_offload(True, use_pin_memory=True, num_blocks_on_gpu=1)
        pipe._exclude_from_cpu_offload.append("transformer")
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()

    if torch_compile:
        pipe.transformer = torch.compile(pipe.transformer, fullgraph=False, dynamic=False)

    # 5. Compatibility patch: nunchaku 1.2.1 calls
    #      pos_embed(img_shapes, txt_seq_lens, device=...)
    #    passing txt_seq_lens as a positional argument.
    #    Newer diffusers QwenEmbedRope.forward() expects it as a keyword argument
    #    (txt_seq_lens=... deprecated, or max_txt_seq_len=...).
    #    The wrapper below converts the positional call to keyword so both
    #    old and new diffusers APIs are satisfied transparently.
    _orig_pos_embed_fwd = pipe.transformer.pos_embed.forward

    def _compat_pos_embed_fwd(img_shapes, txt_seq_lens=None, device=None, **kwargs):
        return _orig_pos_embed_fwd(
            img_shapes,
            txt_seq_lens=txt_seq_lens,
            device=device,
            **kwargs,
        )

    pipe.transformer.pos_embed.forward = _compat_pos_embed_fwd

    return pipe


# ----------------------------
# Load LongCat Image Edit Turbo pipeline
# ----------------------------
def load_longcat_pipeline(model_name: str, model_precision: str = "", model_rank: str = "",
                          model_inference_steps: str = "4", cache_dir: str = "",
                          full_model_path: str = "", vae_name: str = "lct_vae.safetensors",
                          hf_unet: str = "vantagewithai/LongCat-Image-Edit-Turbo-GGUF",
                          hf_clip: str = "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
                          hf_vae: str = "meituan-longcat/LongCat-Image-Edit-Turbo",
                          **kwargs):
    """
    Load the LongCat-Image-Edit-Turbo GGUF pipeline via ComfyUI runtime.

    Parameters
    ----------
    model_name  : "longcat-gguf"
    model_precision : UNet GGUF filename (e.g. LongCat-Image-Edit-Turbo-Q4_K_M.gguf)
    model_rank      : CLIP GGUF filename (e.g. Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf)
    model_inference_steps : default inference steps (default "4")
    hf_unet/clip/vae : HuggingFace repo for auto-download
    """
    if model_name != "longcat-gguf":
        return None

    import os as _os
    _bridge_dir = _os.path.join(_os.path.dirname(__file__), "comfy_bridge")

    unet_name = model_precision if model_precision else "LongCat-Image-Edit-Turbo-Q4_K_M.gguf"
    clip_name = model_rank if model_rank else "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"

    # Auto-download missing models
    _auto = _os.environ.get("COMFY_AUTO_DOWNLOAD", "1") == "1"
    _files = {}
    for tag, filename, repo, folder in [
        ("unet", unet_name, hf_unet, "unet"),
        ("clip", clip_name, hf_clip, "clip"),
        ("vae",  vae_name,  hf_vae,  "vae"),
    ]:
        local = _os.path.join(_bridge_dir, "models", folder, filename)
        hf_path = filename
        if folder == "vae": hf_path = "vae/diffusion_pytorch_model.safetensors"
        _files[tag] = (local, repo, hf_path)

    if _auto:
        _ensure_models(_files)

    from comfy_bridge.longcat_colorize import load_pipeline as _load, colorize as _colorize

    pipeline = _load(unet_name=unet_name, clip_name=clip_name, vae_name=vae_name)
    pipeline["_model_type"] = "longcat-gguf"
    pipeline["_colorize_fn"] = _colorize
    return pipeline
def upscale_with_lanczos(image, target_size):
    return image.resize(target_size, Image.Resampling.LANCZOS)

def resize_long_side(img: Image.Image, dim: int = 1024) -> Image.Image:
    """Resize so the longest side equals `dim`, keeping aspect ratio.
    Dimensions are snapped to multiples of 16 (required by the Qwen VAE:
    8× spatial compression + 2×2 patch packing = factor 16)."""
    w, h = img.size
    max_size = max(w, h)
    if max_size < dim:
        return img  # no resize is needed
    ratio = dim / max_size
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    # Snap to multiples of 16 (Qwen VAE requirement)
    SNAP = 16
    new_w = ((new_w + SNAP - 1) // SNAP) * SNAP
    new_h = ((new_h + SNAP - 1) // SNAP) * SNAP
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def colorize_image(pipe, img: Image, prompt:str, steps: int = 2, seed: int=42) -> Image:
    # LongCat pipeline (dict with _model_type marker)
    if isinstance(pipe, dict) and pipe.get("_model_type") == "longcat-gguf":
        _colorize_fn = pipe.get("_colorize_fn")
        return _colorize_fn(pipe, img, prompt=prompt, steps=steps, seed=seed)

    # GGUF pipeline (dict)  :  comfy_bridge colorize
    if isinstance(pipe, dict):
        from comfy_bridge import colorize
        return colorize(pipe, img, prompt, steps, seed)

    # Nunchaku pipeline (diffusers QwenImageEditPlusPipeline)
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = torch.Generator(device=device).manual_seed(seed)
    result = pipe(image=img, prompt=prompt, num_inference_steps=steps, generator=generator, true_cfg_scale=1.0)
    return result.images[0]

def is_image_dark(img: Image, threshold: int = 20):
    """
    Returns True if the image is totally black or very dark.

    :param img      : image.
    :param threshold: Average pixel intensity below which image is considered "dark".
                      0 = completely black, 255 = completely white (for grayscale).
                      For RGB, average across channels.
    """
    # Convert to grayscale to simplify brightness assessment
    grayscale = img.convert('L')
    stat = ImageStat.Stat(grayscale)
    avg_brightness = stat.mean[0]  # Mean of grayscale channel
    return avg_brightness < threshold

def merge_two_images_with_gap(img1: Image.Image, img2: Image.Image, gap_px: int = 16) -> Image.Image:
    """Merge two same-height images with neutral gray gap."""
    w1, h1 = img1.size
    w2, h2 = img2.size
    assert h1 == h2, "Images must have the same height"
    total_width = w1 + gap_px + w2
    merged = Image.new("RGB", (total_width, h1), (127, 127, 127))
    merged.paste(img1, (0, 0))
    merged.paste(img2, (w1 + gap_px, 0))
    return merged

def split_merged_output(colorized_merged: Image.Image, width1: int, gap_px: int = 16) -> tuple[Image.Image, Image.Image]:
    """Split merged output back into two images."""
    total_w, h = colorized_merged.size
    left = colorized_merged.crop((0, 0, width1, h))
    right = colorized_merged.crop((width1 + gap_px, 0, total_w, h))
    return left, right

def process_image(input_path, output_path, pipe, prompt: str = None, img_size:int = 0, steps: int = 2, log_fn=None) -> float:

    if output_path.exists():
        if log_fn is not None:
            log_fn(f'ℹ️ Image: "{output_path}" already colorized')
        return 0

    original = Image.open(input_path).convert("RGB")

    if is_image_dark(original, threshold=9):
        if log_fn is not None:
            log_fn(f'⚠️ Image: "{input_path}" too dark to be colorized')
        return 0

    t_elapsed = process_image_standard(pipe, original, output_path, prompt, img_size=img_size, steps=steps)

    if log_fn is not None:
        log_fn(f"✅ colored: {output_path} [{t_elapsed:.2f} sec.]")

    return t_elapsed

def process_single_image(pipe, img_path: Path, output_dir: Path, prompt: str, steps: int = 2) -> float:
    """Fallback for odd-numbered batches."""
    out_path = output_dir / (img_path.stem + ".jpg")
    original = Image.open(img_path).convert("RGB")

    if is_image_dark(original, threshold=9):
        return 0

    return process_image_standard(pipe, original, out_path, prompt, steps=steps)

def process_image_standard(pipe, original, output_path, prompt, img_size: int = 1024, steps: int = 2) -> float:

    bw = ImageEnhance.Color(original).enhance(0.0)
    orig_size = original.size

    if img_size == 0:
        bw_lowres = bw
    else:
        bw_lowres = resize_long_side(bw, img_size)

    t_start = time.perf_counter()
    colorized_lowres = colorize_image(pipe, bw_lowres, prompt, steps)
    t_end = time.perf_counter()

    colorized_upscaled = upscale_with_lanczos(colorized_lowres, orig_size)
    colorized_upscaled.save(output_path)

    return t_end - t_start

# ----------------------------
# Pair Processing
# ----------------------------
def process_image_pair(pipe, img1_path: Path, img2_path: Path, output_dir: Path, prompt: str, gap_px=16, steps: int = 2) -> float:
    # Load originals
    orig1 = Image.open(img1_path).convert("RGB")
    orig2 = Image.open(img2_path).convert("RGB")
    orig_size1 = orig1.size
    orig_size2 = orig2.size

    # set output path, save as JPG
    out1 = output_dir / (img1_path.stem + ".jpg")
    out2 = output_dir / (img2_path.stem + ".jpg")

    # set flags dark
    orig1_dark = is_image_dark(orig1, threshold=9)
    orig2_dark = is_image_dark(orig2, threshold=9)

    if orig1_dark and orig2_dark:
        return 0

    if orig1_dark:
        return process_image_standard(pipe, orig2, out2, prompt, steps=steps)

    if orig2_dark:
        return process_image_standard(pipe, orig1, out1, prompt, steps=steps)

    # Convert to B&W
    bw1 = ImageEnhance.Color(orig1).enhance(0.0)
    bw2 = ImageEnhance.Color(orig2).enhance(0.0)

    # Resize to 1024px long side
    lowres1 = resize_long_side(bw1, 1024)
    lowres2 = resize_long_side(bw2, 1024)
    #lowres1 = bw1
    #lowres2 = bw2

    # Ensure same height
    if lowres1.height != lowres2.height:
        target_h = max(lowres1.height, lowres2.height)
        lowres1 = ImageOps.pad(lowres1, (lowres1.width, target_h), color=(127, 127, 127))
        lowres2 = ImageOps.pad(lowres2, (lowres2.width, target_h), color=(127, 127, 127))

    # Merge with gap
    merged_input = merge_two_images_with_gap(lowres1, lowres2, gap_px=gap_px)

    # Single inference
    t_start = time.perf_counter()
    colorized_merged = colorize_image(pipe, merged_input, prompt, steps=steps)
    t_end = time.perf_counter()

    resized_colorized_merged = upscale_with_lanczos(colorized_merged, merged_input.size)

    # Split output
    left_img, right_img = split_merged_output(resized_colorized_merged, lowres1.width, gap_px=gap_px)

    # Upscale to original sizes
    left_final = upscale_with_lanczos(left_img, orig_size1)
    right_final = upscale_with_lanczos(right_img, orig_size2)

    # save images as JPG
    left_final.save(out1)
    right_final.save(out2)

    return t_end - t_start


