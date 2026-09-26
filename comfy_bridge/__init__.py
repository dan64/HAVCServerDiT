"""
comfy_bridge  :  ComfyUI-native GGUF inference, self-contained.
No dependency on external ComfyUI installation.
"""

import sys, os, torch, logging, json, numpy as np
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


def load_viggle_pipeline(unet_path, clip_path, vae_name="qwen_image_2.1_vae_bf16.safetensors", lora_path=None):
    """Load Qwen-Image-2.1 (native ComfyUI int8 ConvRot) + Viggle-Turbo LoRA (unmerged)."""
    import importlib
    ViggleTurboLora = importlib.import_module("viggle_turbo").ViggleTurboLora
    import nodes as cn

    unet_name = os.path.basename(unet_path)
    clip_name = os.path.basename(clip_path)

    logger.info("Loading UNet: %s", unet_name)
    model = get_value_at_index(cn.UNETLoader().load_unet(unet_name=unet_name, weight_dtype="default"), 0)

    if lora_path and os.path.isfile(lora_path):
        logger.info("Applying Viggle-Turbo LoRA: %s", os.path.basename(lora_path))
        model = get_value_at_index(
            ViggleTurboLora().load(model=model, lora_name=os.path.basename(lora_path), strength=1.0), 0)

    logger.info("Loading CLIP: %s", clip_name)
    clip = get_value_at_index(cn.CLIPLoader().load_clip(clip_name=clip_name, type="qwen_image", device="default"), 0)

    logger.info("Loading VAE: %s", vae_name)
    vae = get_value_at_index(cn.VAELoader().load_vae(vae_name=vae_name), 0)

    return {"model": model, "clip": clip, "vae": vae}


_VIGGLE_SIGMA_NODES_2 = "1.0, 0.25"
_VIGGLE_SIGMA_NODES_4 = "1.0, 0.875, 0.5, 0.25"
_VIGGLE_SIGMA_NODES_6 = "1.0, 0.9375, 0.875, 0.75, 0.5, 0.25"  # v0.2.1-r128 LoRA, native step count
_VIGGLE_SIGMA_NODES_8 = "1.0, 0.96875, 0.9375, 0.90625, 0.875, 0.75, 0.5, 0.25"

_VIGGLE_SIGMA_SCHEDULES = {
    2: _VIGGLE_SIGMA_NODES_2,
    4: _VIGGLE_SIGMA_NODES_4,
    6: _VIGGLE_SIGMA_NODES_6,
    8: _VIGGLE_SIGMA_NODES_8,
}

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
    execute(), without mtp/use_quantized_matmul -- decision in REPORT_07:
    those are speed optimizations, not correctness, and comfy_bridge's
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


def colorize_viggle(pipeline, image, prompt, steps=6, seed=42, enhance_prompt=False):
    """Qwen-Image-2.1 + Viggle-Turbo colorization (CFG-off, Viggle-Turbo sigma schedule).

    `steps` selects one of the precomputed sigma schedules in
    `_VIGGLE_SIGMA_SCHEDULES` (2/4/6/8, tied to the v0.2.1-r128 LoRA); 6 is
    the LoRA's native step count. A `steps` value with no matching schedule
    falls back to the 6-step schedule.
    """
    sigma_nodes = _VIGGLE_SIGMA_SCHEDULES.get(steps)
    if sigma_nodes is None:
        logger.warning("colorize_viggle: no sigma schedule defined for steps=%s, falling back to 6 (native)", steps)
        sigma_nodes = _VIGGLE_SIGMA_NODES_6

    import nodes as cn
    from comfy_extras.nodes_qwen import TextEncodeQwenImage21, QwenImage21Cache
    from comfy_extras.nodes_custom_sampler import RandomNoise, KSamplerSelect, BasicGuider, SamplerCustomAdvanced
    import importlib
    ViggleTurboSigmas = importlib.import_module("viggle_turbo").ViggleTurboSigmas

    with torch.inference_mode():
        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        if enhance_prompt:
            try:
                prompt = _viggle_enhance_prompt(pipeline["clip"], img_tensor, prompt, seed=seed)
            except Exception:
                logger.exception("colorize_viggle: prompt enhancement failed, using the original prompt")

        # negative_prompt is a required input on this node but is never consumed
        # downstream: BasicGuider/Guider_Basic only injects the "positive" cond
        # (no CFG, distilled/turbo mode) -- see REPORT_01 sections 1 and 3.
        text_out = TextEncodeQwenImage21().EXECUTE_NORMALIZED(
            clip=pipeline["clip"],
            prompt=prompt,
            negative_prompt="",
            vae=pipeline["vae"],
            resolution=1024,
            images={"image_1": img_tensor},
        )
        positive = get_value_at_index(text_out, 0)
        latent_dict = get_value_at_index(text_out, 2)

        cached_model = get_value_at_index(
            QwenImage21Cache().EXECUTE_NORMALIZED(model=pipeline["model"], device="auto", dtype="default"), 0)
        guider = get_value_at_index(
            BasicGuider().EXECUTE_NORMALIZED(model=cached_model, conditioning=positive), 0)
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