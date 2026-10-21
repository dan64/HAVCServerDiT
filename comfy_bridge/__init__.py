"""
comfy_bridge  :  ComfyUI-native GGUF inference, self-contained.
No dependency on external ComfyUI installation.
"""

import sys, os

# Bootstrap: make comfy_bridge importable as top-level
from . import _bootstrap

# DynamicVRAM (comfy-aimdo): the process half runs before torch is imported,
# like the same block in ComfyUI's main.py; the device half --
# _dynamic_vram.enable() -- is called by the pipeline loaders below, before
# the first model load. Set HAVC_DYNAMIC_VRAM=0 to keep the legacy patcher.
from . import _dynamic_vram
_dynamic_vram.init_process()

import torch, logging, json, math, numpy as np
import time
from PIL import Image

# Opt-in per-image profiler for the Qwen-Image-Edit path (HAVC_EDIT_PROFILE=1)
from . import edit_profile as _edit_profile

# Silence verbose backend logs
logging.getLogger("comfy_kitchen").setLevel(logging.WARNING)
logging.getLogger("comfy.quant_ops").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def get_value_at_index(obj, index):
    try:
        return obj[index]
    except KeyError:
        return obj["result"][index]


def flush_between_units():
    """Allocator hygiene between two units of a phase-B loop (HAVC_UNIT_FLUSH).

    Thin alias of comfy_bridge._dynamic_vram.flush_between_units(): a time-gated
    gc.collect() + soft_empty_cache() mirroring ComfyUI's prompt loop, off
    unless DynamicVRAM is active or HAVC_UNIT_FLUSH forces it. Never raises.
    """
    return _dynamic_vram.flush_between_units()


def load_gguf_pipeline(unet_path, clip_path, vae_name="qwen_image_vae.safetensors", lora_path=None,
                       vram_headroom=None):
    """vram_headroom: the config's GB of VRAM aimdo must leave free (see
    _dynamic_vram.enable / _resolve_headroom); None -> the default."""
    _dynamic_vram.enable(vram_headroom=vram_headroom)  # DynamicVRAM before the first model load (see _dynamic_vram)
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

    # UNet: GGUF quant (ComfyUI-GGUF recipe, dequantized per-op) or native
    # safetensors (stock UNETLoader) -- e.g. the Comfy-Org int8 ConvRot
    # checkpoint for Qwen-Image-Edit 2511.
    unet_name = os.path.basename(unet_path)
    if unet_name.lower().endswith(".gguf"):
        logger.info("Loading UNet GGUF: %s", unet_name)
        ops = GGMLOps()
        sd, extra = gguf_sd_loader(unet_path)
        model = comfy.sd.load_diffusion_model_state_dict(sd, model_options={"custom_operations": ops})
        if model is None:
            raise RuntimeError(f"Failed to load UNet from {unet_path}")
        model = GGUFModelPatcher.clone(model)
        logger.info("UNet loaded (%s)", extra.get("arch_str", "?"))
    else:
        import nodes as cn
        logger.info("Loading UNet (native safetensors): %s", unet_name)
        model = get_value_at_index(
            cn.UNETLoader().load_unet(unet_name=unet_name, weight_dtype="default"), 0)

    # CLIP: GGUF text encoder (ComfyUI-GGUF recipe; the matching mmproj is
    # auto-discovered from the same folder) or a native safetensors text
    # encoder (stock CLIPLoader) -- e.g. the Qwen2.5-VL int8 ConvRot
    # checkpoint, which ships the vision tower in the same file.
    clip_name = os.path.basename(clip_path)
    if clip_name.lower().endswith(".safetensors"):
        import nodes as cn
        logger.info("Loading CLIP (native safetensors): %s", clip_name)
        clip = get_value_at_index(
            cn.CLIPLoader().load_clip(clip_name=clip_name, type="qwen_image",
                                      device="default"), 0)
    else:
        logger.info("Loading CLIP GGUF: %s", clip_name)
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
    _edit_profile.start_run(steps=steps, seed=seed, image=image.size)
    try:
        return _colorize_impl(pipeline, image, prompt, steps, seed)
    finally:
        _edit_profile.end_run()


def _colorize_impl(pipeline, image, prompt, steps=4, seed=42):
    with torch.inference_mode():
        with _edit_profile.phase("prep"):
            img_scaled = _edit_prepare(image)

        positive, latent_dict = _edit_encode_positive(pipeline, img_scaled, prompt)

        img_t = _edit_sample_decode(pipeline, positive, latent_dict, steps, seed)

    with _edit_profile.phase("post"):
        return _edit_to_pil(img_t)


def _edit_prepare(image):
    """The live path's prologue: RGB float tensor + FluxKontextImageScale
    (the ~1 Mpx Kontext snap both the VAE and the text encoder see)."""
    from comfy_extras.nodes_flux import FluxKontextImageScale

    img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
    img_tensor = torch.from_numpy(img_np).unsqueeze(0)
    _fks_out = FluxKontextImageScale().EXECUTE_NORMALIZED(image=img_tensor)
    img_scaled = get_value_at_index(_fks_out, 0)
    if img_scaled.ndim == 3:
        img_scaled = img_scaled.unsqueeze(0)  # (H,W,C) → (1,H,W,C)
    return img_scaled


def _edit_encode_positive(pipeline, img_scaled, prompt):
    """VAE encode of the start latent + the positive TextEncodeQwenImageEdit
    conditioning, in the live path's order. Returns (conditioning, latent).

    The node's negative pass is not computed: KSampler runs at cfg=1.0 and
    comfy/samplers.py takes the cfg1 fast path (uncond=None), so the negative
    conditioning is never consumed (~1.5 s/image of a second full text-
    encoder pass, vision tower included). Same treatment as colorize_viggle();
    dist/scripts/check_edit_bitexact.py verifies that sampling with the positive
    folded in as the negative reproduces the live output byte-for-byte.
    """
    import nodes as cn
    from comfy_extras.nodes_qwen import TextEncodeQwenImageEdit

    with _edit_profile.phase("vaeenc"):
        latent = cn.VAEEncode().encode(pixels=img_scaled, vae=pipeline["vae"])
        latent_dict = latent[0]

    with _edit_profile.phase("te_pos"):
        _pos_raw = TextEncodeQwenImageEdit().EXECUTE_NORMALIZED(
            prompt=prompt,
            clip=pipeline["clip"],
            vae=pipeline["vae"],
            image=img_scaled,
        )
        positive = get_value_at_index(_pos_raw, 0)
    return positive, latent_dict


def _edit_sample_decode(pipeline, conditioning, latent_dict, steps, seed):
    """Sampler + VAE decode, exactly as the live path: AuraFlow shift=3,
    euler/simple, cfg=1.0 (the negative slot carries the same conditioning;
    the cfg1 fast path never reads it)."""
    import nodes as cn
    from comfy_extras.nodes_model_advanced import ModelSamplingAuraFlow

    with _edit_profile.phase("patch"):
        unet_sampled = ModelSamplingAuraFlow().patch_aura(
            shift=3, model=pipeline["model"])[0]

    with _edit_profile.phase("sampling"):
        sampled = cn.KSampler().sample(
            seed=seed, steps=steps, cfg=1.0,
            sampler_name="euler", scheduler="simple", denoise=1.0,
            model=unet_sampled,
            positive=conditioning, negative=conditioning,
            latent_image=latent_dict,
        )
        latent_samples = sampled[0]

    with _edit_profile.phase("decode"):
        img_decoded = cn.VAEDecode().decode(
            samples=latent_samples, vae=pipeline["vae"])
        img_t = get_value_at_index(img_decoded, 0)
    return img_t


def _edit_to_pil(img_t):
    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    return Image.fromarray((img_np * 255).astype(np.uint8))


def encode_edit_conditioning(pipeline, image, prompt):
    """Phase A of the split-colorize flow for the Qwen-Image-Edit family:
    compute the positive conditioning + the start latent of one image and
    return them for caching (save_edit_conditioning) or direct reuse.

    Mirrors the live path (same Kontext snap, same VAE encode order, same
    node call); the node's negative pass is skipped as in _colorize_impl().
    Returns {"conditioning": ..., "latent": ...}.
    """
    with torch.inference_mode():
        with _edit_profile.phase("prep"):
            img_scaled = _edit_prepare(image)
        positive, latent_dict = _edit_encode_positive(pipeline, img_scaled, prompt)
    return {"conditioning": positive, "latent": latent_dict}


def colorize_edit_from_conditioning(pipeline, conditioning, latent_dict, steps=4, seed=42):
    """Phase B of the split-colorize flow: sample + decode one image from a
    precomputed edit conditioning. Returns the colorized PIL image."""
    with torch.inference_mode():
        img_t = _edit_sample_decode(pipeline, conditioning, latent_dict, steps, seed)
    with _edit_profile.phase("post"):
        return _edit_to_pil(img_t)


def save_edit_conditioning(path, conditioning, latent_dict, prompt="", meta=None):
    """Save an encode_edit_conditioning() result as one .safetensors file
    (~21 MB per frame at the ~1 Mpx budget: the edit context is ~1.4k tokens
    of image+text embeddings, far larger than the viggle one).

    The reference latent and the start latent are both stored: they come from
    two different VAE encodes and are not interchangeable. Returns the
    metadata dict written.
    """
    from safetensors.torch import save_file

    extra = conditioning[0][1]
    reference_latents = extra.get("reference_latents") or []
    if not reference_latents:
        raise ValueError("save_edit_conditioning: conditioning has no reference_latents")
    samples = latent_dict["samples"]
    tensors = {
        "context": conditioning[0][0].detach().to("cpu").contiguous(),
        "reference_latent": reference_latents[0].detach().to("cpu").contiguous(),
        "latent_samples": samples.detach().to("cpu").contiguous(),
    }
    metadata = {
        "format": "1",
        "kind": "qwen-edit-conditioning",
        "prompt": str(prompt),
    }
    if meta:
        metadata.update({str(k): str(v) for k, v in meta.items()})
    save_file(tensors, path, metadata=metadata)
    return metadata


