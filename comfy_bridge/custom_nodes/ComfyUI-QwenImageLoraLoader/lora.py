"""Bridge facade over the vendored ussoewwin LoRA composition engine.

``compose_loras_v2`` merges the LoRA into the SVDQuant low-rank buffers
(``proj_down``/``proj_up``) of the Nunchaku transformer -- there is no
runtime hook and nothing to unload per prompt. It must therefore run once,
against the *diffusion model module*, before the CPU-offload manager is
built: the composition appends rows/columns to the buffers the manager
snapshots (see ``ComfyUI-nunchaku.loader.configure_offload``).
"""

import logging

from .nunchaku_code.lora_qwen import compose_loras_v2, reset_lora_v2

logger = logging.getLogger(__name__)


def apply_qwen_lora(model_patcher, lora_path: str, strength: float = 1.0) -> int:
    """Compose one LoRA into a loaded Nunchaku Qwen model.

    ``model_patcher`` is the wrapper returned by the Nunchaku loader (its
    ``.model.diffusion_model`` is the quantized transformer). Returns the
    number of patched modules; raises when the LoRA matched nothing, so a
    silent "LoRA ignored" cannot reach the sampler.
    """
    diffusion_model = model_patcher.model.diffusion_model
    logger.info("Composing LoRA: %s (strength=%.3f)", lora_path, float(strength))
    compose_loras_v2(diffusion_model, [(lora_path, float(strength))])
    slots = getattr(diffusion_model, "_lora_slots", None) or {}
    if not slots:
        raise RuntimeError(
            f"LoRA '{lora_path}' matched no module of the Nunchaku Qwen "
            "transformer (wrong architecture or unsupported format)")
    logger.info("LoRA composed into %d modules", len(slots))
    return len(slots)


def reset_qwen_lora(model_patcher) -> None:
    """Drop every composed LoRA from a loaded Nunchaku Qwen model."""
    reset_lora_v2(model_patcher.model.diffusion_model)
