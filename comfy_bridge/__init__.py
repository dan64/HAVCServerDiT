"""
comfy_bridge  :  ComfyUI-native GGUF inference, self-contained.
No dependency on external ComfyUI installation.
"""

import sys, os, torch, logging, numpy as np
from PIL import Image

# Bootstrap: make comfy_bridge importable as top-level
from . import _bootstrap

# Silence verbose backend logs
logging.getLogger("comfy_kitchen").setLevel(logging.WARNING)
logging.getLogger("comfy.quant_ops").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def get_value_at_index(obj, index):
    try:
        return obj[index]
    except KeyError:
        return obj["result"][index]


def load_gguf_pipeline(unet_path, clip_path, vae_name="qwen_image_vae.safetensors", lora_path=None):
    import importlib
    _gguf_loader = importlib.import_module("ComfyUI-GGUF.loader")
    _gguf_nodes  = importlib.import_module("ComfyUI-GGUF.nodes")
    _gguf_ops    = importlib.import_module("ComfyUI-GGUF.ops")
    GGMLOps = _gguf_ops.GGMLOps
    GGUFModelPatcher = _gguf_nodes.GGUFModelPatcher
    gguf_sd_loader = _gguf_loader.gguf_sd_loader
    gguf_clip_loader = _gguf_loader.gguf_clip_loader
    update_folder_names_and_paths = _gguf_nodes.update_folder_names_and_paths

    import comfy.model_management
    import comfy.sd
    import comfy.sample
    import comfy.samplers
    import comfy.utils
    import folder_paths
    # Suppress "Unknown file list already present"  :  we're intentionally overriding
    _prev_level = logging.getLogger().getEffectiveLevel()
    logging.getLogger().setLevel(logging.ERROR)
    update_folder_names_and_paths("unet_gguf", [os.path.dirname(unet_path)])
    update_folder_names_and_paths("clip_gguf", [os.path.dirname(clip_path)])
    logging.getLogger().setLevel(_prev_level)

    # UNet
    logger.info("Loading UNet GGUF: %s", unet_path)
    ops = GGMLOps()
    sd, extra = gguf_sd_loader(unet_path)
    model = comfy.sd.load_diffusion_model_state_dict(sd, model_options={"custom_operations": ops})
    if model is None:
        raise RuntimeError(f"Failed to load UNet from {unet_path}")
    model = GGUFModelPatcher.clone(model)
    logger.info("UNet loaded (%s)", extra.get("arch_str", "?"))

    # CLIP
    logger.info("Loading CLIP GGUF: %s", clip_path)
    clip_data = gguf_clip_loader(clip_path)
    clip = comfy.sd.load_text_encoder_state_dicts(
        clip_type=comfy.sd.CLIPType.QWEN_IMAGE,
        state_dicts=[clip_data],
        model_options={
            "custom_operations": GGMLOps,
            "initial_device": comfy.model_management.text_encoder_offload_device(),
        },
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
    )
    clip.patcher = GGUFModelPatcher.clone(clip.patcher)
    logger.info("CLIP loaded (qwen_image)")

    # VAE
    logger.info("Loading VAE: %s", vae_name)
    vae_path = folder_paths.get_full_path_or_raise("vae", vae_name)
    vae_sd = comfy.utils.load_torch_file(vae_path, safe_load=True)
    vae = comfy.sd.VAE(sd=vae_sd)
    logger.info("VAE loaded: type=%s, latent_dim=%d, not_video=%s",
                type(vae.first_stage_model).__name__,
                getattr(vae, 'latent_dim', '?'),
                getattr(vae, 'not_video', '?'))

    # LoRA
    if lora_path and os.path.isfile(lora_path):
        from comfy.utils import load_torch_file
        from comfy.lora import load_lora as comfy_load_lora, model_lora_keys_unet
        from comfy.lora_convert import convert_lora
        lora_sd = load_torch_file(lora_path, safe_load=True)
        lora_sd = convert_lora(lora_sd)
        key_map = model_lora_keys_unet(model.model, {})
        patch_dict = comfy_load_lora(lora_sd, key_map)
        if patch_dict:
            model.add_patches(patch_dict, 1.0)
            logger.info("LoRA loaded: %d keys", len(patch_dict))

    return {"unet": model, "clip": clip, "vae": vae, "model": model}


def colorize(pipeline, image, prompt, steps=4, seed=42):
    """Exact replica of ComfyUI workflow using same node calls."""
    import nodes as cn
    from comfy_extras.nodes_flux import FluxKontextImageScale
    from comfy_extras.nodes_qwen import TextEncodeQwenImageEdit
    from comfy_extras.nodes_model_advanced import ModelSamplingAuraFlow

    with torch.inference_mode():
        # PIL → tensor
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        # FluxKontextImageScale
        _fks_out = FluxKontextImageScale().EXECUTE_NORMALIZED(image=img_tensor)
        img_scaled = get_value_at_index(_fks_out, 0)
        if img_scaled.ndim == 3:
            img_scaled = img_scaled.unsqueeze(0)  # (H,W,C) → (1,H,W,C)

        # VAEEncode
        latent = cn.VAEEncode().encode(
            pixels=img_scaled, vae=pipeline["vae"])
        latent_dict = latent[0]

        # TextEncodeQwenImageEdit (positive)
        _pos_raw = TextEncodeQwenImageEdit().EXECUTE_NORMALIZED(
            prompt=prompt,
            clip=pipeline["clip"],
            vae=pipeline["vae"],
            image=img_scaled,
        )
        positive = get_value_at_index(_pos_raw, 0)

        # TextEncodeQwenImageEdit (negative)
        _neg_raw = TextEncodeQwenImageEdit().EXECUTE_NORMALIZED(
            prompt="black and white, faded colors",
            clip=pipeline["clip"],
            vae=pipeline["vae"],
            image=img_scaled,
        )
        negative = get_value_at_index(_neg_raw, 0)

        # ModelSamplingAuraFlow
        unet_sampled = ModelSamplingAuraFlow().patch_aura(
            shift=3, model=pipeline["model"])[0]

        # KSampler
        sampled = cn.KSampler().sample(
            seed=seed, steps=steps, cfg=1.0,
            sampler_name="euler", scheduler="simple", denoise=1.0,
            model=unet_sampled,
            positive=positive, negative=negative,
            latent_image=latent_dict,
        )
        latent_samples = sampled[0]

        # VAEDecode
        img_decoded = cn.VAEDecode().decode(
            samples=latent_samples, vae=pipeline["vae"])
        img_t = get_value_at_index(img_decoded, 0)

    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    return Image.fromarray((img_np * 255).astype(np.uint8))