def load_edit_conditioning(path):
    """Load a conditioning saved by save_edit_conditioning(). Returns
    {"conditioning", "latent", "meta"} in the same structure the live path
    hands to the sampler. Raises ValueError when the file is not an edit
    conditioning (a viggle cache file has the same tensor names but a
    different structure -- see load_viggle_conditioning)."""
    import comfy.model_management
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as f:
        meta = dict(f.metadata() or {})
        if meta.get("kind") != "qwen-edit-conditioning":
            raise ValueError(
                "load_edit_conditioning: not a qwen-edit conditioning file")
        tensors = {k: f.get_tensor(k) for k in f.keys()}

    device = comfy.model_management.get_torch_device()
    conditioning = [[tensors["context"].to(device), {
        "pooled_output": None,
        "reference_latents": [tensors["reference_latent"].to(device)],
    }]]
    latent_dict = {"samples": tensors["latent_samples"].to(device)}
    return {"conditioning": conditioning, "latent": latent_dict, "meta": meta}


def load_viggle_pipeline(unet_path, clip_path, vae_name="qwen_image_2.1_vae_bf16.safetensors", lora_path=None, clip_mmproj=None,
                         vram_headroom=None):
    """Load Qwen-Image-2.1 (native ComfyUI int8 ConvRot or GGUF-quantized).

    The Viggle-Turbo LoRA is applied as an unmerged runtime hook when
    lora_path is given; with lora_path empty/None the checkpoint is used
    as-is (merged models, e.g. the v0.3-6step quants).
    unet_path may be a safetensors file (stock UNETLoader) or a .gguf file
    (ComfyUI-GGUF recipe, same one load_gguf_pipeline() uses).

    clip_path may be either the default safetensors text encoder (loaded via
    the standard CLIPLoader node) or a GGUF text encoder -- in the latter
    case the matching mmproj file is auto-discovered by gguf_clip_loader()
    (ComfyUI-GGUF-Reboot, filename-containment heuristic)
    from the same folder as clip_path; clip_mmproj isn't consumed here, it
    only exists upstream to drive the mmproj auto-download.

    vram_headroom: the config's GB of VRAM aimdo must leave free (see
    _dynamic_vram.enable / _resolve_headroom); None -> the default.
    """
    _dynamic_vram.enable(vram_headroom=vram_headroom)  # DynamicVRAM before the first model load (see _dynamic_vram)
    import importlib
    ViggleTurboLora = importlib.import_module("viggle_turbo").ViggleTurboLora
    import nodes as cn

    unet_name = os.path.basename(unet_path)
    clip_name = os.path.basename(clip_path)

    logger.info("Loading UNet: %s", unet_name)
    if unet_name.lower().endswith(".gguf"):
        # GGUF UNet (e.g. the merged Viggle checkpoints' Q4..Q8 quants): the
        # stock UNETLoader only reads safetensors/torch files, so use the
        # same ComfyUI-GGUF recipe as load_gguf_pipeline().
        _gguf_loader = importlib.import_module("ComfyUI-GGUF.loader")
        _gguf_nodes = importlib.import_module("ComfyUI-GGUF.nodes")
        _gguf_ops = importlib.import_module("ComfyUI-GGUF.ops")
        import comfy.sd
        _sd, _extra = _gguf_loader.gguf_sd_loader(unet_path)
        model = comfy.sd.load_diffusion_model_state_dict(
            _sd, model_options={"custom_operations": _gguf_ops.GGMLOps()})
        if model is None:
            raise RuntimeError(f"Failed to load UNet from {unet_path}")
        model = _gguf_nodes.GGUFModelPatcher.clone(model)
        logger.info("UNet GGUF loaded (%s)", _extra.get("arch_str", "?"))
    else:
        model = get_value_at_index(cn.UNETLoader().load_unet(unet_name=unet_name, weight_dtype="default"), 0)

    if lora_path and os.path.isfile(lora_path):
        logger.info("Applying Viggle-Turbo LoRA: %s", os.path.basename(lora_path))
        model = get_value_at_index(
            ViggleTurboLora().load(model=model, lora_name=os.path.basename(lora_path), strength=1.0), 0)

    logger.info("Loading CLIP: %s", clip_name)
    if clip_path.lower().endswith(".gguf"):
        _reboot_loader = importlib.import_module("ComfyUI-GGUF-Reboot.loader")
        _reboot_ops = importlib.import_module("ComfyUI-GGUF-Reboot.ops")
        import comfy.sd
        import comfy.model_management
        import folder_paths
        clip_data = _reboot_loader.gguf_clip_loader(clip_path)
        clip = comfy.sd.load_text_encoder_state_dicts(
            clip_type=comfy.sd.CLIPType.QWEN_IMAGE,
            state_dicts=[clip_data],
            model_options={
                "custom_operations": _reboot_ops.GGMLOps,
                "initial_device": comfy.model_management.text_encoder_offload_device(),
            },
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
        )
        logger.info("CLIP loaded (qwen_image, GGUF+mmproj via ComfyUI-GGUF-Reboot)")
    else:
        clip = get_value_at_index(cn.CLIPLoader().load_clip(clip_name=clip_name, type="qwen_image", device="default"), 0)

    logger.info("Loading VAE: %s", vae_name)
    vae = get_value_at_index(cn.VAELoader().load_vae(vae_name=vae_name), 0)

    return {"model": model, "clip": clip, "vae": vae}


def load_qwen25_nunchaku_pipeline(unet_path, clip_path, vae_name="qwen_image_vae.safetensors",
                                  lora_path=None, lora_strength=1.0, cpu_offload="auto",
                                  num_blocks_on_gpu=1, use_pin_memory="disable", vram_headroom=None):
    """Load Qwen-Image-Edit (2509 / 2511) through the vendored
    ComfyUI-nunchaku core.

    unet_path is a Nunchaku SVDQuant checkpoint (official nunchaku-ai for
    2509 with the Lightning LoRA fused, QuantFunc for 2511 which needs the
    LoRA applied on top). clip_path is the usual Qwen2.5-VL text encoder
    (safetensors; the same file the other qwen families use).

    lora_path / lora_strength: LoRA composed into the quantized low-rank
    buffers at load time (no runtime hook, nothing to recompose per prompt).

    cpu_offload (auto|enable|disable), num_blocks_on_gpu, use_pin_memory:
    the Nunchaku loader's offload policy, applied *after* the LoRA — the
    composition resizes the buffers the offload manager is built from. On a
    16 GB card `auto` reports 15 GiB and therefore disables offload
    (upstream's rule); measured on the RTX 5070 Ti that is ~1.9x slower
    (10.5 s vs 5.4 s per frame at 2 steps), so the shipped 2511 config asks
    for `enable`.

    vram_headroom: the config's GB of VRAM aimdo must leave free (see
    _dynamic_vram.enable / _resolve_headroom); None -> the default.
    """
    _dynamic_vram.enable(vram_headroom=vram_headroom)  # before the first model load
    import importlib

    nunchaku_loader = importlib.import_module("ComfyUI-nunchaku.loader")
    import nodes as cn

    logger.info("Loading Nunchaku UNet: %s", os.path.basename(unet_path))
    model = nunchaku_loader.load_nunchaku_qwen_model(unet_path)

    if lora_path and os.path.isfile(lora_path):
        lora_mod = importlib.import_module("ComfyUI-QwenImageLoraLoader.lora")
        logger.info("Applying Qwen-Image LoRA: %s", os.path.basename(lora_path))
        lora_mod.apply_qwen_lora(model, lora_path, lora_strength)

    nunchaku_loader.configure_offload(
        model, cpu_offload=cpu_offload,
        num_blocks_on_gpu=num_blocks_on_gpu, use_pin_memory=use_pin_memory)

    logger.info("Loading CLIP: %s", os.path.basename(clip_path))
    clip = get_value_at_index(
        cn.CLIPLoader().load_clip(clip_name=os.path.basename(clip_path), type="qwen_image", device="default"), 0)

    logger.info("Loading VAE: %s", vae_name)
    vae = get_value_at_index(cn.VAELoader().load_vae(vae_name=vae_name), 0)

    return {"model": model, "clip": clip, "vae": vae}


_VIGGLE_SIGMA_NODES_2 = "1.0, 0.25"
_VIGGLE_SIGMA_NODES_4 = "1.0, 0.875, 0.5, 0.25"
_VIGGLE_SIGMA_NODES_6 = "1.0, 0.9375, 0.875, 0.75, 0.5, 0.25"  # v0.2.1-r128 LoRA, native step count
_VIGGLE_SIGMA_NODES_8 = "1, 0.9375, 0.875, 0.75, 0.625, 0.5, 0.25, 0.125"

_VIGGLE_SIGMA_SCHEDULES = {
    2: _VIGGLE_SIGMA_NODES_2,
    4: _VIGGLE_SIGMA_NODES_4,
    6: _VIGGLE_SIGMA_NODES_6,
    8: _VIGGLE_SIGMA_NODES_8,
}

# Qwen-Image-2.1-Turbo: the checkpoint's own 8-step sigma table (the
# `sample_sigmas` of Qwen/Qwen-Image-2.1-Turbo's model_index.json, plus the
# terminal 0 the samplers append). Fixed by the checkpoint -- the step count
# is not a free parameter for this family.
_QWEN21_TURBO_SIGMAS = ("1.0, 0.978453, 0.95418, 0.926626, 0.89508, "
                        "0.845148, 0.704534, 0.414568, 0")

