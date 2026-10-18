"""
comfy_bridge.longcat_colorize  :  LongCat-Image-Edit-Turbo GGUF inference.
Uses the comfy_bridge internal ComfyUI runtime — no external ComfyUI checkout needed.
"""
import sys, os, torch, logging, numpy as np
from PIL import Image

# Bootstrap: make comfy_bridge importable as top-level
from . import _bootstrap

logger = logging.getLogger(__name__)

# Distilled guidance baked into the LongCat-Image-Edit-Turbo graph (the
# FluxGuidance node of the reference workflow): it travels in the cached
# conditioning, so the split flow has to restore it too.
GUIDANCE = 2.5
REFERENCE_LATENTS_METHOD = "index"

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


# ---------------------------------------------------------------------------
# Split colorize (Fast Pipeline): phase A caches the conditioning, phase B
# samples from it, so the TE + VAE and the UNet + VAE each stay resident for
# a whole batch instead of alternating per image.
# ---------------------------------------------------------------------------

def _prepare(image):
    """The live path's prologue: RGB float tensor + FluxKontextImageScale
    (the ~1 Mpx Kontext snap the VAE and the text encoder both see)."""
    from . import _edit_prepare

    return _edit_prepare(image)


def _start_latent(img_scaled):
    """The empty latent the live path feeds KSampler (same dimensions as the
    scaled image, empty: the sampler adds the noise)."""
    import nodes as cn

    if img_scaled.ndim == 4:
        _, h, w = img_scaled.shape[:3]
    else:
        h, w = img_scaled.shape[:2]
    latent = cn.EmptyLatentImage().generate(width=int(w), height=int(h), batch_size=1)
    return latent[0]


def _encode_positive(pipeline, img_scaled, prompt):
    """The positive half of the live graph: EditPlus encode -> FluxGuidance ->
    reference-latent method. The negative pass is not computed: KSampler runs
    at cfg=1.0 and comfy/samplers.py takes the cfg1 fast path (uncond=None),
    so it would be a full text-encoder pass thrown away (the same saving the
    edit family already makes)."""
    pos_out = pipeline["_textencode"]().EXECUTE_NORMALIZED(
        prompt=prompt,
        clip=pipeline["clip"],
        vae=pipeline["vae"],
        image1=img_scaled,
    )
    positive_raw = get_value_at_index(pos_out, 0)
    fg_pos_out = pipeline["_fluxguidance"]().EXECUTE_NORMALIZED(
        guidance=GUIDANCE, conditioning=positive_raw,
    )
    positive = get_value_at_index(fg_pos_out, 0)
    mref_pos_out = pipeline["_multiref"]().EXECUTE_NORMALIZED(
        reference_latents_method=REFERENCE_LATENTS_METHOD, conditioning=positive,
    )
    return get_value_at_index(mref_pos_out, 0)


def encode_conditioning(pipeline, image, prompt):
    """Phase A of the split flow for longcat-gguf: the positive conditioning
    (context + reference latents + guidance/method values) and the start
    latent of one image. Returns {"conditioning", "latent"} for
    save_conditioning() or direct reuse."""
    with torch.inference_mode():
        img_scaled = _prepare(image)
        conditioning = _encode_positive(pipeline, img_scaled, prompt)
        latent_dict = _start_latent(img_scaled)
    return {"conditioning": conditioning, "latent": latent_dict}


def _decode(img_t):
    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    return Image.fromarray((img_np * 255).astype(np.uint8))


def colorize_from_conditioning(pipeline, conditioning, latent_dict, steps=8, seed=42):
    """Phase B of the split flow: sample + decode one cached conditioning.
    Same graph as colorize() (CFGNorm strength 1, euler/simple, cfg 1.0); the
    positive is passed in both slots because cfg 1.0 never reads the second
    one. Returns the colorized PIL image."""
    import nodes as cn

    with torch.inference_mode():
        cfgnorm_out = pipeline["_cfgnorm"]().EXECUTE_NORMALIZED(
            strength=1, pre_cfg=False, model=pipeline["unet"],
        )
        model_patched = get_value_at_index(cfgnorm_out, 0)

        sampled = cn.KSampler().sample(
            seed=seed, steps=steps, cfg=1.0,
            sampler_name="euler", scheduler="simple", denoise=1.0,
            model=model_patched,
            positive=conditioning, negative=conditioning,
            latent_image=latent_dict,
        )
        decoded = cn.VAEDecode().decode(samples=sampled[0], vae=pipeline["vae"])
        img_t = get_value_at_index(decoded, 0)
    return _decode(img_t)


def save_conditioning(path, conditioning, latent_dict, prompt="", meta=None):
    """Save an encode_conditioning() result as one .safetensors file.

    The edit-family format cannot be reused: the LongCat sampler also needs
    the distilled guidance and the reference-latent method, which live in the
    conditioning dict rather than in tensors -- both are written as metadata.
    Returns the metadata dict written.
    """
    from safetensors.torch import save_file

    extra = conditioning[0][1]
    reference_latents = extra.get("reference_latents") or []
    if not reference_latents:
        raise ValueError("save_conditioning: conditioning has no reference_latents")
    tensors = {
        "context": conditioning[0][0].detach().to("cpu").contiguous(),
        "latent_samples": latent_dict["samples"].detach().to("cpu").contiguous(),
    }
    for i, ref in enumerate(reference_latents):
        tensors[f"reference_latent_{i}"] = ref.detach().to("cpu").contiguous()
    metadata = {
        "format": "1",
        "kind": "longcat-conditioning",
        "prompt": str(prompt),
        "guidance": str(extra.get("guidance", GUIDANCE)),
        "reference_latents_method": str(
            extra.get("reference_latents_method", REFERENCE_LATENTS_METHOD)),
        "references": str(len(reference_latents)),
    }
    if meta:
        metadata.update({str(k): str(v) for k, v in meta.items()})
    save_file(tensors, path, metadata=metadata)
    return metadata


def load_conditioning(path):
    """Load a conditioning saved by save_conditioning(). Returns
    {"conditioning", "latent", "meta"} in the structure the sampler expects.
    Raises ValueError for any other conditioning kind (an edit-family file in
    the same folder, for instance)."""
    import comfy.model_management
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as f:
        meta = dict(f.metadata() or {})
        if meta.get("kind") != "longcat-conditioning":
            raise ValueError("load_conditioning: not a longcat conditioning file")
        tensors = {k: f.get_tensor(k) for k in f.keys()}

    device = comfy.model_management.get_torch_device()
    count = int(meta.get("references", "1") or "1")
    reference_latents = [tensors[f"reference_latent_{i}"].to(device)
                         for i in range(count)]
    conditioning = [[tensors["context"].to(device), {
        "pooled_output": None,
        "reference_latents": reference_latents,
        "guidance": float(meta.get("guidance", GUIDANCE)),
        "reference_latents_method": meta.get(
            "reference_latents_method", REFERENCE_LATENTS_METHOD),
    }]]
    latent_dict = {"samples": tensors["latent_samples"].to(device)}
    return {"conditioning": conditioning, "latent": latent_dict, "meta": meta}
