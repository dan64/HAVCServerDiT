"""Bridge-style loader for Nunchaku-quantized Qwen-Image-Edit checkpoints.

Adapted from ComfyUI-nunchaku v1.2.1 ``nodes/models/qwenimage.py``
(Apache-2.0, see ``../LICENCE.txt``). The state-dict inspection, the model
config selection and the ModelPatcher construction are upstream's; the
ComfyUI node/widget layer (``folder_paths`` lists, ``INPUT_TYPES``,
``load_model``) is replaced by :func:`load_nunchaku_qwen_model`, which takes
an absolute path and the already-resolved offload wording.

Why the split: the embedded HAVC server never builds a node graph. It needs
"load this file into a MODEL the sampler can drive", and it applies the LoRA
between the two steps -- composing a LoRA appends rows to the low-rank
buffers, so it has to happen *before* ``set_offload()`` builds the offload
manager (the manager copies/keeps the block list the composition changed).
Upstream reaches the same order indirectly, from inside its wrapper's first
forward; here it is explicit.
"""

import json
import logging
import os

import comfy.utils
from comfy import model_detection, model_management

from nunchaku.utils import (
    check_hardware_compatibility,
    get_gpu_memory,
    get_precision_from_quantization_config,
)

from .model_configs.qwenimage import NunchakuQwenImage
from .model_patcher import NunchakuModelPatcher

logger = logging.getLogger(__name__)


def load_diffusion_model_state_dict(sd: dict, metadata: dict = None, model_options: dict = None):
    """Build a Nunchaku Qwen-Image model from a loaded state dict.

    Same body as upstream (v1.2.1), with the defaults made explicit.
    ``metadata`` must carry the checkpoint's ``quantization_config``: the
    kernel precision (int4 / nvfp4) is read from it rather than from the GPU,
    which is what lets an int4 file load correctly on Blackwell too (the
    upstream nunchaku ``get_precision()`` default would pick nvfp4 there).
    """
    metadata = metadata or {}
    model_options = model_options or {}

    quantization_config = json.loads(metadata.get("quantization_config", "{}"))
    precision = get_precision_from_quantization_config(quantization_config)
    rank = quantization_config.get("rank", 32)

    dtype = model_options.get("dtype", None)

    # Allow loading unets from checkpoint files
    diffusion_model_prefix = model_detection.unet_prefix_from_state_dict(sd)
    temp_sd = comfy.utils.state_dict_prefix_replace(sd, {diffusion_model_prefix: ""}, filter_keys=True)
    if len(temp_sd) > 0:
        sd = temp_sd

    parameters = comfy.utils.calculate_parameters(sd)
    weight_dtype = comfy.utils.weight_dtype(sd)

    load_device = model_management.get_torch_device()
    check_hardware_compatibility(quantization_config, load_device)

    model_config = NunchakuQwenImage(
        {"image_model": "qwen_image", "scale_shift": 0, "rank": rank, "precision": precision}
    )
    model_config.optimizations["fp8"] = False

    new_sd = sd

    offload_device = model_management.unet_offload_device()
    unet_weight_dtype = list(model_config.supported_inference_dtypes)
    if model_config.scaled_fp8 is not None:
        weight_dtype = None

    if dtype is None:
        unet_dtype = model_management.unet_dtype(
            model_params=parameters, supported_dtypes=unet_weight_dtype, weight_dtype=weight_dtype
        )
    else:
        unet_dtype = dtype

    manual_cast_dtype = model_management.unet_manual_cast(
        unet_dtype, load_device, model_config.supported_inference_dtypes
    )
    model_config.set_inference_dtype(unet_dtype, manual_cast_dtype)
    model_config.custom_operations = model_options.get("custom_operations", model_config.custom_operations)
    if model_options.get("fp8_optimizations", False):
        model_config.optimizations["fp8"] = True

    model = model_config.get_model(new_sd, "")
    model = model.to(offload_device)
    model.load_model_weights(new_sd, "")
    return NunchakuModelPatcher(model, load_device=load_device, offload_device=offload_device)


def load_nunchaku_qwen_model(model_path: str, dtype=None):
    """Load one Nunchaku Qwen-Image checkpoint and return its ModelPatcher.

    The model is left on the offload device (CPU) with CPU offload *off*:
    the caller composes the LoRA on it, then calls :func:`configure_offload`
    with the settings of its config.
    """
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Nunchaku checkpoint not found: {model_path}")

    logger.info("Loading Nunchaku Qwen-Image checkpoint: %s", os.path.basename(model_path))
    sd, metadata = comfy.utils.load_torch_file(model_path, return_metadata=True)
    quant = json.loads((metadata or {}).get("quantization_config", "{}"))
    logger.info(
        "Checkpoint quantization: precision=%s rank=%s",
        quant.get("precision", "?"), quant.get("rank", "?"),
    )
    return load_diffusion_model_state_dict(sd, metadata=metadata, model_options={"dtype": dtype})


def configure_offload(model, cpu_offload: str = "auto", num_blocks_on_gpu: int = 1,
                      use_pin_memory: str = "disable") -> bool:
    """Apply the CPU-offload policy to a loaded Nunchaku model.

    ``cpu_offload``: ``auto`` (upstream rule: on when the card reports less
    than 15 GiB), ``enable`` or ``disable``. Returns whether offload ended up
    enabled. Must run *after* any LoRA composition: the manager is built from
    the block list, whose low-rank buffers the composition resizes.
    """
    mode = (cpu_offload or "auto").strip().lower()
    if mode == "auto":
        try:
            gpu_gb = get_gpu_memory()
        except Exception as exc:  # pragma: no cover - no CUDA / probe failure
            logger.warning("get_gpu_memory() failed (%s): enabling CPU offload", exc)
            enabled = True
        else:
            enabled = gpu_gb < 15
            logger.info("VRAM %.1f GiB -> %s CPU offload", gpu_gb, "enabling" if enabled else "disabling")
    elif mode == "enable":
        enabled = True
    elif mode == "disable":
        enabled = False
    else:
        raise ValueError(f"Invalid cpu_offload option: {cpu_offload!r} (auto|enable|disable)")

    if not enabled:
        return False

    pin = str(use_pin_memory).strip().lower() == "enable"
    blocks = max(1, int(num_blocks_on_gpu))
    model.model.diffusion_model.set_offload(
        True, num_blocks_on_gpu=blocks, use_pin_memory=pin)
    logger.info("CPU offload enabled: num_blocks_on_gpu=%d use_pin_memory=%s", blocks, pin)
    return True