_VIGGLE_PE_SYSTEM_PROMPT = """# Image Prompt Rewriting Expert

You turn a user's image request into one long English paragraph that describes the
finished image as if you were looking at it, plus the aspect ratio it should be
rendered at. You are not talking to the user and not talking to a renderer: you are
an observer reporting what is in the frame.

Work through the eight steps below in order. Each step commits one decision; later
steps never revise an earlier one.

## Step 1 — Read the brief and split it in two

List what the user has fixed and what they have left open.

Fixed, and it must survive into your description unchanged: every string of text
they want shown, every named object, every count, every stated colour, every stated
position, and the aspect ratio if they gave one. Copy their text strings character
for character, in their own script, including punctuation and spacing.

A third thing they may give you is an instruction about the job rather than about the
picture — "use double quotes", "no hard-edged blocks", "4K, no noise", "make sure the
text is sharp". That is not content. Obey it silently where it applies and never echo
it: the description states what is in the frame, never what must be done.

Open, and you must decide it: everything they did not mention. A three-word request
and a three-hundred-word request both become a description of the same size, so a
short brief means you are inventing most of the frame, not writing less.

## Step 2 — Fix the frame

Decide the orientation from the subject, then pick the ratio.

If the user states a ratio, use it. Otherwise: `3:2` for anything horizontal and
`2:3` for anything vertical — these are the two defaults and cover most images.
Use `1:1` for a square badge, icon, album cover or single centred emblem, `16:9`
for a wide cinematic or presentation frame, `1:2` or `9:16` for a phone screen or a
tall standing banner. `3:4`, `2:1`, `21:9`, `4:3`, `9:21`, `4:5`, `3:1`, `5:4`,
`1:3` exist but only when the subject or the user really calls for them.

The ratio lives only in the `wh_ratio` field. Never write a ratio, a resolution, or
a pixel count into the description itself.

## Step 3 — Write the opening sentence

One sentence, around twenty words. Name the medium, the style, the subject, and the
background or palette; usually name the orientation too:

`The image is a ⟨vertical / wide / square / tall⟩ ⟨style⟩ ⟨photograph · poster · illustration · scene · portrait · infographic · close-up · graphic · page · card · sheet · logo⟩ of ⟨subject⟩, ⟨the background and its palette⟩.`

`This is a …` or a bare `A vertical realistic photograph of …` work equally well. The
medium noun is the one part that is never omitted.

The style word goes here — realistic, photorealistic, minimalist, flat-vector,
cinematic, watercolour, isometric, editorial, hand-drawn, 3D-rendered, retro. Name
it once here; you may echo it in the closing sentence.

## Step 4 — Inventory before you write

Before any more prose, settle two lists.

Every element that will appear, each with a place in the frame: upper-left,
across the top, on the far right, in the lower-third, in the centre, in front of,
behind, tucked into the corner. You will need eight to fourteen such positional
phrases, about ten typically, and they must reach the corners, the edges and the
centre — not cluster in the middle.

Every piece of text that will be legible in the image, in reading order.

## Step 5 — Walk the frame

Now describe it in order. Which order depends on how the frame is filled.

**If the frame is divided into regions** — a poster, a page, an interface, a layout, a
wide scene with several things in it — walk the regions:

1. The background and the surface it sits on — this comes immediately after the
   opening sentence, not at the end.
2. The top band: headline, header bar, sky, ceiling, whatever occupies the top edge.
3. Down and across the body of the frame: left side, then centre, then right side.
   Give each region one or two sentences.
4. The bottom band: footer, foreground, ground plane, base row.

**If one subject fills the frame** — a portrait, a close-up, a single object — walk
the subject instead: the background and how far it falls off, then the subject's pose
and where it is placed in the frame, then head and face, then body and each garment or
surface, then what is held or touching it, then whatever little is left at the edges.
Keep using positional phrases inside the subject — in the upper-left of the frame,
behind the left shoulder, along the lower edge — so the frame stays locatable.

Roughly a third of your sentences should open on the positional phrase itself —
"On the right side of the frame, …", "In the upper-left corner, …", "Across the
lower third, …" — so the reader always knows where they are looking.

Keep it to one paragraph. Break to a new paragraph only when the image is genuinely
built from stacked regions — panels, cards, sections, slides — and then one
paragraph per region, each opening on where that region sits.

## Step 6 — Set every piece of text

Skip this step if nothing in the image is meant to be read — a third of images have
no legible text at all, and inventing signage for them is a mistake.

Otherwise, for each string from your Step 4 list, in reading order, name where it sits,
what it looks like, and what it says: `a bold black headline across the top reads "…"`.

Put the string in straight double quotes, in its own script — Chinese, Russian,
Korean, Japanese and Arabic text stays in Chinese, Russian, Korean, Japanese and
Arabic. Give its weight, colour, case and relative size. Describe a line break as a
second line rather than putting a real newline inside the string. If a mark is not meant
to be read — distant signage, a label behind glass, dense body copy — call it
blurred, indistinct, or too small to read rather than inventing letters. If the image contains a chart
or a table, its axes, tick labels, legend entries, series and cell values are text
too: write them out.

## Step 7 — Give the lighting its own sentence

Every image has light in it, and the description always accounts for it: the source,
its direction, its quality, and the shadows and highlights it leaves. Soft diffused
daylight from a window on the left, hard overhead studio light, warm low sun, flat
even ambient light for a diagram.

Once the contents are placed, give it a sentence of its own — `The lighting is …` —
or, if the light is what makes a particular surface look the way it does, fold it into
that surface's sentence. Either way it is stated explicitly, not left implied.

## Step 8 — Close with the whole frame

End on a single sentence that steps back:

`The overall composition ⟨is / uses / feels⟩ …`

`The composition is …`, `The overall design …`, `The overall mood …`, `The overall
palette …` and `The image has …` are the same move. Cover balance and symmetry, the
palette, the style, and the mood in that one sentence. Write exactly one such
sentence — do not follow it with a second summary.

## Throughout

**Size.** The description runs about twenty sentences and four to five hundred words,
roughly twenty-five words a sentence. That is the same size whether the brief was three
words or three hundred: a dense frame with many regions and a lot of text runs longer, a
single quiet subject runs shorter, but a thin brief never buys a thin description.

**Observe, don't instruct.** Present tense, third person, declarative. No "you", no
"create", no "make sure", no "the AI should". No quality boosters — no "masterpiece",
"8K", "highly detailed", "award-winning".

**Hedge what you cannot be certain of.** An observer describing a picture says
"appears to be", "likely", "suggesting", and offers a pair — "a notebook
or a tablet", "wood or dark laminate" — when the thing is genuinely ambiguous. Do
this often; it is the natural register here. Be flatly definite only about what the
user fixed.

**Name colours with a modifier, almost never bare.** Deep navy, muted olive, pale
cream, warm terracotta, soft dusty rose, blue-grey, off-white, charcoal, brownish-
green. Hex codes only if the user gave them.

**Give the material, not just the noun.** Brushed metal, matte plastic, glossy
ceramic, coarse linen, weathered wood, frosted glass, grain, scuffs, condensation,
visible brush strokes, paper fibre.

**Enumerate; never summarise.** "Several items" and "various decorations" are not
descriptions. Say what each thing is. Write small counts as words — three, five,
twelve — and if something is partly hidden, say so and describe the visible part.

**People get their observable surface.** Build, posture, where they are looking,
expression, hair, skin tone, and each garment with its colour and material. Age is a
life stage or a decade — a child, a teenager, a young adult, middle-aged, elderly,
in her thirties — never a number of years. If a face is turned away or cropped, say
that instead of describing it.

**Objects by class, not by brand.** A silver laptop, a mirrorless camera, a compact
hatchback — unless the user named the brand. Photographic and design vocabulary is
welcome: shallow depth of field, bokeh, backlit, close-up, negative space,
grid, drop shadow.

**Everything holds together physically.** Shadows fall away from the light, reflections
match what is in front of the surface, scale is consistent between neighbouring
objects, and a surface reacts to what sits on it. If the user asked for something
impossible, describe it as the image shows it and let the rest of the scene stay
coherent around it.

** Colorization **
This description will be used to add color to a black-and-white photograph, not
to hedge about what colors might be present. For any subject, garment, object, or
setting whose color is a matter of common knowledge or strong convention (a Santa
Claus costume, a stop sign, a national flag, a school bus), state that expected
color directly and confidently instead of describing it as "dark" or "muted" just
because the photograph itself has no color information. Reserve hedging for
genuinely ambiguous cases with no such convention. Then add to the description the
following requirement: <user_prompt>.

## Language

The description is always in English, whatever language the request arrives in. The
only exception is text shown inside the image, which stays in its own script.


## Output format

Return one strictly valid JSON object on a single line, nothing before or after:

{"rewritten_prompt": "<the description>"}"""


def _viggle_enhance_prompt(clip, image_tensor, prompt, seed=42):
    """Qwen3-VL image-aware prompt rewriting (mirrors the TextGenerate node's
    execute(), without mtp/use_quantized_matmul: those are speed optimizations,
    not correctness, and comfy_bridge's
    clip.generate() doesn't have the mtp parameter). Falls back to the
    original prompt on any failure (JSON parse, empty result, exception).
    """
    system_prompt = _VIGGLE_PE_SYSTEM_PROMPT.replace("<user_prompt>", prompt)
    request = f"{prompt}\n(Write the description in English.)"

    tokens = clip.tokenize(request, image=image_tensor, skip_template=False,
                            min_length=1, thinking=True, video=None, audio=None,
                            system_prompt=system_prompt)
    generated_ids = clip.generate(tokens, do_sample=False, max_length=512, seed=seed)
    generated_text = clip.decode(generated_ids)

    reasoning, _, text = generated_text.partition("</think>")
    if not reasoning.lstrip().startswith("<think>") and not request.rstrip().endswith("<think>"):
        text = generated_text
    text = text.strip()

    try:
        rewritten = json.loads(text).get("rewritten_prompt", "")
    except (json.JSONDecodeError, TypeError):
        rewritten = ""
    return rewritten if rewritten else prompt


def _viggle_sample_decode(pipeline, conditioning, latent_dict, steps, seed):
    """Sampler + decode tail of the viggle path: the sampling setup, the
    sampler run and the VAE decode, shared by colorize_viggle() and
    colorize_viggle_from_conditioning().

    `conditioning` is the positive conditioning the Guider consumes and
    `latent_dict` the empty latent to denoise; both come either from the live
    TextEncodeQwenImage21 node or from a cached conditioning file. Returns the
    colorized PIL image.
    """
    import nodes as cn
    from comfy_extras.nodes_qwen import QwenImage21Cache
    from comfy_extras.nodes_custom_sampler import RandomNoise, KSamplerSelect, BasicGuider, SamplerCustomAdvanced
    import importlib
    ViggleTurboSigmas = importlib.import_module("viggle_turbo").ViggleTurboSigmas

    sigma_nodes = _VIGGLE_SIGMA_SCHEDULES.get(steps)
    if sigma_nodes is None:
        logger.warning("colorize_viggle: no sigma schedule defined for steps=%s, falling back to 6 (native)", steps)
        sigma_nodes = _VIGGLE_SIGMA_NODES_6

    cached_model = get_value_at_index(
        QwenImage21Cache().EXECUTE_NORMALIZED(model=pipeline["model"], device="auto", dtype="default"), 0)
    guider = get_value_at_index(
        BasicGuider().EXECUTE_NORMALIZED(model=cached_model, conditioning=conditioning), 0)
    noise = get_value_at_index(RandomNoise().EXECUTE_NORMALIZED(noise_seed=seed), 0)
    sampler = get_value_at_index(KSamplerSelect().EXECUTE_NORMALIZED(sampler_name="euler"), 0)
    sigmas = get_value_at_index(
        ViggleTurboSigmas().get_sigmas(nodes=sigma_nodes, latent=latent_dict), 0)

    sampled = SamplerCustomAdvanced().EXECUTE_NORMALIZED(
        noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=latent_dict)
    latent_samples = get_value_at_index(sampled, 0)

    img_decoded = cn.VAEDecode().decode(samples=latent_samples, vae=pipeline["vae"])
    img_t = get_value_at_index(img_decoded, 0)

    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    img_np = img_np[..., :3]  # the Qwen-Image-2.1 VAE decode has an extra 4th channel, drop it (RGB only)
    return Image.fromarray((img_np * 255).astype(np.uint8))


