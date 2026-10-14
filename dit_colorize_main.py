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
import json
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
    for name, entry in files.items():
        if entry is None:
            continue
        local_path, repo_id, hf_filename = entry
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
                       hf_lora="lightx2v/Qwen-Image-Edit-2511-Lightning",
                       clip_mmproj: str = "", clip_mmproj_hf_name: str = "",
                       unet_hf_name: str = ""):
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
    unet_gguf_path : path to the UNet file -- a GGUF quant or a native
                     safetensors checkpoint (e.g. Comfy-Org int8 ConvRot).
    unet_hf_name   : optional, the UNet filename as it exists on the hf_unet
                     repo, when it differs from the local basename (e.g. the
                     Comfy-Org "split_files/diffusion_models/" layout).
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
    if clip_mmproj and not _os.path.isabs(clip_mmproj):
        clip_mmproj = _os.path.join(_bridge_dir, clip_mmproj)

    from comfy_bridge import load_gguf_pipeline as comfy_load_gguf

    # Auto-download missing files from HuggingFace
    _auto = _os.environ.get("COMFY_AUTO_DOWNLOAD", "1") == "1"
    _bridge = _bridge_dir
    _vae_local = _os.path.join(_bridge, "models", "vae", vae_name)
    _files = {
        # unet: unet_hf_name overrides the assumed remote path when the file
        # is not stored at the repo root (e.g. Comfy-Org's split_files/ layout).
        "unet": (unet_gguf_path, hf_unet, unet_hf_name or _os.path.basename(unet_gguf_path)),
        "clip": (clip_gguf_path, hf_clip, _os.path.basename(clip_gguf_path)),
        "vae":  (_vae_local, hf_vae, "split_files/vae/" + vae_name),
        "lora": (lora_path, hf_lora, _os.path.basename(lora_path)) if lora_path else None,
        # mmproj: generalized -- remote filename can differ from the
        # desired local name (e.g. generic "mmproj-BF16.gguf" upstream), driven by
        # config instead of a hardcoded literal.
        "mmproj": (clip_mmproj, hf_clip, clip_mmproj_hf_name or _os.path.basename(clip_mmproj)) if clip_mmproj else None,
    }

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
                          clip_mmproj: str = "", clip_mmproj_hf_name: str = "",
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
    clip_mmproj / clip_mmproj_hf_name : optional mmproj GGUF for the CLIP's vision
    tower -- same mechanism as gguf-qwen/qwen21-viggle. Unlike those
    two, this function previously had NO mmproj handling at all (not even
    hardcoded): on a fresh install using only longcat-gguf, the mmproj was never
    auto-downloaded and gguf_mmproj_loader() would silently fall back to a
    text-only CLIP (no vision tower merged).
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
    if clip_mmproj:
        _mmproj_local = clip_mmproj if _os.path.isabs(clip_mmproj) else _os.path.join(_bridge_dir, clip_mmproj)
        _files["mmproj"] = (_mmproj_local, hf_clip, clip_mmproj_hf_name or _os.path.basename(_mmproj_local))

    if _auto:
        _ensure_models(_files)

    from comfy_bridge.longcat_colorize import load_pipeline as _load, colorize as _colorize

    pipeline = _load(unet_name=unet_name, clip_name=clip_name, vae_name=vae_name)
    pipeline["_model_type"] = "longcat-gguf"
    pipeline["_colorize_fn"] = _colorize
    return pipeline


def load_viggle_pipeline(model_name: str, unet_path: str, clip_path: str,
                          lora_path: str = "", vae_name: str = "qwen_image_2.1_vae_bf16.safetensors",
                          hf_unet="Comfy-Org/Qwen-Image-2.1",
                          hf_clip="Comfy-Org/Qwen-Image-2.1",
                          hf_vae="Comfy-Org/Qwen-Image-2.1",
                          hf_lora="Viggle/Qwen-Image-2.1-viggle-turbo",
                          clip_mmproj: str = "",
                          clip_mmproj_hf_name: str = "",
                          unet_hf_name: str = ""):
    """
    Load the Qwen-Image-2.1 pipeline (native ComfyUI int8 ConvRot weights).
    The Viggle-Turbo LoRA is applied as an unmerged runtime hook when
    lora_path is given; with lora_path empty the checkpoint is used as-is
    (for models that already have the LoRA merged in).

    clip_mmproj : optional path to a separate mmproj GGUF file, only used
    when clip_path points to a GGUF text encoder (vs. the default
    safetensors path). Downloaded from the same hf_clip repo as clip_path.
    clip_mmproj_hf_name : optional, the mmproj filename as it exists on the
    hf_clip repo, when it differs from clip_mmproj's local basename (e.g.
    a generic "mmproj-BF16.gguf" upstream vs. a locally prefixed name).
    Defaults to clip_mmproj's own basename when not given.
    unet_hf_name : optional, the UNet filename as it exists on the hf_unet
    repo, when it differs from the default download path the loader assumes
    ("diffusion_models/<local filename>", the Comfy-Org layout) -- e.g. for
    files kept at the root of the Viggle repo.
    """
    if model_name != "qwen21-viggle":
        return None

    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    import os as _os
    _bridge_dir = _os.path.join(_os.path.dirname(__file__), "comfy_bridge")
    unet_path = _os.path.join(_bridge_dir, unet_path) if not _os.path.isabs(unet_path) else unet_path
    clip_path = _os.path.join(_bridge_dir, clip_path) if not _os.path.isabs(clip_path) else clip_path
    if lora_path and not _os.path.isabs(lora_path):
        lora_path = _os.path.join(_bridge_dir, lora_path)
    if clip_mmproj and not _os.path.isabs(clip_mmproj):
        clip_mmproj = _os.path.join(_bridge_dir, clip_mmproj)

    from comfy_bridge import load_viggle_pipeline as _comfy_load_viggle, colorize_viggle as _colorize_viggle

    _auto = _os.environ.get("COMFY_AUTO_DOWNLOAD", "1") == "1"
    _vae_local = _os.path.join(_bridge_dir, "models", "vae", vae_name)
    # hf_clip may point to a flat community GGUF repo (e.g. lmstudio-community/
    # Qwen3-VL-8B-Instruct-GGUF, no subfolder) instead of the structured Comfy-Org
    # repo -- mirror load_gguf_pipeline()'s convention (no prefix for GGUF clip
    # files) rather than assuming the Comfy-Org "text_encoders/" layout always applies.
    _clip_hf_filename = (
        _os.path.basename(clip_path) if clip_path.lower().endswith(".gguf")
        else "text_encoders/" + _os.path.basename(clip_path)
    )
    _files = {
        # unet: unet_hf_name overrides the assumed remote path when the file
        # is not stored under the Comfy-Org-style "diffusion_models/" folder
        # (e.g. the merged checkpoints at the root of the Viggle repo).
        "unet": (unet_path,  hf_unet, unet_hf_name or ("diffusion_models/" + _os.path.basename(unet_path))),
        "clip": (clip_path,  hf_clip, _clip_hf_filename),
        "vae":  (_vae_local, hf_vae,  "vae/" + vae_name),
        "lora": (lora_path,  hf_lora, _os.path.basename(lora_path)) if lora_path else None,
        # mmproj: the remote filename can differ from the desired local one (e.g. a
        # generic "mmproj-BF16.gguf" upstream vs. a locally prefixed name) -- same
        # ad-hoc handling load_gguf_pipeline() already does for gguf-qwen's mmproj,
        # generalized here via clip_mmproj_hf_name instead of a hardcoded literal.
        # Falls back to clip_mmproj's own basename when not given (today's behavior).
        "mmproj": (clip_mmproj, hf_clip, clip_mmproj_hf_name or _os.path.basename(clip_mmproj)) if clip_mmproj else None,
    }
    if _auto:
        _ensure_models(_files)

    pipeline = _comfy_load_viggle(unet_path, clip_path, lora_path=lora_path, vae_name=vae_name, clip_mmproj=clip_mmproj)
    pipeline["_model_type"] = "qwen21-viggle"
    pipeline["_colorize_fn"] = _colorize_viggle
    return pipeline


