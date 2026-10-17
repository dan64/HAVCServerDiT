"""ComfyUI-nunchaku core, vendored for the embedded HAVC runtime.

Source: https://github.com/mit-han-lab/ComfyUI-nunchaku, tag v1.2.1
(Apache-2.0, see LICENCE.txt). Only the model/loader half is vendored: the
ComfyUI node classes, the widget layer and the asset installers stay out --
the bridge imports this package directly (same pattern as ComfyUI-GGUF) and
drives it through ``loader.load_nunchaku_qwen_model()``.

Files are byte-identical to upstream v1.2.1:

    models/qwenimage.py         quantized transformer (SVDQuant blocks)
    model_base/qwenimage.py     QwenImage model base with the nunchaku unet
    model_configs/qwenimage.py  supported_models wrapper
    model_patcher.py            ModelPatcher that moves the module with to_safely()
    mixins/model.py             to_safely()/offload mixin

v1.2.1 is the first release compatible with the current ComfyUI core API
(``additional_t_cond`` instead of the removed ``guidance`` argument,
``timestep_zero_index``, ``default_ref_method``); the bridge core already
speaks that API (comfy/ldm/qwen_image/model.py).

Adapted: ``loader.py`` (upstream ``nodes/models/qwenimage.py`` minus the
folder_paths/widget layer). Everything bridge-specific lives there.
"""

__all__ = ["loader"]