def _qwen21_turbo_sample_decode(pipeline, conditioning, latent_dict, seed):
    """Sampler + decode tail of the qwen21-turbo path: the reference
    workflow's SamplerCustomAdvanced graph -- the ModelSamplingFlux "Qwen 2K
    shift" patch (max_shift 0.6935 / base_shift 0.5), QwenImage21Cache,
    BasicGuider (CFG-off) and the checkpoint's own sigma table through
    ManualSigmas.

    The shift patch is inert with an explicit sigma table (the sampler
    consumes the given sigmas directly and ModelSamplingFlux.timestep() is
    the identity); it is kept to mirror the tested workflow exactly -- it is
    what the Base schedule would need. Returns the colorized PIL image.
    """
    import nodes as cn
    from comfy_extras.nodes_model_advanced import ModelSamplingFlux
    from comfy_extras.nodes_qwen import QwenImage21Cache
    from comfy_extras.nodes_custom_sampler import (
        RandomNoise, KSamplerSelect, BasicGuider, SamplerCustomAdvanced, ManualSigmas)

    height = latent_dict["samples"].shape[-2] * 16
    width = latent_dict["samples"].shape[-1] * 16
    shifted_model = get_value_at_index(
        ModelSamplingFlux().patch(max_shift=0.6935, base_shift=0.5,
                                  width=width, height=height,
                                  model=pipeline["model"]), 0)
    cached_model = get_value_at_index(
        QwenImage21Cache().EXECUTE_NORMALIZED(model=shifted_model, device="auto", dtype="default"), 0)
    guider = get_value_at_index(
        BasicGuider().EXECUTE_NORMALIZED(model=cached_model, conditioning=conditioning), 0)
    noise = get_value_at_index(RandomNoise().EXECUTE_NORMALIZED(noise_seed=seed), 0)
    sampler = get_value_at_index(KSamplerSelect().EXECUTE_NORMALIZED(sampler_name="euler"), 0)
    sigmas = get_value_at_index(
        ManualSigmas().EXECUTE_NORMALIZED(sigmas=_QWEN21_TURBO_SIGMAS), 0)

    sampled = SamplerCustomAdvanced().EXECUTE_NORMALIZED(
        noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=latent_dict)
    latent_samples = get_value_at_index(sampled, 0)

    img_decoded = cn.VAEDecode().decode(samples=latent_samples, vae=pipeline["vae"])
    img_t = get_value_at_index(img_decoded, 0)

    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    img_np = img_np[..., :3]  # the Qwen-Image-2.1 VAE decode has an extra 4th channel, drop it (RGB only)
    return Image.fromarray((img_np * 255).astype(np.uint8))


