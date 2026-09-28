# Trimmed vendored copy for comfy_bridge (HAVCServerDiT_dev): only loader.py
# (gguf_clip_loader) + ops.py (GGMLOps) + their dequant.py/quant_ops.py
# dependencies are used, to load qwen21-viggle's CLIP from GGUF+mmproj.
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