def load_qwen21_turbo_pipeline(model_name: str, unet_path: str, clip_path: str,
                                vae_name: str = "qwen_image_2.1_vae_bf16.safetensors",
                                hf_unet="Comfy-Org/Qwen-Image-2.1",
                                hf_clip="Comfy-Org/Qwen-Image-2.1",
                                hf_vae="Comfy-Org/Qwen-Image-2.1",
                                unet_hf_name: str = ""):
    """
    Load the Qwen-Image-2.1-Turbo pipeline (native ComfyUI int8 ConvRot
    weights from the Comfy-Org repack).

    Same architecture and loading path as qwen21-viggle (Qwen3-VL 8B text
    encoder + the 2.1 VAE, stock ComfyUI loaders): the difference is
    entirely in the sampling recipe -- the checkpoint ships its own 8-step
    sigma table (ManualSigmas) and no LoRA is involved.

    unet_hf_name : optional, the UNet filename as it exists on the hf_unet
    repo, when it differs from the default download path the loader assumes
    ("diffusion_models/<local filename>", the Comfy-Org layout).
    """
    if model_name != "qwen21-turbo":
        return None

    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    import os as _os
    _bridge_dir = _os.path.join(_os.path.dirname(__file__), "comfy_bridge")
    unet_path = _os.path.join(_bridge_dir, unet_path) if not _os.path.isabs(unet_path) else unet_path
    clip_path = _os.path.join(_bridge_dir, clip_path) if not _os.path.isabs(clip_path) else clip_path

    # comfy_bridge.load_viggle_pipeline is the generic Qwen-Image-2.1 native
    # loader (safetensors UNet through the stock UNETLoader, safetensors
    # clip, VAE): the turbo checkpoint needs no LoRA and no separate mmproj
    # (the int8 clip ships the vision tower in the same file).
    from comfy_bridge import load_viggle_pipeline as _comfy_load_qwen21, colorize_qwen21_turbo as _colorize_turbo

    _auto = _os.environ.get("COMFY_AUTO_DOWNLOAD", "1") == "1"
    _vae_local = _os.path.join(_bridge_dir, "models", "vae", vae_name)
    _files = {
        # unet: unet_hf_name overrides the assumed remote path when the file
        # is not stored under the Comfy-Org-style "diffusion_models/" folder.
        "unet": (unet_path, hf_unet, unet_hf_name or ("diffusion_models/" + _os.path.basename(unet_path))),
        "clip": (clip_path, hf_clip, "text_encoders/" + _os.path.basename(clip_path)),
        "vae":  (_vae_local, hf_vae,  "vae/" + vae_name),
    }
    if _auto:
        _ensure_models(_files)

    pipeline = _comfy_load_qwen21(unet_path, clip_path, vae_name=vae_name)
    pipeline["_model_type"] = "qwen21-turbo"
    pipeline["_colorize_fn"] = _colorize_turbo
    return pipeline


def load_flux2_pipeline(model_name: str, unet_path: str, clip_path: str,
                        lora_path: str = "", vae_name: str = "flux2-vae.safetensors",
                        guidance: float = 4.0,
                        hf_unet="unsloth/FLUX.2-dev-GGUF",
                        hf_clip="Comfy-Org/flux2-dev",
                        hf_vae="Comfy-Org/flux2-dev",
                        hf_lora="Comfy-Org/flux2-dev",
                        unet_hf_name: str = "", clip_hf_name: str = "",
                        vae_hf_name: str = "", lora_hf_name: str = ""):
    """
    Load the FLUX.2 pipeline (Flux.2-dev transformer + Mistral-3 text
    encoder + Flux2 VAE, with the FLUX.2-Turbo LoRA applied at runtime).

    unet_path may be a GGUF quant (the Flux.2-dev quants under models/unet)
    or a safetensors checkpoint (the Comfy-Org fp8-mixed repack, for cards
    with the VRAM for it). The family is entirely ComfyUI-native -- no diffusers
    pipeline, no mmproj: the B&W frame reaches the transformer as a VAE
    reference latent, so the text encoder is prompt-only.

    guidance : the FluxGuidance value of the reference workflow (Flux.2-dev
    has embedded guidance; CFG stays off -- one sampling pass, like the other
    turbo-style families). Carried on the pipeline dict and used by phase A of
    the split flow, so it is baked into the cached conditioning.

    *_hf_name : optional overrides of the assumed HuggingFace paths. The
    defaults follow the Comfy-Org "split_files/<kind>/" layout (and the repo
    root for GGUF UNets); set them when a config points at a differently
    organized mirror.
    """
    if model_name != "flux2":
        return None

    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    import os as _os
    _bridge_dir = _os.path.join(_os.path.dirname(__file__), "comfy_bridge")
    unet_path = _os.path.join(_bridge_dir, unet_path) if not _os.path.isabs(unet_path) else unet_path
    clip_path = _os.path.join(_bridge_dir, clip_path) if not _os.path.isabs(clip_path) else clip_path
    if lora_path and not _os.path.isabs(lora_path):
        lora_path = _os.path.join(_bridge_dir, lora_path)

    from comfy_bridge import (load_flux2_pipeline as _comfy_load_flux2,
                              colorize_flux2 as _colorize_flux2)

    _auto = _os.environ.get("COMFY_AUTO_DOWNLOAD", "1") == "1"
    _vae_local = _os.path.join(_bridge_dir, "models", "vae", vae_name)
    _files = {
        # unet: GGUF quants live at the root of their repo, the Comfy-Org
        # safetensors repack under split_files/diffusion_models/ -- same
        # split-by-format convention the viggle loader uses.
        "unet": (unet_path, hf_unet, unet_hf_name or (
            _os.path.basename(unet_path) if unet_path.lower().endswith(".gguf")
            else "split_files/diffusion_models/" + _os.path.basename(unet_path))),
        "clip": (clip_path, hf_clip, clip_hf_name or ("split_files/text_encoders/" + _os.path.basename(clip_path))),
        "vae":  (_vae_local, hf_vae, vae_hf_name or ("split_files/vae/" + vae_name)),
        "lora": (lora_path, hf_lora, lora_hf_name or ("split_files/loras/" + _os.path.basename(lora_path))) if lora_path else None,
    }
    if _auto:
        _ensure_models(_files)

    pipeline = _comfy_load_flux2(unet_path, clip_path, vae_name=vae_name, lora_path=lora_path)
    pipeline["_model_type"] = "flux2"
    pipeline["_colorize_fn"] = _colorize_flux2
    try:
        pipeline["_guidance"] = float(guidance)
    except (TypeError, ValueError):
        pipeline["_guidance"] = 4.0
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

