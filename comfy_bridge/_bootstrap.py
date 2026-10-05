import os, sys
# Make comfy_bridge self-contained
_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BRIDGE_DIR not in sys.path:
    sys.path.insert(0, _BRIDGE_DIR)
_CUSTOM = os.path.join(_BRIDGE_DIR, "custom_nodes")
if _CUSTOM not in sys.path:
    sys.path.insert(0, _CUSTOM)

# Point models directory to comfy_bridge/models (self-contained), or to the
# unified models folder when the launcher provides HAVC_MODELS_DIR (Fase 1).
_models_root = os.environ.get("HAVC_MODELS_DIR")
if _models_root:
    os.environ["COMFYUI_MODELS_DIR"] = os.path.join(_models_root, "comfy")
else:
    os.environ["COMFYUI_MODELS_DIR"] = os.path.join(_BRIDGE_DIR, "models")
