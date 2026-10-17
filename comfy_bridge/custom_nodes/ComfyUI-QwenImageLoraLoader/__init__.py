"""ussoewwin Qwen-Image LoRA code, vendored for the embedded HAVC runtime.

Source: https://github.com/ussoewwin/ComfyUI-QwenImageLoraLoader, v2.2.6
(Apache-2.0, see LICENSE). Only ``nunchaku_code/lora_qwen.py`` is vendored:
the LoRA composition engine (standard LoRA and LoKR, fused QKV/GLU handling,
AWQ and SVDQuant targets). The node classes and the dynamic wrapper are not:
HAVC composes the LoRA once, at pipeline load, on the CPU-resident model --
there is no ComfyUI graph to re-evaluate and no per-prompt recompose.

``lora.py`` is the bridge facade (``apply_qwen_lora``).
"""

__all__ = ["lora"]