def colorize_image(pipe, img: Image, prompt:str, steps: int = 2, seed: int=42, enhance_prompt: bool = False, resolution: int = None) -> Image:
    # LongCat pipeline (dict with _model_type marker)
    if isinstance(pipe, dict) and pipe.get("_model_type") == "longcat-gguf":
        _colorize_fn = pipe.get("_colorize_fn")
        return _colorize_fn(pipe, img, prompt=prompt, steps=steps, seed=seed)

    # Qwen-Image-2.1-Turbo pipeline (dict with _model_type marker)
    if isinstance(pipe, dict) and pipe.get("_model_type") == "qwen21-turbo":
        _colorize_fn = pipe.get("_colorize_fn")
        kwargs = {"resolution": resolution} if resolution is not None else {}
        return _colorize_fn(pipe, img, prompt=prompt, steps=steps, seed=seed, **kwargs)

    # FLUX.2 pipeline (dict with _model_type marker)
    if isinstance(pipe, dict) and pipe.get("_model_type") == "flux2":
        _colorize_fn = pipe.get("_colorize_fn")
        kwargs = {"resolution": resolution} if resolution is not None else {}
        return _colorize_fn(pipe, img, prompt=prompt, steps=steps, seed=seed, **kwargs)

    # Qwen-Image-2.1 + Viggle-Turbo pipeline (dict with _model_type marker)
    if isinstance(pipe, dict) and pipe.get("_model_type") == "qwen21-viggle":
        _colorize_fn = pipe.get("_colorize_fn")
        kwargs = {"resolution": resolution} if resolution is not None else {}
        return _colorize_fn(pipe, img, prompt=prompt, steps=steps, seed=seed, enhance_prompt=enhance_prompt, **kwargs)

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

# ---------------------------------------------------------------------------
# Unsharp-mask input pre-filter (opt-in, used by the colorization paths)
# ---------------------------------------------------------------------------

# Fixed amount/threshold (Pillow `percent` / `threshold`), mirroring the
# reference settings validated on sources whose film grain stopped the model
# from colorizing (GIMP: amount 0.50, threshold 0). Only the radius is a
# client parameter; radius <= 0 disables the filter.
USM_AMOUNT = 50
USM_THRESHOLD = 0


def apply_input_usm(img: Image.Image, usm_radius: float = 0.0) -> Image.Image:
    """Optional Unsharp Mask pre-filter for a colorization input.

    No-op when usm_radius <= 0 (or not numeric); the radius is clamped to 50
    so a hand-edited client cannot stall the pipeline.
    """
    try:
        radius = float(usm_radius)
    except (TypeError, ValueError):
        return img
    if not radius > 0:
        return img
    from PIL import ImageFilter
    return img.filter(ImageFilter.UnsharpMask(
        radius=min(radius, 50.0), percent=USM_AMOUNT, threshold=USM_THRESHOLD))


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

def process_image(input_path, output_path, pipe, prompt: str = None, img_size:int = 0, steps: int = 2, log_fn=None, enhance_prompt: bool = False, usm_radius: float = 0.0) -> float:

    if output_path.exists():
        if log_fn is not None:
            log_fn(f'ℹ️ Image: "{output_path}" already colorized')
        return 0

    original = Image.open(input_path).convert("RGB")

    if is_image_dark(original, threshold=9):
        if log_fn is not None:
            log_fn(f'⚠️ Image: "{input_path}" too dark to be colorized')
        return 0

    t_elapsed = process_image_standard(pipe, original, output_path, prompt, img_size=img_size, steps=steps, enhance_prompt=enhance_prompt, usm_radius=usm_radius)

    if log_fn is not None:
        log_fn(f"✅ colored: {output_path} [{t_elapsed:.2f} sec.]")

    return t_elapsed

def process_single_image(pipe, img_path: Path, output_dir: Path, prompt: str, steps: int = 2, enhance_prompt: bool = False, usm_radius: float = 0.0) -> float:
    """Fallback for odd-numbered batches."""
    out_path = output_dir / (img_path.stem + ".jpg")
    original = Image.open(img_path).convert("RGB")

    if is_image_dark(original, threshold=9):
        return 0

    return process_image_standard(pipe, original, out_path, prompt, steps=steps, enhance_prompt=enhance_prompt, usm_radius=usm_radius)

def process_image_standard(pipe, original, output_path, prompt, img_size: int = 1024, steps: int = 2, enhance_prompt: bool = False, usm_radius: float = 0.0) -> float:

    bw = ImageEnhance.Color(original).enhance(0.0)
    bw = apply_input_usm(bw, usm_radius)
    orig_size = original.size

    if img_size == 0:
        bw_lowres = bw
    else:
        bw_lowres = resize_long_side(bw, img_size)

    t_start = time.perf_counter()
    colorized_lowres = colorize_image(pipe, bw_lowres, prompt, steps, enhance_prompt=enhance_prompt)
    t_end = time.perf_counter()

    colorized_upscaled = upscale_with_lanczos(colorized_lowres, orig_size)
    colorized_upscaled.save(output_path)

    return t_end - t_start


# ----------------------------
# Split colorize (phase A/B): cached text-encoder conditioning
# ----------------------------

def _te_manifest_key(model_config, prompt, resolution, img_size, enhance_prompt, usm_radius: float = 0.0):
    """The cache-key fields: a manifest is only valid when all of them match."""
    return {
        "model_config": model_config,
        "prompt": prompt,
        "resolution": resolution,
        "img_size": img_size,
        "enhance_prompt": bool(enhance_prompt),
        "usm_radius": round(float(usm_radius or 0.0), 3),
    }


