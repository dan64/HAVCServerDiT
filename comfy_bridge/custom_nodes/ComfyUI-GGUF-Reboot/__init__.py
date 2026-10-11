# Trimmed vendored copy for comfy_bridge (HAVCServerDiT): loader.py
# (gguf_clip_loader) + ops.py (GGMLOps) + their dequant.py / quant_ops.py /
# kquant_backend.py dependencies; the two are kept for qwen21-viggle's CLIP
# loaded from GGUF+mmproj. Source: molbal/ComfyUI-GGUF (GGUF-Reboot),
# tag v26-10-11 (2026-10-11); the previous copy was 48de657 (v26-09-04+6).
# kquant_triton_backend.py is the optional bundled K-quant backend (only
# imported when COMFYUI_GGUF_KQUANT_BACKEND=bundled; triton is not shipped).
# The upstream __init__.py unconditionally does
# "from .nodes import NODE_CLASS_MAPPINGS" (ComfyUI custom-node
# registration, unused here -- comfy_bridge imports submodules directly by
# dotted path, it never scans custom_nodes/ for NODE_CLASS_MAPPINGS) which
# in turn needs nodes.py -> tools/convert.py -> a bare "from lora import"
# (absolute, not relative -- only resolves when this folder itself is on
# sys.path, an assumption that doesn't hold here). nodes.py/lora.py/tools/
# were deliberately not copied to avoid vendoring that unused, fragile
# chain -- do not re-add "from .nodes import ..." here without also
# copying and fixing that chain.
