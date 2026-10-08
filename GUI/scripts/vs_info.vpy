# Imports
import importlib.util
import os
import vapoursynth as vs

# Video-info probe (used by the GUI via `vspipe --info`): it must answer
# immediately, so the LSMASH source filter is loaded directly from the
# plugin bundled in vscmnet2 — importing vscmnet2 here would instead pull
# in torch and cost ~4 s on every call (measured 2026-10-08; ~0.3 s without
# the import). `find_spec` locates the package without importing it; if
# anything is missing the probe falls back to the full vscmnet2 reader.
core = vs.core
_dll = None
_spec = importlib.util.find_spec("vscmnet2")
if _spec is not None and _spec.origin:
    _dll = os.path.join(os.path.dirname(_spec.origin), "plugins",
                        "SourceFilter", "LSmashSource", "LSMASHSource.dll")

_loaded = False
if _dll and os.path.isfile(_dll):
    try:
        core.std.LoadPlugin(path=_dll)
        _loaded = True
    except Exception:
        _loaded = False

if _loaded:
    clip = core.lsmas.LWLibavSource(source=VideoPath, stream_index=0,
                                    fpsnum=0, fpsden=1, cache=0,
                                    prefer_hw=0)
else:
    # Fallback — the full package (slower first call, but always correct).
    import vscmnet2 as cmnet2
    clip = cmnet2.vs_read_video(source=VideoPath, return_rgb=False)

# output
clip.set_output()