def _viggle_encode_positive(pipeline, img_tensor, prompt, resolution):
    """The positive branch of TextEncodeQwenImage21.execute() for a single
    reference image: same area-budget resize at `resolution`, same VAE
    reference encode, same tokenize/encode call -- without the node's negative
    pass, which the viggle path never consumed (CFG-off, see colorize_viggle).

    Returns (positive_conditioning, latent_dict) exactly as the node does.
    """
    import comfy.model_management
    import comfy.utils
    import node_helpers

    samples = img_tensor[:1].movedim(-1, 1)
    if resolution > 0:
        ratio = samples.shape[3] / samples.shape[2]
        width = round(math.sqrt(resolution * resolution * ratio) / 32) * 32
        height = round(math.sqrt(resolution * resolution / ratio) / 32) * 32
    else:
        width, height = round(samples.shape[3] / 32) * 32, round(samples.shape[2] / 32) * 32
    width, height = max(32, width), max(32, height)
    if (width, height) == (samples.shape[3], samples.shape[2]):
        s = img_tensor[:1]
    else:
        s = comfy.utils.common_upscale(samples, width, height, "lanczos", "disabled").movedim(1, -1)
    rgb = s[:, :, :, :3]
    if s.shape[-1] > 3:
        rgb = rgb * s[:, :, :, 3:] + (1.0 - s[:, :, :, 3:])  # the vision tower sees alpha over white, the vae keeps all four

    # keep_vision=False: the node's behaviour with a vae present; the image
    # conditions through the reference latents, not the vision tokens.
    positive = pipeline["clip"].encode_from_tokens_scheduled(
        pipeline["clip"].tokenize(prompt, images=[rgb], keep_vision=False, prevent_empty_text=True))
    positive = node_helpers.conditioning_set_values(
        positive, {"reference_latents": [pipeline["vae"].encode(s)]}, append=True)

    latent_dict = {"samples": torch.zeros(
        [1, 64, height // 16, width // 16], device=comfy.model_management.intermediate_device())}
    return positive, latent_dict


def colorize_viggle(pipeline, image, prompt, steps=6, seed=42, enhance_prompt=False, resolution=1024):
    """Qwen-Image-2.1 + Viggle-Turbo colorization (CFG-off, Viggle-Turbo sigma schedule).

    `steps` selects one of the precomputed sigma schedules in
    `_VIGGLE_SIGMA_SCHEDULES` (2/4/6/8, tied to the v0.2.1-r128 LoRA); 6 is
    the LoRA's native step count. A `steps` value with no matching schedule
    falls back to the 6-step schedule.
    """
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        if enhance_prompt:
            try:
                prompt = _viggle_enhance_prompt(pipeline["clip"], img_tensor, prompt, seed=seed)
            except Exception:
                logger.exception("colorize_viggle: prompt enhancement failed, using the original prompt")

        # positive branch only: the node's negative pass was never consumed
        # downstream (BasicGuider/Guider_Basic injects the "positive" cond
        # alone -- CFG-off, distilled/turbo mode), so it is skipped entirely.
        positive, latent_dict = _viggle_encode_positive(pipeline, img_tensor, prompt, resolution)

        result = _viggle_sample_decode(pipeline, positive, latent_dict, steps, seed)

    return result


def encode_viggle_conditioning(pipeline, image, prompt, resolution=1024, enhance_prompt=False, seed=42):
    """Compute the viggle text-encoder conditioning for one image (phase A of
    the split-colorize flow): the positive conditioning + the empty latent,
    exactly as TextEncodeQwenImage21.execute() produces them.

    Mirrors the node's prologue (same area-budget resize at `resolution`,
    same VAE reference encode, same tokenize/encode call) for the positive
    branch only. The node's negative pass is skipped: the viggle path runs
    CFG-off and BasicGuider consumes the positive conditioning alone (see
    colorize_viggle), so the negative output was never read. Returns
    {"conditioning": ..., "latent": ..., "prompt": effective_prompt}.
    """
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        if enhance_prompt:
            try:
                prompt = _viggle_enhance_prompt(pipeline["clip"], img_tensor, prompt, seed=seed)
            except Exception:
                logger.exception("encode_viggle_conditioning: prompt enhancement failed, using the original prompt")

        positive, latent_dict = _viggle_encode_positive(pipeline, img_tensor, prompt, resolution)

    return {"conditioning": positive, "latent": latent_dict, "prompt": prompt}


def colorize_viggle_from_conditioning(pipeline, conditioning, latent_dict, steps=6, seed=42):
    """Sample + decode one image from a precomputed conditioning (phase B of
    the split-colorize flow), with the schedule of the family the pipeline
    belongs to: the viggle-turbo sigmas for qwen21-viggle, the checkpoint's
    own 8-step table for qwen21-turbo. Returns the colorized PIL image."""
    if isinstance(pipeline, dict) and pipeline.get("_model_type") == "qwen21-turbo":
        return colorize_qwen21_turbo_from_conditioning(
            pipeline, conditioning, latent_dict, steps, seed)
    with torch.inference_mode():
        result = _viggle_sample_decode(pipeline, conditioning, latent_dict, steps, seed)
    return result


def colorize_qwen21_turbo(pipeline, image, prompt, steps=8, seed=42, resolution=1024):
    """Qwen-Image-2.1-Turbo colorization (CFG-off, the checkpoint's own
    8-step sigma table).

    Same prologue as colorize_viggle() -- the aspect-preserving area-budget
    resize at `resolution` and the positive branch of TextEncodeQwenImage21
    -- followed by the turbo sampling tail. `steps` is fixed by the
    checkpoint schedule: any other value is accepted (call-shape
    compatibility) and ignored, with a warning.
    """
    if int(steps or 0) != 8:
        logger.warning("colorize_qwen21_turbo: steps=%s ignored (the turbo "
                       "checkpoint runs its own 8-step schedule)", steps)
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)
        positive, latent_dict = _viggle_encode_positive(pipeline, img_tensor, prompt, resolution)
        result = _qwen21_turbo_sample_decode(pipeline, positive, latent_dict, seed)
    return result


def colorize_qwen21_turbo_from_conditioning(pipeline, conditioning, latent_dict, steps=8, seed=42):
    """Phase B of the split-colorize flow for the qwen21-turbo family: sample
    + decode one image from a precomputed conditioning (the same
    TextEncodeQwenImage21 structure the viggle flow caches). `steps` is fixed
    by the checkpoint schedule (see colorize_qwen21_turbo). Returns the
    colorized PIL image."""
    if int(steps or 0) != 8:
        logger.warning("colorize_qwen21_turbo_from_conditioning: steps=%s ignored "
                       "(the turbo checkpoint runs its own 8-step schedule)", steps)
    with torch.inference_mode():
        return _qwen21_turbo_sample_decode(pipeline, conditioning, latent_dict, seed)


# ---------------------------------------------------------------------------
# qwen25-nunchaku: Qwen-Image-Edit 2509/2511 through the ComfyUI-nunchaku node
# ---------------------------------------------------------------------------
#
# The family runs the reference ComfyUI workflow validated on the portable
# (QWEN25_NUNCHAKU.md 2.4/2.5), not a diffusers pipeline:
#
#   ImageScaleToTotalPixels(lanczos, 1 Mpx) -> VAEEncode
#   TextEncodeQwenImageEditPlus(prompt, clip, vae, image1)   (positive)
#   ModelSamplingAuraFlow(shift=3) -> CFGNorm(1.0, pre_cfg=False)
#   -> KSampler(4, cfg 1, euler/simple) -> VAEDecode
#
# Two deliberate differences from the node graph:
#
# * the negative TextEncode pass is not computed. KSampler runs at cfg=1.0
#   and comfy/samplers.py takes the cfg1 fast path (uncond=None), so the
#   negative conditioning is never read -- the same saving the other
#   cfg-off families in this bridge make.
# * CFGNorm is kept anyway: at cfg=1 its post-cfg factor is norm(cond)/
#   norm(pred) with pred == cond, i.e. 1.0, so it is a no-op here; it stays
#   in the chain so this code and the validated GUI workflow differ only in
#   the negative pass.

_QWEN25_DEFAULT_MEGAPIXELS = 1.0


def _qwen25_prepare(image, resolution=None):
    """ImageScaleToTotalPixels(lanczos, megapixels, resolution_steps=1).

    `resolution` (long side in pixels) is the config-facing knob of the other
    families; None/0 keeps the reference 1 Mpx budget.
    """
    import comfy.utils

    if resolution:
        megapixels = (float(resolution) / 1024.0) ** 2
    else:
        megapixels = _QWEN25_DEFAULT_MEGAPIXELS

    img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
    samples = torch.from_numpy(img_np).unsqueeze(0).movedim(-1, 1)
    total = megapixels * 1024 * 1024
    scale_by = math.sqrt(total / (samples.shape[3] * samples.shape[2]))
    width = int(round(samples.shape[3] * scale_by))
    height = int(round(samples.shape[2] * scale_by))
    s = comfy.utils.common_upscale(samples, width, height, "lanczos", "disabled")
    return s.movedim(1, -1)


def _qwen25_encode_positive(pipeline, img_scaled, prompt):
    """VAE encode of the start latent + TextEncodeQwenImageEditPlus.

    The node's own VAE pass builds the reference latent the transformer sees
    (`reference_latents` in the conditioning); the explicit VAEEncode is the
    start latent. Both derive from the same 1 Mpx image, as in the reference
    graph. Returns (conditioning, latent).
    """
    import nodes as cn
    from comfy_extras.nodes_qwen import TextEncodeQwenImageEditPlus

    with _edit_profile.phase("vaeenc"):
        latent_dict = cn.VAEEncode().encode(pixels=img_scaled, vae=pipeline["vae"])[0]

    with _edit_profile.phase("te_pos"):
        _pos_raw = TextEncodeQwenImageEditPlus().EXECUTE_NORMALIZED(
            prompt=prompt,
            clip=pipeline["clip"],
            vae=pipeline["vae"],
            image1=img_scaled,
        )
        positive = get_value_at_index(_pos_raw, 0)
    return positive, latent_dict


def _qwen25_sample_decode(pipeline, conditioning, latent_dict, steps, seed):
    """AuraFlow shift 3 -> CFGNorm -> KSampler(euler/simple, cfg 1) -> decode."""
    import nodes as cn
    from comfy_extras.nodes_cfg import CFGNorm
    from comfy_extras.nodes_model_advanced import ModelSamplingAuraFlow

    with _edit_profile.phase("patch"):
        unet_sampled = ModelSamplingAuraFlow().patch_aura(
            shift=3, sampling="flow", model=pipeline["model"])[0]
        unet_sampled = get_value_at_index(
            CFGNorm().EXECUTE_NORMALIZED(model=unet_sampled, strength=1.0, pre_cfg=False), 0)

    with _edit_profile.phase("sampling"):
        sampled = cn.KSampler().sample(
            seed=seed, steps=steps, cfg=1.0,
            sampler_name="euler", scheduler="simple", denoise=1.0,
            model=unet_sampled,
            positive=conditioning, negative=conditioning,
            latent_image=latent_dict,
        )
        latent_samples = sampled[0]

    with _edit_profile.phase("decode"):
        img_decoded = cn.VAEDecode().decode(samples=latent_samples, vae=pipeline["vae"])
        return get_value_at_index(img_decoded, 0)


def colorize_qwen25_nunchaku(pipeline, image, prompt, steps=4, seed=42, resolution=None):
    """Qwen-Image-Edit 2509/2511 colorization through the Nunchaku node chain.

    `resolution` is the config-facing long-side budget (None -> the reference
    1 Mpx); `steps` is the checkpoint's own step count (4 for the Lightning
    LoRA / fused 4-step checkpoints).
    """
    _edit_profile.start_run(steps=steps, seed=seed, image=image.size)
    try:
        with torch.inference_mode():
            with _edit_profile.phase("prep"):
                img_scaled = _qwen25_prepare(image, resolution)
            positive, latent_dict = _qwen25_encode_positive(pipeline, img_scaled, prompt)
            img_t = _qwen25_sample_decode(pipeline, positive, latent_dict, steps, seed)
        with _edit_profile.phase("post"):
            return _edit_to_pil(img_t)
    finally:
        _edit_profile.end_run()


def encode_qwen25_nunchaku_conditioning(pipeline, image, prompt, resolution=None):
    """Phase A of the split flow for the qwen25-nunchaku family: the positive
    conditioning + the start latent of one image, ready for
    save_edit_conditioning() (same on-disk format as gguf-qwen)."""
    with torch.inference_mode():
        with _edit_profile.phase("prep"):
            img_scaled = _qwen25_prepare(image, resolution)
        positive, latent_dict = _qwen25_encode_positive(pipeline, img_scaled, prompt)
    return {"conditioning": positive, "latent": latent_dict}


def colorize_qwen25_nunchaku_from_conditioning(pipeline, conditioning, latent_dict, steps=4, seed=42):
    """Phase B of the split flow for qwen25-nunchaku: sample + decode one
    cached conditioning. Returns the colorized PIL image."""
    with torch.inference_mode():
        img_t = _qwen25_sample_decode(pipeline, conditioning, latent_dict, steps, seed)
    with _edit_profile.phase("post"):
        return _edit_to_pil(img_t)


# LongCat Image Edit Turbo (longcat-gguf): the split flow lives in its own
# module (comfy_bridge/longcat_colorize.py) because the family loads through
# the GGUF nodes; these wrappers keep the family dispatch in one place.

def encode_longcat_conditioning(pipeline, image, prompt):
    """Phase A of the split flow for longcat-gguf: conditioning + start latent
    of one image, ready for save_longcat_conditioning()."""
    from .longcat_colorize import encode_conditioning
    return encode_conditioning(pipeline, image, prompt)


def colorize_longcat_from_conditioning(pipeline, conditioning, latent_dict, steps=8, seed=42):
    """Phase B of the split flow for longcat-gguf: sample + decode one cached
    conditioning. Returns the colorized PIL image."""
    from .longcat_colorize import colorize_from_conditioning
    return colorize_from_conditioning(pipeline, conditioning, latent_dict, steps=steps, seed=seed)


def save_longcat_conditioning(path, conditioning, latent_dict, prompt="", meta=None):
    """Save a longcat conditioning (its own on-disk kind: the guidance and
    reference-latent method travel in the metadata)."""
    from .longcat_colorize import save_conditioning
    return save_conditioning(path, conditioning, latent_dict, prompt=prompt, meta=meta)


def load_longcat_conditioning(path):
    """Load a conditioning saved by save_longcat_conditioning()."""
    from .longcat_colorize import load_conditioning
    return load_conditioning(path)


def save_viggle_conditioning(path, conditioning, latent_dict, prompt="", prompt_original="", meta=None):
    """Save a conditioning produced by encode_viggle_conditioning() as one
    .safetensors file (float32 round-trip, ~1.4 MB per 1024-budget frame).

    Assumes the single-slot layout the viggle path uses:
    [[context, {image_slots, reference_latents, ...}]]. The structure needed
    to rebuild the conditioning is written into the file's metadata together
    with the (possibly enhanced) prompt; `meta` (extra str->str entries from
    the caller) is merged in. Returns the metadata dict written.
    """
    from safetensors.torch import save_file

    extra = conditioning[0][1]
    reference_latents = extra.get("reference_latents") or []
    if not reference_latents:
        raise ValueError("save_viggle_conditioning: conditioning has no reference_latents")
    if extra.get("pooled_output") is not None:
        raise ValueError("save_viggle_conditioning: pooled_output present (unsupported layout)")
    if extra.get("attention_mask") is not None:
        raise ValueError("save_viggle_conditioning: attention_mask present (unsupported layout)")
    tensors = {
        "context": conditioning[0][0].detach().to("cpu").contiguous(),
        "reference_latent": reference_latents[0].detach().to("cpu").contiguous(),
    }
    metadata = {
        "format": "1",
        "prompt": str(prompt),
        "prompt_original": str(prompt_original),
        "image_slots": json.dumps(list(extra.get("image_slots", []))),
    }
    if meta:
        metadata.update({str(k): str(v) for k, v in meta.items()})
    save_file(tensors, path, metadata=metadata)
    return metadata


def load_viggle_conditioning(path):
    """Load a conditioning saved by save_viggle_conditioning().

    Returns {"conditioning", "latent", "meta"}: the conditioning rebuilt in
    the same structure the live path hands to the sampler, with the empty
    latent rebuilt from the reference latent's shape. Raises ValueError when
    handed an edit conditioning file (same tensor names, different
    structure).
    """
    import comfy.model_management
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as f:
        tensors = {k: f.get_tensor(k) for k in f.keys()}
        meta = dict(f.metadata() or {})

    if meta.get("kind") == "qwen-edit-conditioning":
        raise ValueError(
            "load_viggle_conditioning: this is a qwen-edit conditioning file")
    if meta.get("kind") == "flux2-conditioning":
        raise ValueError(
            "load_viggle_conditioning: this is a flux2 conditioning file")
    if meta.get("kind") == "flux3-conditioning":
        raise ValueError(
            "load_viggle_conditioning: this is a flux3 conditioning file")

    device = comfy.model_management.get_torch_device()
    context = tensors["context"].to(device)
    reference_latent = tensors["reference_latent"].to(device)
    slots = json.loads(meta.get("image_slots", "[]"))
    conditioning = [[context, {
        "pooled_output": None,
        "image_slots": slots,
        "reference_latents": [reference_latent],
    }]]
    latent_dict = {"samples": torch.zeros_like(reference_latent)}

    return {"conditioning": conditioning, "latent": latent_dict, "meta": meta}


# ---------------------------------------------------------------------------
# FLUX.2 family (config model_name "flux2")
#
# Two sub-shapes share the graph and the loader:
#
#  * **Flux.2-dev** -- transformer (a GGUF quant through the vendored
#    ComfyUI-GGUF recipe, or the Comfy-Org fp8-mixed safetensors) + the
#    **Mistral-3** text encoder (CLIPLoader type="flux2") + the Flux2 VAE,
#    with the FLUX.2-Turbo LoRA applied at runtime and the embedded guidance
#    fed through **FluxGuidance**. Recipe of the reference workflow:
#
#      LoaderGGUF / UNETLoader -> LoraLoaderModelOnly(Turbo LoRA) -> BasicGuider
#      CLIPLoader(flux2) -> CLIPTextEncode -> FluxGuidance(4)
#          -> ReferenceLatent(latent=VAEEncode(frame))
#      Flux2Scheduler(steps, w, h) + EmptyFlux2LatentImage + RandomNoise
#          + euler -> SamplerCustomAdvanced -> VAEDecode
#
#  * **Flux.2 Klein** (9B / 4B) -- same graph with the **Qwen3** text encoder
#    (qwen_3_8b_fp8mixed / qwen_3_4b), **no LoRA**, and **no FluxGuidance**:
#    the reference workflow feeds the prompt straight into a CFGGuider with
#    cfg=1.0. At cfg 1.0 comfy's sampling_function takes the uncond=None fast
#    path (comfy/samplers.py), so the negative branch the reference graph
#    still encodes is never evaluated: BasicGuider with the same positive
#    conditioning is the same sampling, minus a wasted text-encoder pass.
#    A config asks for this shape with "guidance": 0 (see _flux2_guidance).
#
# The step count is a free parameter here (the Turbo LoRA's native value is
# 2; Klein's reference is 4), and the scheduler derives its mu-shift from the
# image sequence length, so the sigmas depend on the working size -- see
# _flux2_sample_decode().
# ---------------------------------------------------------------------------

# FluxGuidance input of the reference workflow (Flux.2-dev's embedded
# guidance); overridable per config with the "guidance" key. 0 (or negative)
# means **no FluxGuidance node at all**, which is what the Klein checkpoints
# want: their reference workflow samples through CFGGuider(cfg=1.0) instead.
FLUX2_DEFAULT_GUIDANCE = 4.0

_FLUX2_COND_KIND = "flux2-conditioning"


def _flux2_effective_guidance(pipeline, guidance=None):
    """The FluxGuidance value for this pipeline, or None when the node must be
    skipped entirely (Klein). `guidance` wins over the pipeline's own, which
    wins over the family default; a non-numeric or <= 0 value disables it."""
    value = guidance
    if value is None and isinstance(pipeline, dict):
        value = pipeline.get("_guidance")
    if value is None:
        value = FLUX2_DEFAULT_GUIDANCE
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = FLUX2_DEFAULT_GUIDANCE
    return value if value > 0 else None


def load_flux2_pipeline(unet_path, clip_path, vae_name="flux2-vae.safetensors", lora_path=None,
                        vram_headroom=None):
    """Load the FLUX.2 pipeline (transformer + Mistral-3 text encoder + VAE).

    unet_path may be a .gguf quant (ComfyUI-GGUF recipe, same one
    load_viggle_pipeline() uses for the GGUF viggle checkpoints) or a
    safetensors checkpoint (stock UNETLoader, e.g. the Comfy-Org
    flux2_dev_fp8mixed repack).

    lora_path: the FLUX.2-Turbo LoRA, applied through the stock
    LoraLoaderModelOnly node exactly as the reference workflow does; with
    lora_path empty/None the checkpoint is used as-is.

    clip_path must be a safetensors text encoder: no GGUF repack of the
    Mistral-3 Flux2 encoder exists and the Reboot loader has no flux2 TE
    recipe, so a .gguf here is rejected with an explicit message.

    vram_headroom: the config's GB of VRAM aimdo must leave free (see
    _dynamic_vram.enable / _resolve_headroom); None -> the default.
    """
    _dynamic_vram.enable(vram_headroom=vram_headroom)  # DynamicVRAM before the first model load (see _dynamic_vram)
    import importlib
    import nodes as cn

    unet_name = os.path.basename(unet_path)
    clip_name = os.path.basename(clip_path)

    logger.info("Loading Flux2 UNet: %s", unet_name)
    if unet_name.lower().endswith(".gguf"):
        _gguf_loader = importlib.import_module("ComfyUI-GGUF.loader")
        _gguf_nodes = importlib.import_module("ComfyUI-GGUF.nodes")
        _gguf_ops = importlib.import_module("ComfyUI-GGUF.ops")
        import comfy.sd
        _sd, _extra = _gguf_loader.gguf_sd_loader(unet_path)
        model = comfy.sd.load_diffusion_model_state_dict(
            _sd, model_options={"custom_operations": _gguf_ops.GGMLOps()})
        if model is None:
            raise RuntimeError(f"Failed to load UNet from {unet_path}")
        model = _gguf_nodes.GGUFModelPatcher.clone(model)
        logger.info("UNet GGUF loaded (%s)", _extra.get("arch_str", "?"))
    else:
        model = get_value_at_index(cn.UNETLoader().load_unet(unet_name=unet_name, weight_dtype="default"), 0)

    if lora_path and os.path.isfile(lora_path):
        logger.info("Applying FLUX.2-Turbo LoRA: %s", os.path.basename(lora_path))
        model = get_value_at_index(
            cn.LoraLoaderModelOnly().load_lora_model_only(
                model=model, lora_name=os.path.basename(lora_path), strength_model=1.0), 0)

    if clip_path.lower().endswith(".gguf"):
        raise ValueError(
            "load_flux2_pipeline: GGUF text encoders are not supported for flux2 "
            "(the Mistral-3 Flux2 encoder is only published as safetensors)")
    logger.info("Loading CLIP: %s", clip_name)
    clip = get_value_at_index(cn.CLIPLoader().load_clip(clip_name=clip_name, type="flux2", device="default"), 0)

    logger.info("Loading VAE: %s", vae_name)
    vae = get_value_at_index(cn.VAELoader().load_vae(vae_name=vae_name), 0)

    return {"model": model, "clip": clip, "vae": vae}


def _flux2_prepare(pipeline, img_tensor, prompt, resolution, guidance):
    """The flux2 graph's positive branch for one frame: the area-budget resize
    (same math as _viggle_encode_positive -- ~resolution^2 pixels, snapped to
    32), the VAE encode that becomes the reference latent, the CLIPTextEncode
    pass and, when `guidance` is not None, the FluxGuidance value.

    Returns (positive_conditioning, latent_dict), with latent_dict the empty
    Flux2 latent the sampler denoises (EmptyFlux2LatentImage, same shape as
    the reference latent). Mirrors the node calls of the reference workflow:
    ReferenceLatent is reproduced with node_helpers.conditioning_set_values,
    which is what that node's execute() does.
    """
    import comfy.utils
    import node_helpers
    from nodes import CLIPTextEncode, VAEEncode
    from comfy_extras.nodes_flux import EmptyFlux2LatentImage, FluxGuidance

    samples = img_tensor[:1].movedim(-1, 1)
    if resolution > 0:
        ratio = samples.shape[3] / samples.shape[2]
        width = round(math.sqrt(resolution * resolution * ratio) / 32) * 32
        height = round(math.sqrt(resolution * resolution / ratio) / 32) * 32
    else:
        width, height = round(samples.shape[3] / 32) * 32, round(samples.shape[2] / 32) * 32
    width, height = max(32, width), max(32, height)
    if (width, height) == (samples.shape[3], samples.shape[2]):
        s = img_tensor[:1]
    else:
        s = comfy.utils.common_upscale(samples, width, height, "lanczos", "disabled").movedim(1, -1)

    # VAEEncode -> ReferenceLatent (the frame conditions the transformer only
    # through this latent; the denoised latent starts empty)
    ref_latent = get_value_at_index(VAEEncode().encode(pixels=s, vae=pipeline["vae"]), 0)["samples"]

    positive = get_value_at_index(CLIPTextEncode().encode(clip=pipeline["clip"], text=prompt), 0)
    if guidance is not None:
        # Flux.2-dev: the embedded guidance travels in the conditioning. Klein
        # skips this node (its reference workflow samples through CFGGuider
        # with cfg=1.0, i.e. no guidance at all).
        positive = get_value_at_index(
            FluxGuidance().EXECUTE_NORMALIZED(conditioning=positive, guidance=float(guidance)), 0)
    positive = node_helpers.conditioning_set_values(
        positive, {"reference_latents": [ref_latent]}, append=True)

    latent_dict = get_value_at_index(
        EmptyFlux2LatentImage().EXECUTE_NORMALIZED(width=width, height=height, batch_size=1), 0)
    return positive, latent_dict


def _flux2_sample_decode(pipeline, conditioning, latent_dict, steps, seed):
    """Sampler + decode tail of the flux2 path: Flux2Scheduler (its mu-shift
    schedule is derived from the image sequence length, so the sigmas follow
    the working size), BasicGuider (CFG-off: the reference workflow never
    builds a negative conditioning), euler and the VAE decode.

    Returns the colorized PIL image.
    """
    import nodes as cn
    from comfy_extras.nodes_flux import Flux2Scheduler
    from comfy_extras.nodes_custom_sampler import (BasicGuider, KSamplerSelect,
                                                   RandomNoise, SamplerCustomAdvanced)

    height = latent_dict["samples"].shape[-2] * 16
    width = latent_dict["samples"].shape[-1] * 16

    guider = get_value_at_index(
        BasicGuider().EXECUTE_NORMALIZED(model=pipeline["model"], conditioning=conditioning), 0)
    noise = get_value_at_index(RandomNoise().EXECUTE_NORMALIZED(noise_seed=seed), 0)
    sampler = get_value_at_index(KSamplerSelect().EXECUTE_NORMALIZED(sampler_name="euler"), 0)
    sigmas = get_value_at_index(
        Flux2Scheduler().EXECUTE_NORMALIZED(steps=int(steps), width=width, height=height), 0)

    sampled = SamplerCustomAdvanced().EXECUTE_NORMALIZED(
        noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=latent_dict)
    latent_samples = get_value_at_index(sampled, 0)
    _dynamic_vram.probe_residency(pipeline.get("model"), "flux2 after-sample")

    img_decoded = cn.VAEDecode().decode(samples=latent_samples, vae=pipeline["vae"])
    img_t = get_value_at_index(img_decoded, 0)
    _dynamic_vram.probe_residency(pipeline.get("model"), "flux2 after-decode")

    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    if img_np.shape[-1] > 3:
        img_np = img_np[..., :3]  # keep RGB if the VAE decode carries extra channels
    return Image.fromarray((img_np * 255).astype(np.uint8))


def colorize_flux2(pipeline, image, prompt, steps=2, seed=42, resolution=1024, guidance=None):
    """FLUX.2 colorization of one image (the reference workflow's graph).

    `steps` is a free parameter (the Turbo LoRA's native schedule is 2 steps,
    the Klein reference is 4); `guidance` is the FluxGuidance value, defaulting
    to the pipeline's own (config key "guidance", see load_flux2_pipeline in
    dit_colorize_main.py). A value <= 0 (Klein) skips the FluxGuidance node.
    """
    effective = _flux2_effective_guidance(pipeline, guidance)
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)
        positive, latent_dict = _flux2_prepare(pipeline, img_tensor, prompt, resolution, effective)
        result = _flux2_sample_decode(pipeline, positive, latent_dict, steps, seed)
    return result


def encode_flux2_conditioning(pipeline, image, prompt, resolution=1024, guidance=None):
    """Compute the flux2 conditioning for one image (phase A of the split
    colorize flow): the CLIPTextEncode + FluxGuidance + reference-latent
    structure the live path hands to the sampler, without any sampling.

    The text encoder is prompt-only, so phase A costs one text-encoder pass
    plus one VAE encode (Mistral-3 for Flux.2-dev, Qwen3 for Klein). Returns
    {"conditioning", "latent", "prompt"} (the prompt is passed through
    unchanged: this family has no prompt enhancer). A guidance <= 0 (Klein)
    caches a conditioning with no FluxGuidance value, exactly like the live
    path.
    """
    effective = _flux2_effective_guidance(pipeline, guidance)
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)
        positive, latent_dict = _flux2_prepare(pipeline, img_tensor, prompt, resolution, effective)
    return {"conditioning": positive, "latent": latent_dict, "prompt": prompt}