def _te_manifest_load(te_dir, key):
    """(manifest, cached entries) when the manifest exists and its key matches,
    else (None, {}) -- a cache produced for other settings is ignored."""
    path = os.path.join(te_dir, "manifest.json")
    if not os.path.isfile(path):
        return None, {}
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    except Exception:
        return None, {}
    old.setdefault("usm_radius", 0.0)   # pre-USM manifests: filter was off
    if any(old.get(k) != v for k, v in key.items()):
        return None, {}
    return old, dict(old.get("frames") or {})


def _te_manifest_save(te_dir, key, frames):
    manifest = {"format": 1, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), **key,
                "frames": frames}
    path = os.path.join(te_dir, "manifest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _split_family(pipe):
    """The family marker of a loaded pipeline ("" for non-dict pipelines).

    The split flows (the single-frame encode_frame_te / colorize_frame_from_te
    and the paired encode_pair_te / colorize_pair_from_te) are shared by the
    cached-TE families: qwen21-viggle and qwen21-turbo use the viggle
    conditioning, flux2 uses its own (prompt-only text encoder + reference
    latent), while the 2511 family has its own edit-conditioning functions.
    """
    if isinstance(pipe, dict):
        return pipe.get("_model_type", "") or ""
    return ""


def encode_frame_te(pipe, img_path, te_dir, stem, prompt, resolution: int = 1024,
                    img_size: int = 0, enhance_prompt: bool = False,
                    first: bool = False, model_config: str = "",
                    usm_radius: float = 0.0) -> dict:
    """Phase A, single frame: encode + cache the conditioning of one image
    under te_dir/<stem>.safetensors. first=True drops every loaded model
    before anything else (so the TE + VAE start from a clean VRAM even when
    this frame turns out to be cached); frames already cached for the same
    prompt/settings are skipped (resume).

    The preprocessing mirrors process_image_standard() (dark check,
    desaturate, optional resize); the conditioning comes from the family's own
    encoder -- comfy_bridge.encode_viggle_conditioning() for the qwen21
    split-TE families, comfy_bridge.encode_flux2_conditioning() for flux2.
    Returns {"ok", "skipped", "elapsed", "msg"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase A wants the TE + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    os.makedirs(te_dir, exist_ok=True)
    key = _te_manifest_key(model_config, prompt, resolution, img_size, enhance_prompt, usm_radius)
    _, cached = _te_manifest_load(te_dir, key)

    src = str(img_path)
    te_path = os.path.join(te_dir, stem + ".safetensors")
    mtime = os.path.getmtime(src)
    prev = cached.get(stem)
    if prev and prev.get("mtime") == mtime and os.path.isfile(te_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": ""}

    t0 = time.perf_counter()
    original = Image.open(src).convert("RGB")
    if is_image_dark(original, threshold=9):
        logger.info("encode_frame_te: too dark, skipped: %s", os.path.basename(src))
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": "too dark"}

    bw = ImageEnhance.Color(original).enhance(0.0)
    bw = apply_input_usm(bw, usm_radius)
    orig_w, orig_h = original.size
    img_in = resize_long_side(bw, img_size) if img_size > 0 else bw

    family = _split_family(pipe)
    if family == "flux2":
        # flux2: prompt-only text encoder + the frame as a VAE reference
        # latent; no prompt enhancer in this family
        res = comfy_bridge.encode_flux2_conditioning(
            pipe, img_in, prompt, resolution=resolution)
        _save = comfy_bridge.save_flux2_conditioning
    else:
        res = comfy_bridge.encode_viggle_conditioning(
            pipe, img_in, prompt, resolution=resolution,
            enhance_prompt=enhance_prompt)
        _save = comfy_bridge.save_viggle_conditioning
    _save(
        te_path, res["conditioning"], res["latent"],
        prompt=res["prompt"], prompt_original=prompt,
        meta={"orig_width": orig_w, "orig_height": orig_h,
              "source": os.path.basename(src), "model_config": model_config})

    cached[stem] = {"mtime": mtime, "te": os.path.basename(te_path)}
    _te_manifest_save(te_dir, key, cached)
    elapsed = time.perf_counter() - t0
    logger.info("encode_frame_te: %s", os.path.basename(src))
    return {"ok": True, "skipped": False, "elapsed": elapsed, "msg": ""}


def colorize_frame_from_te(pipe, te_dir, stem, out_path, steps: int = 2, seed: int = 42,
                           first: bool = False) -> dict:
    """Phase B, single frame: sample + decode one cached conditioning into
    out_path, with the same post-processing as the live path (LANCZOS upscale
    to the original size, PIL default save). first=True drops every loaded
    model before anything else (the UNet + VAE start from a clean VRAM even
    when this frame turns out to be skipped); an existing output is skipped
    (resume). Returns {"ok", "skipped", "elapsed", "msg"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase B wants the UNet + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    out_path = str(out_path)
    if os.path.isfile(out_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": ""}

    te_path = os.path.join(te_dir, stem + ".safetensors")
    if not os.path.isfile(te_path):
        # never encoded (e.g. a dark frame) or the chunk cache was already
        # dropped: nothing to do here, not an error
        return {"ok": True, "skipped": True, "elapsed": 0.0,
                "msg": "no conditioning cached"}

    t0 = time.perf_counter()
    if _split_family(pipe) == "flux2":
        loaded = comfy_bridge.load_flux2_conditioning(te_path)
        colorized_lowres = comfy_bridge.colorize_flux2_from_conditioning(
            pipe, loaded["conditioning"], loaded["latent"], steps=steps, seed=seed)
    else:
        loaded = comfy_bridge.load_viggle_conditioning(te_path)
        colorized_lowres = comfy_bridge.colorize_viggle_from_conditioning(
            pipe, loaded["conditioning"], loaded["latent"], steps=steps, seed=seed)
    meta = loaded["meta"]
    try:
        orig_size = (int(meta.get("orig_width")), int(meta.get("orig_height")))
    except (TypeError, ValueError):
        orig_size = colorized_lowres.size
    colorized_upscaled = upscale_with_lanczos(colorized_lowres, orig_size)
    colorized_upscaled.save(out_path)
    elapsed = time.perf_counter() - t0
    logger.info("colorize_frame_from_te: %s", stem)
    return {"ok": True, "skipped": False, "elapsed": elapsed, "msg": ""}


def encode_frames_te(pipe, in_dir, out_dir, prompt, resolution: int = 1024, img_size: int = 0,
                     enhance_prompt: bool = False, model_config: str = "",
                     usm_radius: float = 0.0) -> dict:
    """Phase A batch: loop encode_frame_te over the images in in_dir (one
    .safetensors per frame + manifest.json). Kept for whole-batch callers; the
    GUI drives encode_frame_te frame by frame (chunked) so progress and cancel
    stay per-frame. Returns {"ok", "count", "skipped", "elapsed", "msg"}.
    """
    import logging

    logger = logging.getLogger(__name__)

    os.makedirs(out_dir, exist_ok=True)
    names = sorted(f for f in os.listdir(in_dir)
                   if os.path.splitext(f)[1].lower() in (".png", ".jpg", ".jpeg"))
    if not names:
        return {"ok": False, "count": 0, "skipped": 0, "elapsed": 0.0,
                "msg": f"no images found in {in_dir}"}

    t0 = time.perf_counter()
    count = skipped = 0
    for i, name in enumerate(names):
        stem = os.path.splitext(name)[0]
        res = encode_frame_te(pipe, os.path.join(in_dir, name), out_dir, stem,
                              prompt, resolution=resolution, img_size=img_size,
                              enhance_prompt=enhance_prompt, first=(i == 0),
                              model_config=model_config, usm_radius=usm_radius)
        if not res.get("ok"):
            logger.warning("encode_frames_te: %s: %s", name, res.get("msg"))
            continue
        if res.get("skipped"):
            skipped += 1
        else:
            count += 1
    elapsed = time.perf_counter() - t0
    return {"ok": True, "count": count, "skipped": skipped, "elapsed": elapsed, "msg": ""}


def colorize_frames_from_te(pipe, te_dir, out_dir, steps: int = 2, seed: int = 42) -> dict:
    """Phase B batch: loop colorize_frame_from_te over the frames of the cache
    (manifest entries, or the .safetensors files when the manifest is absent).
    Kept for whole-batch callers. Returns
    {"ok", "count", "skipped", "elapsed", "msg"}.
    """
    import logging

    logger = logging.getLogger(__name__)

    frames = {}
    manifest_path = os.path.join(te_dir, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                frames = dict(json.load(fh).get("frames") or {})
        except Exception:
            frames = {}
    if not frames and os.path.isdir(te_dir):
        frames = {os.path.splitext(f)[0]: {}
                  for f in sorted(os.listdir(te_dir)) if f.endswith(".safetensors")}
    if not frames:
        return {"ok": False, "count": 0, "skipped": 0, "elapsed": 0.0,
                "msg": f"no cached conditioning in {te_dir}"}

    os.makedirs(out_dir, exist_ok=True)
    t0 = time.perf_counter()
    count = skipped = 0
    for i, stem in enumerate(sorted(frames)):
        res = colorize_frame_from_te(pipe, te_dir, stem,
                                     os.path.join(out_dir, stem + ".jpg"),
                                     steps=steps, seed=seed, first=(i == 0))
        if not res.get("ok"):
            logger.warning("colorize_frames_from_te: %s: %s", stem, res.get("msg"))
            continue
        if res.get("skipped"):
            skipped += 1
        else:
            count += 1
    elapsed = time.perf_counter() - t0
    return {"ok": True, "count": count, "skipped": skipped, "elapsed": elapsed, "msg": ""}


# ----------------------------
# Split colorize (phase A/B) for the Qwen-Image-Edit 2511 family (gguf-qwen):
# the same cached-conditioning scheme as the viggle flow above, but the
# conditioning is the edit node's (context + reference latent + start latent,
# ~21 MB/frame) and the working size comes from FluxKontextImageScale instead
# of a fixed resolution -- see comfy_bridge.encode_edit_conditioning().
# ----------------------------

def encode_frame_edit(pipe, img_path, te_dir, stem, prompt, img_size: int = 0,
                      first: bool = False, model_config: str = "",
                      usm_radius: float = 0.0) -> dict:
    """Phase A, single frame (edit family): encode + cache the conditioning of
    one image under te_dir/<stem>.safetensors. Same contract as
    encode_frame_te(): first=True drops the loaded models before anything
    else (so the TE + VAE start from a clean VRAM even when this frame turns
    out to be cached); frames already cached for the same prompt/settings are
    skipped (resume). Returns {"ok", "skipped", "elapsed", "msg"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase A wants the TE + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    os.makedirs(te_dir, exist_ok=True)
    # resolution is not a parameter of the edit path (FluxKontextImageScale
    # decides the working size from the image): 0 marks the edit format.
    key = _te_manifest_key(model_config, prompt, 0, img_size, False, usm_radius)
    _, cached = _te_manifest_load(te_dir, key)

    src = str(img_path)
    te_path = os.path.join(te_dir, stem + ".safetensors")
    mtime = os.path.getmtime(src)
    prev = cached.get(stem)
    if prev and prev.get("mtime") == mtime and os.path.isfile(te_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": ""}

    t0 = time.perf_counter()
    original = Image.open(src).convert("RGB")
    if is_image_dark(original, threshold=9):
        logger.info("encode_frame_edit: too dark, skipped: %s", os.path.basename(src))
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": "too dark"}

    bw = ImageEnhance.Color(original).enhance(0.0)
    bw = apply_input_usm(bw, usm_radius)
    orig_w, orig_h = original.size
    img_in = resize_long_side(bw, img_size) if img_size > 0 else bw

    res = comfy_bridge.encode_edit_conditioning(pipe, img_in, prompt)
    comfy_bridge.save_edit_conditioning(
        te_path, res["conditioning"], res["latent"], prompt=prompt,
        meta={"orig_width": orig_w, "orig_height": orig_h,
              "source": os.path.basename(src), "model_config": model_config})

    cached[stem] = {"mtime": mtime, "te": os.path.basename(te_path)}
    _te_manifest_save(te_dir, key, cached)
    elapsed = time.perf_counter() - t0
    logger.info("encode_frame_edit: %s", os.path.basename(src))
    return {"ok": True, "skipped": False, "elapsed": elapsed, "msg": ""}


def colorize_frame_edit_from_te(pipe, te_dir, stem, out_path, steps: int = 4,
                                seed: int = 42, first: bool = False) -> dict:
    """Phase B, single frame (edit family): sample + decode one cached
    conditioning into out_path, with the same post-processing as the live
    path (LANCZOS upscale to the original size, PIL default save). Same
    contract as colorize_frame_from_te(). Returns
    {"ok", "skipped", "elapsed", "msg"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase B wants the UNet + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    out_path = str(out_path)
    if os.path.isfile(out_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": ""}

    te_path = os.path.join(te_dir, stem + ".safetensors")
    if not os.path.isfile(te_path):
        # never encoded (e.g. a dark frame) or the chunk cache was already
        # dropped: nothing to do here, not an error
        return {"ok": True, "skipped": True, "elapsed": 0.0,
                "msg": "no conditioning cached"}

    t0 = time.perf_counter()
    try:
        loaded = comfy_bridge.load_edit_conditioning(te_path)
    except ValueError as exc:
        # a conditioning of the other family left in this folder (same stem):
        # skip instead of sampling a mismatched structure
        logger.warning("colorize_frame_edit_from_te: %s: %s", stem, exc)
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": str(exc)}

    colorized_lowres = comfy_bridge.colorize_edit_from_conditioning(
        pipe, loaded["conditioning"], loaded["latent"], steps=steps, seed=seed)
    meta = loaded["meta"]
    try:
        orig_size = (int(meta.get("orig_width")), int(meta.get("orig_height")))
    except (TypeError, ValueError):
        orig_size = colorized_lowres.size
    colorized_upscaled = upscale_with_lanczos(colorized_lowres, orig_size)
    colorized_upscaled.save(out_path)
    elapsed = time.perf_counter() - t0
    logger.info("colorize_frame_edit_from_te: %s", stem)
    return {"ok": True, "skipped": False, "elapsed": elapsed, "msg": ""}


# ----------------------------
# Split colorize, PAIRED mode (config key "fast_split_TE"): two frames are
# merged side by side *before* the text encoder and the decoded canvas is
# split back *after* the transformer -- one TE pass and one sampling pass per
# two frames. Available to every split-TE family (the qwen21-viggle /
# qwen21-turbo conditioning format and the qwen-2511 edit one); a model opts
# in with "fast_split_TE": true in its config/*.json (the GUI reads the flag
# and drives these functions through their RPC twins).
# ----------------------------

PAIR_GAP_PX = 16  # neutral separator between the two frames of a pair


def _pair_canvas_frame(orig, img_size, usm_radius):
    """One frame of a pair: desaturate, optional USM pre-filter, optional
    long-side resize -- the same prologue process_image_standard() uses."""
    bw = ImageEnhance.Color(orig).enhance(0.0)
    bw = apply_input_usm(bw, usm_radius)
    return resize_long_side(bw, img_size) if img_size > 0 else bw


def _pair_merge_canvas(img1_path, img2_path, img_size=0, usm_radius=0.0,
                       gap_px=PAIR_GAP_PX):
    """Build the paired conditioning canvas from one or two frames.

    Both frames are desaturated (and optionally USM-filtered), padded to the
    same height with neutral gray and merged side by side. A dark frame
    degrades the pair to the surviving frame alone (the same semantics as
    process_image_pair()); a fully dark pair conditions nothing.

    Returns {"mode": "pair"|"single"|"dark", "image": PIL|None, "geom": dict}.
    The geometry travels in the conditioning metadata: it is what phase B uses
    to map the decoded canvas back to the two frames.
    """
    orig1 = Image.open(img1_path).convert("RGB")
    dark1 = is_image_dark(orig1, threshold=9)

    img2_path = str(img2_path or "")
    orig2 = None
    dark2 = False
    if img2_path and os.path.isfile(img2_path):
        orig2 = Image.open(img2_path).convert("RGB")
        dark2 = is_image_dark(orig2, threshold=9)

    if dark1 and (orig2 is None or dark2):
        return {"mode": "dark", "image": None, "geom": {}}

    if dark1 or dark2 or orig2 is None:
        # one usable frame: condition that one alone; `which` keeps the
        # mapping to the pair's two output paths
        which = 2 if dark1 else 1
        src = orig2 if dark1 else orig1
        return {"mode": "single", "image": _pair_canvas_frame(src, img_size, usm_radius),
                "geom": {"mode": "single", "which": which,
                         "ow": src.size[0], "oh": src.size[1]}}

    bw1 = _pair_canvas_frame(orig1, img_size, usm_radius)
    bw2 = _pair_canvas_frame(orig2, img_size, usm_radius)
    if bw1.height != bw2.height:
        target_h = max(bw1.height, bw2.height)
        bw1 = ImageOps.pad(bw1, (bw1.width, target_h), color=(127, 127, 127))
        bw2 = ImageOps.pad(bw2, (bw2.width, target_h), color=(127, 127, 127))
    merged = merge_two_images_with_gap(bw1, bw2, gap_px=gap_px)
    return {"mode": "pair", "image": merged,
            "geom": {"mode": "pair", "w1": bw1.width, "w2": bw2.width,
                     "h": merged.height, "gap": int(gap_px),
                     "ow1": orig1.size[0], "oh1": orig1.size[1],
                     "ow2": orig2.size[0], "oh2": orig2.size[1]}}


def _pair_geometry_peek(te_path):
    """The pair geometry recorded in a conditioning's metadata (None when the
    file is not a paired conditioning). Reads the safetensors metadata only --
    no tensors, so it is cheap enough for a resume check."""
    from safetensors import safe_open

    with safe_open(str(te_path), framework="pt", device="cpu") as f:
        meta = dict(f.metadata() or {})
    raw = meta.get("pair_geometry")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _pair_outputs(geom, out1_path, out2_path):
    """The output paths the geometry implies: one for a degraded pair (the
    surviving frame), two for a merged pair."""
    if geom.get("mode") == "single":
        path = out2_path if int(geom.get("which", 1)) == 2 else out1_path
        return [str(path)] if path else []
    return [str(p) for p in (out1_path, out2_path) if p]


def _pair_split_save(colorized, geom, out1_path, out2_path):
    """Split one decoded pair canvas back into its frames, upscale each to its
    original size and save it (the same two-step geometry the old pair flow
    used: canvas -> merged working size -> per-frame original). Returns the
    list of written paths."""
    if geom.get("mode") == "single":
        path = out2_path if int(geom.get("which", 1)) == 2 else out1_path
        if not path:
            raise ValueError("_pair_split_save: missing output path for the single frame")
        upscale_with_lanczos(colorized, (int(geom["ow"]), int(geom["oh"]))).save(path)
        return [str(path)]

    if not (out1_path and out2_path):
        raise ValueError("_pair_split_save: a merged pair needs both output paths")
    merged_w = int(geom["w1"]) + int(geom["gap"]) + int(geom["w2"])
    merged = upscale_with_lanczos(colorized, (merged_w, int(geom["h"])))
    left, right = split_merged_output(merged, int(geom["w1"]), gap_px=int(geom["gap"]))
    upscale_with_lanczos(left, (int(geom["ow1"]), int(geom["oh1"]))).save(out1_path)
    upscale_with_lanczos(right, (int(geom["ow2"]), int(geom["oh2"]))).save(out2_path)
    return [str(out1_path), str(out2_path)]


def encode_pair_te(pipe, in1_path, in2_path, te_dir, stem, prompt, resolution: int = 1024,
                   img_size: int = 0, enhance_prompt: bool = False, first: bool = False,
                   model_config: str = "", usm_radius: float = 0.0) -> dict:
    """Phase A, one pair (qwen21-viggle / qwen21-turbo / flux2 conditioning
    formats): condition the merged canvas of one or two frames with a single
    text-encoder pass and cache it under te_dir/<stem>.safetensors, geometry
    included.

    For flux2 the canvas is the VAE reference latent of a prompt-only
    conditioning (encode_flux2_conditioning), exactly as the single-frame
    flow; the enhancer flag does not apply to that family.

    Same contract as encode_frame_te(): first=True drops the loaded models
    before anything else; a pair already cached for the same prompt/settings is
    skipped (resume). in2_path may be empty (an odd trailing frame) or point
    to a dark frame: the pair degrades to a single-frame conditioning.
    Returns {"ok", "skipped", "elapsed", "msg"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase A wants the TE + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    os.makedirs(te_dir, exist_ok=True)
    key = dict(_te_manifest_key(model_config, prompt, resolution, img_size,
                                enhance_prompt, usm_radius), pair=True)
    _, cached = _te_manifest_load(te_dir, key)

    src = str(in1_path)
    in2_path = str(in2_path or "")
    mtimes = [os.path.getmtime(src)]
    if in2_path and os.path.isfile(in2_path):
        mtimes.append(os.path.getmtime(in2_path))
    else:
        in2_path = ""
    mtime = max(mtimes)

    te_path = os.path.join(te_dir, stem + ".safetensors")
    prev = cached.get(stem)
    if prev and prev.get("mtime") == mtime and os.path.isfile(te_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": ""}

    t0 = time.perf_counter()
    canvas = _pair_merge_canvas(src, in2_path, img_size=img_size, usm_radius=usm_radius)
    if canvas["mode"] == "dark":
        logger.info("encode_pair_te: both frames too dark, skipped: %s", stem)
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": "too dark"}

    if _split_family(pipe) == "flux2":
        # flux2: prompt-only text encoder + the canvas as VAE reference
        # latent; no prompt enhancer in this family
        res = comfy_bridge.encode_flux2_conditioning(
            pipe, canvas["image"], prompt, resolution=resolution)
        _save = comfy_bridge.save_flux2_conditioning
    else:
        res = comfy_bridge.encode_viggle_conditioning(
            pipe, canvas["image"], prompt, resolution=resolution,
            enhance_prompt=enhance_prompt)
        _save = comfy_bridge.save_viggle_conditioning
    _save(
        te_path, res["conditioning"], res["latent"],
        prompt=res["prompt"], prompt_original=prompt,
        meta={"source": os.path.basename(src), "model_config": model_config,
              "pair_geometry": json.dumps(canvas["geom"], separators=(",", ":"))})

    cached[stem] = {"mtime": mtime, "te": os.path.basename(te_path)}
    _te_manifest_save(te_dir, key, cached)
    elapsed = time.perf_counter() - t0
    logger.info("encode_pair_te: %s (mode=%s)", stem, canvas["mode"])
    return {"ok": True, "skipped": False, "elapsed": elapsed, "msg": ""}


def colorize_pair_from_te(pipe, te_dir, stem, out1_path, out2_path="", steps: int = 2,
                          seed: int = 42, first: bool = False) -> dict:
    """Phase B, one pair (qwen21-viggle / qwen21-turbo / flux2 conditioning
    formats): sample + decode the cached pair canvas, split it back into the
    frames and save each at its original size (one output for a degraded pair).
    Same contract as colorize_frame_from_te(): first=True drops the loaded
    models first; a pair whose expected outputs all exist is skipped. Returns
    {"ok", "skipped", "elapsed", "msg", "written"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase B wants the UNet + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    te_path = os.path.join(te_dir, stem + ".safetensors")
    if not os.path.isfile(te_path):
        # never encoded (e.g. a fully dark pair) or the chunk cache was already
        # dropped: nothing to do here, not an error
        return {"ok": True, "skipped": True, "elapsed": 0.0, "written": [],
                "msg": "no conditioning cached"}

    geom = _pair_geometry_peek(te_path)
    if geom is None:
        return {"ok": False, "skipped": False, "elapsed": 0.0, "written": [],
                "msg": "colorize_pair_from_te: not a paired conditioning"}
    outs = _pair_outputs(geom, str(out1_path or ""), str(out2_path or ""))
    if not outs:
        return {"ok": False, "skipped": False, "elapsed": 0.0, "written": [],
                "msg": "colorize_pair_from_te: missing output path"}
    if all(os.path.isfile(p) for p in outs):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "written": [], "msg": ""}

    t0 = time.perf_counter()
    try:
        if _split_family(pipe) == "flux2":
            loaded = comfy_bridge.load_flux2_conditioning(te_path)
            colorized_lowres = comfy_bridge.colorize_flux2_from_conditioning(
                pipe, loaded["conditioning"], loaded["latent"], steps=steps, seed=seed)
        else:
            loaded = comfy_bridge.load_viggle_conditioning(te_path)
            colorized_lowres = comfy_bridge.colorize_viggle_from_conditioning(
                pipe, loaded["conditioning"], loaded["latent"], steps=steps, seed=seed)
    except ValueError as exc:
        # a conditioning of another family left in this folder (same stem):
        # skip instead of sampling a mismatched structure
        logger.warning("colorize_pair_from_te: %s: %s", stem, exc)
        return {"ok": True, "skipped": True, "elapsed": 0.0, "written": [],
                "msg": str(exc)}

    written = _pair_split_save(colorized_lowres, geom, out1_path, out2_path)
    elapsed = time.perf_counter() - t0
    logger.info("colorize_pair_from_te: %s (mode=%s, %d out)",
                stem, geom.get("mode"), len(written))
    return {"ok": True, "skipped": False, "elapsed": elapsed,
            "written": written, "msg": ""}


def encode_pair_edit(pipe, in1_path, in2_path, te_dir, stem, prompt, img_size: int = 0,
                     first: bool = False, model_config: str = "",
                     usm_radius: float = 0.0) -> dict:
    """Phase A, one pair of the qwen-2511 edit family: the same scheme as
    encode_pair_te(), but the conditioning is the edit node's (context +
    reference latent + start latent) -- see encode_edit_conditioning().
    Returns {"ok", "skipped", "elapsed", "msg"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase A wants the TE + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    os.makedirs(te_dir, exist_ok=True)
    # resolution is not a parameter of the edit path: 0 marks the edit format
    # (same marker the single-frame edit flow uses)
    key = dict(_te_manifest_key(model_config, prompt, 0, img_size, False, usm_radius),
               pair=True)
    _, cached = _te_manifest_load(te_dir, key)

    src = str(in1_path)
    in2_path = str(in2_path or "")
    mtimes = [os.path.getmtime(src)]
    if in2_path and os.path.isfile(in2_path):
        mtimes.append(os.path.getmtime(in2_path))
    else:
        in2_path = ""
    mtime = max(mtimes)

    te_path = os.path.join(te_dir, stem + ".safetensors")
    prev = cached.get(stem)
    if prev and prev.get("mtime") == mtime and os.path.isfile(te_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": ""}

    t0 = time.perf_counter()
    canvas = _pair_merge_canvas(src, in2_path, img_size=img_size, usm_radius=usm_radius)
    if canvas["mode"] == "dark":
        logger.info("encode_pair_edit: both frames too dark, skipped: %s", stem)
        return {"ok": True, "skipped": True, "elapsed": 0.0, "msg": "too dark"}

    res = comfy_bridge.encode_edit_conditioning(pipe, canvas["image"], prompt)
    comfy_bridge.save_edit_conditioning(
        te_path, res["conditioning"], res["latent"], prompt=prompt,
        meta={"source": os.path.basename(src), "model_config": model_config,
              "pair_geometry": json.dumps(canvas["geom"], separators=(",", ":"))})

    cached[stem] = {"mtime": mtime, "te": os.path.basename(te_path)}
    _te_manifest_save(te_dir, key, cached)
    elapsed = time.perf_counter() - t0
    logger.info("encode_pair_edit: %s (mode=%s)", stem, canvas["mode"])
    return {"ok": True, "skipped": False, "elapsed": elapsed, "msg": ""}


def colorize_pair_edit_from_te(pipe, te_dir, stem, out1_path, out2_path="",
                               steps: int = 4, seed: int = 42,
                               first: bool = False) -> dict:
    """Phase B, one pair of the qwen-2511 edit family: sample + decode the
    cached edit conditioning, split the canvas back and save each frame at its
    original size. Same contract as colorize_pair_from_te(). Returns
    {"ok", "skipped", "elapsed", "msg", "written"}.
    """
    import logging

    import comfy.model_management

    import comfy_bridge

    logger = logging.getLogger(__name__)

    if first:
        # phase B wants the UNet + VAE alone in VRAM: start from a clean slate
        comfy.model_management.unload_all_models()

    te_path = os.path.join(te_dir, stem + ".safetensors")
    if not os.path.isfile(te_path):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "written": [],
                "msg": "no conditioning cached"}

    geom = _pair_geometry_peek(te_path)
    if geom is None:
        return {"ok": False, "skipped": False, "elapsed": 0.0, "written": [],
                "msg": "colorize_pair_edit_from_te: not a paired conditioning"}
    outs = _pair_outputs(geom, str(out1_path or ""), str(out2_path or ""))
    if not outs:
        return {"ok": False, "skipped": False, "elapsed": 0.0, "written": [],
                "msg": "colorize_pair_edit_from_te: missing output path"}
    if all(os.path.isfile(p) for p in outs):
        return {"ok": True, "skipped": True, "elapsed": 0.0, "written": [], "msg": ""}

    t0 = time.perf_counter()
    try:
        loaded = comfy_bridge.load_edit_conditioning(te_path)
    except ValueError as exc:
        logger.warning("colorize_pair_edit_from_te: %s: %s", stem, exc)
        return {"ok": True, "skipped": True, "elapsed": 0.0, "written": [],
                "msg": str(exc)}

    colorized_lowres = comfy_bridge.colorize_edit_from_conditioning(
        pipe, loaded["conditioning"], loaded["latent"], steps=steps, seed=seed)
    written = _pair_split_save(colorized_lowres, geom, out1_path, out2_path)
    elapsed = time.perf_counter() - t0
    logger.info("colorize_pair_edit_from_te: %s (mode=%s, %d out)",
                stem, geom.get("mode"), len(written))
    return {"ok": True, "skipped": False, "elapsed": elapsed,
            "written": written, "msg": ""}


def cleanup_te_cache(te_dir) -> dict:
    """Delete the conditioning files of a colorized chunk and reset the
    manifest frames (its key fields stay): the split flow only needs the cache
    while the chunk's frames are being colorized, so the disk stays bounded.
    Shared by the viggle and edit split flows. Returns {"ok", "count", "msg"}.
    """
    te_dir = str(te_dir)
    count = 0
    if os.path.isdir(te_dir):
        for name in os.listdir(te_dir):
            if name.endswith(".safetensors"):
                try:
                    os.remove(os.path.join(te_dir, name))
                    count += 1
                except OSError:
                    pass
    manifest_path = os.path.join(te_dir, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            manifest["frames"] = {}
            tmp = manifest_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=1, ensure_ascii=False)
            os.replace(tmp, manifest_path)
        except Exception:
            pass
    return {"ok": True, "count": count, "msg": ""}


# ----------------------------
# Pair Processing
# ----------------------------
VIGGLE_PAIR_RESOLUTION = 1280  # working resolution for qwen21-viggle in
                                 # pair-mode only (vs 1024 for single-image
                                 # and for the other backends) - mitigates
                                 # fine-detail color artifacts near the
                                 # merge boundary at the default resolution.
                                 # 1280 chosen over 1536: same fix at ~47%
                                 # time cost instead of ~105%, validated by
                                 # the user on thousands of real frames.

def process_image_pair(pipe, img1_path: Path, img2_path: Path, output_dir: Path, prompt: str, gap_px=16, steps: int = 2, enhance_prompt: bool = False, usm_radius: float = 0.0) -> float:
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
        return process_image_standard(pipe, orig2, out2, prompt, steps=steps, enhance_prompt=enhance_prompt, usm_radius=usm_radius)

    if orig2_dark:
        return process_image_standard(pipe, orig1, out1, prompt, steps=steps, enhance_prompt=enhance_prompt, usm_radius=usm_radius)

    # Convert to B&W (with the optional unsharp-mask pre-filter)
    bw1 = ImageEnhance.Color(orig1).enhance(0.0)
    bw2 = ImageEnhance.Color(orig2).enhance(0.0)
    bw1 = apply_input_usm(bw1, usm_radius)
    bw2 = apply_input_usm(bw2, usm_radius)

    # Resize to a working resolution - higher for qwen21-viggle in pair-mode
    # (mitigates fine-detail color artifacts near the merge boundary)
    pair_resolution = VIGGLE_PAIR_RESOLUTION if (isinstance(pipe, dict) and pipe.get("_model_type") == "qwen21-viggle") else 1024
    lowres1 = resize_long_side(bw1, pair_resolution)
    lowres2 = resize_long_side(bw2, pair_resolution)
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
    colorized_merged = colorize_image(pipe, merged_input, prompt, steps=steps, enhance_prompt=enhance_prompt, resolution=pair_resolution)
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


