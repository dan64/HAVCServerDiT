"""
comfy_bridge.longcat_colorize  :  LongCat-Image-Edit-Turbo GGUF inference.
Uses the comfy_bridge internal ComfyUI runtime — no external ComfyUI checkout needed.
"""
import sys, os, torch, logging, numpy as np
from PIL import Image

# Bootstrap: make comfy_bridge importable as top-level
from . import _bootstrap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cached pipeline state (loaded once, reused across calls)
# ---------------------------------------------------------------------------
_pipeline = None


def get_value_at_index(obj, index):
    try:
        return obj[index]
    except KeyError:
        return obj["result"][index]


def load_pipeline(
    unet_name: str = "LongCat-Image-Edit-Turbo-Q4_K_M.gguf",
    clip_name: str = "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
    vae_name: str = "lct_vae.safetensors",
):
    """Load LongCat-Image-Edit-Turbo GGUF via ComfyUI runtime.
    Returns a dict with model handles; subsequent calls are no-ops."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    import importlib
    import folder_paths

    # Import GGUF nodes and register custom folder paths
    _gguf = importlib.import_module("ComfyUI-GGUF")
    _gguf_nodes = importlib.import_module("ComfyUI-GGUF.nodes")
    _gguf_ncm = _gguf.NODE_CLASS_MAPPINGS

    # Patch folder_paths to accept .gguf files alongside existing exts.
    # UnetLoaderGGUF/CLIPLoaderGGUF use get_full_path("unet"/"clip", ...)
    # but the base folder_paths only allows supported_pt_extensions.
    _prev = logging.getLogger().getEffectiveLevel()
    logging.getLogger().setLevel(logging.ERROR)
    _unet_dirs = folder_paths.get_folder_paths("unet")
    _clip_dirs = folder_paths.get_folder_paths("clip")
    _gguf_nodes.update_folder_names_and_paths("unet_gguf", _unet_dirs)
    _gguf_nodes.update_folder_names_and_paths("clip_gguf", _clip_dirs)
    # Also add .gguf to the base ext lists so native GGUF loaders work.
    # "unet" maps to "diffusion_models", "clip" maps to "text_encoders".
    for _key in ("diffusion_models", "text_encoders"):
        if _key in folder_paths.folder_names_and_paths:
            _dirs, _exts = folder_paths.folder_names_and_paths[_key]
            folder_paths.folder_names_and_paths[_key] = (_dirs, _exts | {".gguf"})
    logging.getLogger().setLevel(_prev)

    from comfy_extras.nodes_flux import (
        FluxKontextImageScale,
        FluxGuidance,
        FluxKontextMultiReferenceLatentMethod,
    )
    import nodes as cn
    from comfy_extras.nodes_qwen import TextEncodeQwenImageEditPlus
    from comfy_extras.nodes_cfg import CFGNorm

    # Load UNet via GGUF (use native UnetLoaderGGUF for correctness)
    logger.info("Loading LongCat UNet (GGUF): %s", unet_name)
    unet_result = _gguf_ncm["UnetLoaderGGUF"]().load_unet(unet_name=unet_name)
    unet = get_value_at_index(unet_result, 0)

    # Load CLIP via GGUF (use native CLIPLoaderGGUF)
    logger.info("Loading LongCat CLIP (GGUF): %s", clip_name)
    clip_result = _gguf_ncm["CLIPLoaderGGUF"]().load_clip(
        clip_name=clip_name, type="longcat_image"
    )
    clip = get_value_at_index(clip_result, 0)

    # Load VAE (standard safetensors)
    logger.info("Loading LongCat VAE: %s", vae_name)
    vae_result = cn.VAELoader().load_vae(vae_name=vae_name)
    vae = get_value_at_index(vae_result, 0)

    _pipeline = {
        "unet": unet,
        "clip": clip,
        "vae": vae,
        "_cfgnorm": CFGNorm,
        "_imagescale": FluxKontextImageScale,
        "_textencode": TextEncodeQwenImageEditPlus,
        "_fluxguidance": FluxGuidance,
        "_multiref": FluxKontextMultiReferenceLatentMethod,
    }
    logger.info("LongCat GGUF pipeline loaded")
    return _pipeline


def colorize(pipeline, image, prompt="colorize this image", steps=8, seed=42):
    """Colorize a PIL RGB image using the LongCat GGUF pipeline.
    Returns a PIL RGB Image."""
    import nodes as cn

    with torch.inference_mode():
        # PIL → tensor
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        # CFGNorm
        cfgnorm_out = pipeline["_cfgnorm"]().EXECUTE_NORMALIZED(
            strength=1, pre_cfg=False, model=pipeline["unet"],
        )
        model_patched = get_value_at_index(cfgnorm_out, 0)

        # FluxKontextImageScale
        scale_out = pipeline["_imagescale"]().EXECUTE_NORMALIZED(image=img_tensor)
        img_scaled = get_value_at_index(scale_out, 0)
        if img_scaled.ndim == 3:
            img_scaled = img_scaled.unsqueeze(0)

        # TextEncodeQwenImageEditPlus (positive)
        pos_out = pipeline["_textencode"]().EXECUTE_NORMALIZED(
            prompt=prompt,
            clip=pipeline["clip"],
            vae=pipeline["vae"],
            image1=img_scaled,
        )
        positive_raw = get_value_at_index(pos_out, 0)

        # FluxGuidance (positive)
        fg_pos_out = pipeline["_fluxguidance"]().EXECUTE_NORMALIZED(
            guidance=2.5, conditioning=positive_raw,
        )
        positive = get_value_at_index(fg_pos_out, 0)

        # FluxKontextMultiReferenceLatentMethod (positive)
        mref_pos_out = pipeline["_multiref"]().EXECUTE_NORMALIZED(
            reference_latents_method="index", conditioning=positive,
        )
        positive_cond = get_value_at_index(mref_pos_out, 0)

        # TextEncodeQwenImageEditPlus (negative)
        neg_out = pipeline["_textencode"]().EXECUTE_NORMALIZED(
            prompt="",
            clip=pipeline["clip"],
            vae=pipeline["vae"],
            image1=img_scaled,
        )
        negative_raw = get_value_at_index(neg_out, 0)

        # FluxGuidance (negative)
        fg_neg_out = pipeline["_fluxguidance"]().EXECUTE_NORMALIZED(
            guidance=2.5, conditioning=negative_raw,
        )
        negative = get_value_at_index(fg_neg_out, 0)

        # FluxKontextMultiReferenceLatentMethod (negative)
        mref_neg_out = pipeline["_multiref"]().EXECUTE_NORMALIZED(
            reference_latents_method="index", conditioning=negative,
        )
        negative_cond = get_value_at_index(mref_neg_out, 0)

        # EmptyLatentImage
        _, h, w = img_scaled.shape[:3] if img_scaled.ndim == 4 else (1, *img_scaled.shape[:2])
        latent = cn.EmptyLatentImage().generate(width=w, height=h, batch_size=1)
        latent_dict = latent[0]

        # KSampler
        sampled = cn.KSampler().sample(
            seed=seed, steps=steps, cfg=1.0,
            sampler_name="euler", scheduler="simple", denoise=1.0,
            model=model_patched,
            positive=positive_cond, negative=negative_cond,
            latent_image=latent_dict,
        )
        latent_samples = sampled[0]

        # VAEDecode
        decoded = cn.VAEDecode().decode(samples=latent_samples, vae=pipeline["vae"])
        img_t = get_value_at_index(decoded, 0)

    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    return Image.fromarray((img_np * 255).astype(np.uint8))