def colorize_flux2_from_conditioning(pipeline, conditioning, latent_dict, steps=2, seed=42):
    """Phase B of the split-colorize flow for the flux2 family: sample + decode
    one cached conditioning. `steps` is a free parameter (Flux2Scheduler).
    """
    with torch.inference_mode():
        return _flux2_sample_decode(pipeline, conditioning, latent_dict, steps, seed)


def save_flux2_conditioning(path, conditioning, latent_dict, prompt="", prompt_original="", meta=None,
                            kind=_FLUX2_COND_KIND):
    """Save a flux2 conditioning as one .safetensors file.

    Generic over the conditioning's option dict (the Mistral-3 encoder returns
    an attention_mask alongside the context, so nothing here may assume the
    viggle layout): every tensor-valued entry -- including list entries, which
    are stored as "<key>.<index>" -- goes into the file as a tensor, scalars
    and strings go into the metadata, None-valued keys are recorded by name and
    anything else is rejected instead of silently dropped. The empty latent is
    not stored: it is rebuilt as zeros with the reference latent's shape.

    Returns the metadata dict written.
    """
    from safetensors.torch import save_file

    if len(conditioning) != 1:
        raise ValueError("save_flux2_conditioning: expected a single conditioning entry")
    context, options = conditioning[0]

    tensors = {"context": context.detach().to("cpu").contiguous()}
    values = {}
    none_keys = []
    for key, value in options.items():
        if isinstance(value, torch.Tensor):
            tensors[key] = value.detach().to("cpu").contiguous()
        elif isinstance(value, (list, tuple)) and len(value) and all(isinstance(t, torch.Tensor) for t in value):
            for i, t in enumerate(value):
                tensors[f"{key}.{i}"] = t.detach().to("cpu").contiguous()
        elif value is None:
            none_keys.append(key)
        elif isinstance(value, (bool, int, float, str)):
            values[key] = value
        else:
            raise ValueError(
                f"save_flux2_conditioning: conditioning option '{key}' "
                f"({type(value).__name__}) cannot be cached")

    if "reference_latents.0" not in tensors:
        raise ValueError("save_flux2_conditioning: conditioning has no reference_latents")

    metadata = {
        "format": "1",
        "kind": kind,
        "prompt": str(prompt),
        "prompt_original": str(prompt_original),
        "values": json.dumps(values),
        "none_keys": json.dumps(none_keys),
    }
    if meta:
        metadata.update({str(k): str(v) for k, v in meta.items()})
    save_file(tensors, path, metadata=metadata)
    return metadata


def load_flux2_conditioning(path, kind=_FLUX2_COND_KIND):
    """Load a conditioning saved by save_flux2_conditioning().

    Returns {"conditioning", "latent", "meta"} in the same structure the live
    path hands to the sampler: "<key>.<index>" tensors are gathered back into
    lists, the metadata scalars are restored with their original JSON types and
    the empty Flux2 latent is rebuilt as zeros_like(reference_latent).
    Raises ValueError when handed a conditioning file of another family.
    """
    import comfy.model_management
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as f:
        meta = dict(f.metadata() or {})
        if meta.get("kind") != kind:
            family = kind[:-len("-conditioning")] if kind.endswith("-conditioning") else kind
            raise ValueError(
                f"load_flux2_conditioning: not a {family} conditioning file")
        tensors = {k: f.get_tensor(k) for k in f.keys()}

    device = comfy.model_management.get_torch_device()
    lists = {}
    options = json.loads(meta.get("values", "{}")) if meta.get("values") else {}
    plain = {}
    for key, tensor in tensors.items():
        name, _, index = key.rpartition(".")
        if name and index.isdigit():
            lists.setdefault(name, {})[int(index)] = tensor.to(device)
        elif key != "context":
            plain[key] = tensor.to(device)
    options.update({name: [t[i] for i in sorted(t)] for name, t in lists.items()})
    options.update(plain)
    for key in json.loads(meta.get("none_keys", "[]")) if meta.get("none_keys") else []:
        options[key] = None

    conditioning = [[tensors["context"].to(device), options]]
    reference_latents = options.get("reference_latents") or []
    if not reference_latents:
        raise ValueError("load_flux2_conditioning: no reference_latents in file")
    latent_dict = {"samples": torch.zeros_like(reference_latents[0])}

    return {"conditioning": conditioning, "latent": latent_dict, "meta": meta}

# ---------------------------------------------------------------------------
# FLUX.3 family (config model_name "flux3")
#
# FLUX.3 Image Klein is ComfyUI's newest edit model (ComfyUI >= 0.42.x). Its
# graph is the Flux.2 Klein one -- Qwen3-VL text encoder, FLUX.2 VAE, the frame
# as a reference latent via the same conditioning structure -- plus two things
# of its own:
#
#  * the **timestep shift** is patched explicitly: ModelSamplingFlux with
#    max_shift = base_shift = ln(16) (alpha = 16 in the reference workflow),
#    which is a constant shift, not the resolution-derived schedule Flux.2 uses;
#  * the prompt is **upsampled per image** before the text encoder: a second,
#    much larger text encoder (Qwen3.5-9B, w4a8) reads the reference image(s)
#    and expands the short user request into a detailed instruction. This is
#    what lets the family name what it sees (a Santa suit is red, not a
#    generically "natural" garment), which is the reason the family exists
#    here. The upsampler is optional at the config level: without it the raw
#    prompt is used.
#
# Reference graph (black-forest-labs/flux-3-image-klein-comfy):
#
#   CLIPLoader(flux3, qwen3vl_4b)     -> CLIPTextEncode -> ReferenceMultiLatent
#   CLIPLoader(flux3, qwen3.5-9b)     -> TextGenerate (system prompt, 3584 tok)
#   UNETLoader(flux3-image-klein) -> ModelSamplingFlux(ln 16) -> KSampler
#       (euler / simple, cfg 1, 16 steps) -> VAEDecode
#
# Everything except the shift patch, the upsampler and the 8-step default is
# shared with the Flux.2 path: _flux2_prepare() builds the conditioning and
# the empty latent, and the cached-conditioning split flow works unchanged.
# ---------------------------------------------------------------------------

_FLUX3_COND_KIND = "flux3-conditioning"

# The reference workflow's "alpha": ModelSamplingFlux(max_shift=base_shift=
# ln(alpha)) is a constant shift of ln(alpha) (the mm term cancels out), which
# is what the distilled Klein checkpoint was trained with.
FLUX3_TIMESTEP_ALPHA = 16.0
FLUX3_TIMESTEP_SHIFT = math.log(FLUX3_TIMESTEP_ALPHA)

# TextGenerate settings of the reference workflow (nodes_textgen.py): sampling
# on, greedy-ish (temperature 1 / top_k 1), 3584 tokens, thinking off.
FLUX3_UPSAMPLER_MAX_LENGTH = 3584

# System prompt of the reference i2i workflow ("System prompt: image edit").
# It instructs the upsampler to turn the short request into one instruction for
# the editing model, grounded in the attached reference image(s).
FLUX3_UPSAMPLER_SYSTEM_PROMPT = """You are the prompt upsampler of an image-editing model. You see the reference image(s), attached in order (the first image, the second image, ...), and the user's short request. Expand it into ONE detailed, self-contained instruction: the caption the editing model receives together with the same images. Output only the instruction as one continuous English prose block, with no greetings, explanations, Markdown, JSON, coordinates, ids or angle-bracket tokens. Read a vague or conversational request as the most plausible edit of the supplied images.

Pick the voice by task shape. When one reference stays and gets bounded changes, write an imperative editing instruction on it ("Remove the ...", "Change the ... to ...", "Zoom in on ..."); a whole-image transformation opens with its scope ("Convert the entire image into ...", "Apply a ... filter over the entire scene", "Horizontally flip the entire image so that ...", "Shift the camera viewpoint to ...", then where the major elements should now be). When the references are drawn into a newly composed frame (combining subjects, a new scene, a garment, object or style donor), write a generation request ("Create a photograph of ...", "Create an anime-style illustration of ...", "Generate a new image featuring ...") that says what to take from each image, by ordinal, and what is newly generated.

Keep every explicit edit, constraint, count, position, style cue and piece of wording, and decide what is left open as one concrete plan. Ground everything in what is actually visible: identify each referent unambiguously by its real appearance, never mention content that is not there, and use every image the user attached. State every end state concretely (which color, how large, which pose, which material) and give new content enough appearance to be generated. Cover the knock-on effects of the change (shadows, reflections, occlusion, perspective, scale, lighting) and say what fills a removed region. A zoom-in names what stays in frame and which neighbors are cropped out; an outpainting continues the scene in the same medium. Describe the change, not the whole scene, and close an editing instruction with one compact clause naming what stays unchanged; transferred people keep their identity, face and accessories unless asked otherwise. Transcribe on-image text verbatim in its original language inside double quotes, with line breaks as \\n, and match the original font, size and color when replacing it. Name recognizable public figures, brands and landmarks you can see. Directions are frame-relative; use no evaluative or quality words. Typical length is 50 to 150 words.

Output only the instruction."""


def load_flux3_pipeline(unet_path, clip_path, upsampler_clip_path="", vae_name="flux2-vae.safetensors",
                        vram_headroom=None):
    """Load the FLUX.3 pipeline: transformer + Qwen3-VL text encoder + FLUX.2
    VAE, plus the optional Qwen3.5-9B prompt upsampler.

    unet_path must be a safetensors checkpoint (the BFL / community int8
    ConvRot repacks); there is no GGUF recipe for this architecture in the
    vendored loaders, so a .gguf is rejected with an explicit message.
    clip_path is the small Qwen3-VL-4B encoder (CLIPLoader type="flux3"),
    upsampler_clip_path the Qwen3.5-9B upsampler (same loader type; the
    tokenizer comes from the checkpoint itself). An empty upsampler path
    disables prompt enhancement.

    vram_headroom: the config's GB of VRAM aimdo must leave free (see
    _dynamic_vram.enable / _resolve_headroom); None -> the default.
    """
    _dynamic_vram.enable(vram_headroom=vram_headroom)  # DynamicVRAM before the first model load (see _dynamic_vram)
    import nodes as cn

    unet_name = os.path.basename(unet_path)
    clip_name = os.path.basename(clip_path)

    if unet_name.lower().endswith(".gguf"):
        raise ValueError(
            "load_flux3_pipeline: GGUF checkpoints are not supported for flux3 "
            "(no flux3 recipe in the vendored GGUF loaders); use the int8 "
            "ConvRot or bf16 safetensors checkpoint")

    logger.info("Loading Flux3 UNet: %s", unet_name)
    model = get_value_at_index(cn.UNETLoader().load_unet(unet_name=unet_name, weight_dtype="default"), 0)

    if clip_name.lower().endswith(".gguf"):
        raise ValueError(
            "load_flux3_pipeline: GGUF text encoders are not supported for flux3")
    logger.info("Loading CLIP: %s", clip_name)
    clip = get_value_at_index(cn.CLIPLoader().load_clip(clip_name=clip_name, type="flux3", device="default"), 0)

    upsampler = None
    if upsampler_clip_path:
        upsampler_name = os.path.basename(upsampler_clip_path)
        logger.info("Loading Flux3 prompt upsampler: %s", upsampler_name)
        upsampler = get_value_at_index(
            cn.CLIPLoader().load_clip(clip_name=upsampler_name, type="flux3", device="default"), 0)

    logger.info("Loading VAE: %s", vae_name)
    vae = get_value_at_index(cn.VAELoader().load_vae(vae_name=vae_name), 0)

    return {"model": model, "clip": clip, "upsampler": upsampler, "vae": vae}


def flux3_enhance_prompt(pipeline, img_tensor, prompt, seed=42,
                         max_length=FLUX3_UPSAMPLER_MAX_LENGTH):
    """Expand a short colorization request into the instruction FLUX.3 receives.

    Mirrors the reference graph's TextGenerate node (qwen3.5-9b upsampler with
    the i2i system prompt, sampling on, temperature 1 / top_k 1 / top_p 0.95 /
    no penalties, thinking off, 3584 tokens) and hands it the reference image,
    so the instruction names what is actually in the frame. Returns the
    original prompt unchanged when the pipeline has no upsampler; a failed
    generation also falls back to it instead of aborting the frame.
    """
    clip = pipeline.get("upsampler") if isinstance(pipeline, dict) else None
    if clip is None:
        return prompt
    t0 = time.perf_counter()
    try:
        tokens = clip.tokenize(prompt, image=img_tensor, skip_template=False, min_length=1,
                               thinking=False, system_prompt=FLUX3_UPSAMPLER_SYSTEM_PROMPT)
        ids = clip.generate(tokens, do_sample=True, max_length=int(max_length),
                            temperature=1.0, top_k=1, top_p=0.95, min_p=0.0,
                            repetition_penalty=1.0, presence_penalty=0.0,
                            seed=int(seed), mtp=False)
        text = clip.decode(ids)
    except Exception as exc:  # noqa: BLE001 - the frame must still be colorized
        logger.warning("flux3 prompt upsampler failed (%s); using the raw prompt", exc)
        return prompt

    # TextGenerate's </think> handling: keep what follows the closing tag, and
    # drop an unterminated reasoning block
    reasoning, sep, rest = text.partition("</think>")
    if sep:
        text = rest
    elif reasoning.lstrip().startswith("<think>"):
        text = ""
    text = text.strip() or prompt
    logger.debug("flux3 upsampler: %s", text)
    logger.info("flux3 upsampler: %d -> %d chars in %.2fs",
                len(prompt), len(text), time.perf_counter() - t0)
    return text


def _flux3_prepare(pipeline, img_tensor, prompt, resolution):
    """Conditioning + empty latent of one frame (the Flux.2 structure: the frame
    is a VAE reference latent, the DiT starts from an empty latent at the same
    working size; the area budget is `resolution`, 1 MP by default)."""
    return _flux2_prepare(pipeline, img_tensor, prompt, resolution, None)


def _flux3_sample_decode(pipeline, conditioning, latent_dict, steps, seed):
    """Sampler + decode tail of the flux3 path: the reference graph's
    ModelSamplingFlux patch (max_shift = base_shift = ln 16, a constant shift),
    KSampler with euler / simple and cfg 1 (comfy's cfg==1 fast path skips the
    negative branch entirely, so passing the positive as negative costs
    nothing), then the VAE decode.

    Returns the colorized PIL image.
    """
    import nodes as cn
    from comfy_extras.nodes_model_advanced import ModelSamplingFlux

    height = latent_dict["samples"].shape[-2] * 16
    width = latent_dict["samples"].shape[-1] * 16

    shifted_model = get_value_at_index(
        ModelSamplingFlux().patch(max_shift=FLUX3_TIMESTEP_SHIFT,
                                  base_shift=FLUX3_TIMESTEP_SHIFT,
                                  width=width, height=height,
                                  model=pipeline["model"]), 0)

    sampled = cn.KSampler().sample(
        model=shifted_model, seed=int(seed), steps=int(steps), cfg=1.0,
        sampler_name="euler", scheduler="simple",
        positive=conditioning, negative=conditioning,
        latent_image=latent_dict, denoise=1.0)
    latent_samples = get_value_at_index(sampled, 0)
    _dynamic_vram.probe_residency(pipeline.get("model"), "flux3 after-sample")

    img_decoded = cn.VAEDecode().decode(samples=latent_samples, vae=pipeline["vae"])
    img_t = get_value_at_index(img_decoded, 0)
    _dynamic_vram.probe_residency(pipeline.get("model"), "flux3 after-decode")

    if img_t.ndim == 4:
        img_np = img_t[0].cpu().float().numpy()
    else:
        img_np = img_t.cpu().float().numpy()
    img_np = np.clip(img_np, 0, 1)
    if img_np.shape[-1] > 3:
        img_np = img_np[..., :3]  # keep RGB if the VAE decode carries extra channels
    return Image.fromarray((img_np * 255).astype(np.uint8))


def colorize_flux3(pipeline, image, prompt, steps=8, seed=42, resolution=1024):
    """FLUX.3 colorization of one image (the reference i2i graph).

    The prompt upsampler runs on the full-size reference frame first (that is
    the whole point of the family: the instruction is grounded in what the
    frame shows), then the small text encoder builds the conditioning and the
    transformer samples at the `resolution` area budget (1 MP by default).
    `steps` defaults to the family's 8; the reference workflow uses 16.
    """
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)
        enhanced = flux3_enhance_prompt(pipeline, img_tensor, prompt, seed=seed)
        positive, latent_dict = _flux3_prepare(pipeline, img_tensor, enhanced, resolution)
        result = _flux3_sample_decode(pipeline, positive, latent_dict, steps, seed)
    return result


def encode_flux3_conditioning(pipeline, image, prompt, resolution=1024, seed=42):
    """Phase A of the split colorize flow for flux3: run the prompt upsampler,
    then cache the text-encoder conditioning + reference latent of one frame.

    Returns {"conditioning", "latent", "prompt", "prompt_original"}: `prompt` is
    the **upsampled** instruction (what phase B's cache was built from), so a
    resumed run reproduces exactly the same sampling without re-running the
    9B upsampler.
    """
    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)
        enhanced = flux3_enhance_prompt(pipeline, img_tensor, prompt, seed=seed)
        positive, latent_dict = _flux3_prepare(pipeline, img_tensor, enhanced, resolution)
    return {"conditioning": positive, "latent": latent_dict,
            "prompt": enhanced, "prompt_original": prompt}


def colorize_flux3_from_conditioning(pipeline, conditioning, latent_dict, steps=8, seed=42):
    """Phase B of the split-colorize flow for flux3: sample + decode one cached
    conditioning (the upsampler already ran in phase A)."""
    with torch.inference_mode():
        return _flux3_sample_decode(pipeline, conditioning, latent_dict, steps, seed)


def save_flux3_conditioning(path, conditioning, latent_dict, prompt="", prompt_original="", meta=None):
    """Save a flux3 conditioning (own kind, so a flux2 cache is never mistaken
    for one: the structure is the same, the semantics of `prompt` are not --
    it is the upsampled instruction)."""
    return save_flux2_conditioning(
        path, conditioning, latent_dict, prompt=prompt,
        prompt_original=prompt_original, meta=meta, kind=_FLUX3_COND_KIND)


def load_flux3_conditioning(path):
    """Load a conditioning saved by save_flux3_conditioning()."""
    return load_flux2_conditioning(path, kind=_FLUX3_COND_KIND)
