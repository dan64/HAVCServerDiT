"""Opt-in per-image profiler for the Qwen-Image-Edit pipeline (gguf-qwen).

Enable with HAVC_EDIT_PROFILE=1 in the process that runs ``colorize()``
(server or bench). One ``[edit-profile] ...`` line is emitted per call --
i.e. per image -- with the seconds spent in each phase, the model-load
seconds attributed to the phase that triggered them, and a VRAM snapshot.

Disabled (variable unset) the module is inert: ``start_run()`` returns
immediately, ``phase()`` is a no-op context manager and the
``comfy.model_management.load_models_gpu`` wrapper is never installed.

Phases are declared by the caller with ``phase(name)``. Model loads are
attributed by wrapping ``load_models_gpu`` on the first enabled run; the
wrapper is a plain Python function replacement, ``uninstall()`` restores
the original. A single load call that touches several models splits its
seconds evenly across their class names.
"""

import contextlib
import os
import threading
import time

ENV_VAR = "HAVC_EDIT_PROFILE"


def enabled():
    return os.environ.get(ENV_VAR, "") == "1"


class _State(threading.local):
    def __init__(self):
        self.active = False
        self.phases = {}        # phase name -> seconds (insertion order = call order)
        self.phase = None       # phase currently open, None outside
        self.loads = []         # (seconds, [model names], phase or None)
        self.meta = {}
        self.t0 = None
        self.vram_start = None  # free bytes at run start; None without CUDA
        self.vram_min = None
        self.vram_last = None


_state = _State()
_orig_load_models_gpu = None
_installed = False


def _model_name(m):
    """Class name of a patcher's inner model, for the loads report."""
    try:
        inner = getattr(m, "model", m)
        return type(inner).__name__ or "?"
    except Exception:
        return "?"


def _sample_vram():
    """Free VRAM bytes, or None when CUDA is unavailable."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info()
        return int(free)
    except Exception:
        return None


def _update_vram_min():
    free = _sample_vram()
    if free is None:
        return
    _state.vram_last = free
    if _state.vram_min is None or free < _state.vram_min:
        _state.vram_min = free


def _install_hook():
    """Install the timing wrapper on comfy.model_management.load_models_gpu.

    Returns True when the hook is active (installed now or already)."""
    global _installed, _orig_load_models_gpu
    if _installed:
        return True
    try:
        import comfy.model_management as mm
    except Exception:
        return False
    if getattr(mm, "load_models_gpu", None) is None:
        return False
    _orig_load_models_gpu = mm.load_models_gpu

    def _timed_load_models_gpu(models, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            return _orig_load_models_gpu(models, *args, **kwargs)
        finally:
            if _state.active:
                try:
                    names = [_model_name(m) for m in models]
                except Exception:
                    names = ["?"]
                _state.loads.append((time.perf_counter() - t0, names, _state.phase))

    mm.load_models_gpu = _timed_load_models_gpu
    _installed = True
    return True


def uninstall():
    """Restore the original load_models_gpu (tests / clean shutdown)."""
    global _installed, _orig_load_models_gpu
    if not _installed:
        return
    try:
        import comfy.model_management as mm
        mm.load_models_gpu = _orig_load_models_gpu
    except Exception:
        pass
    _installed = False
    _orig_load_models_gpu = None


@contextlib.contextmanager
def phase(name):
    """Time one phase of a run; inert while no enabled run is open."""
    if not _state.active:
        yield
        return
    prev = _state.phase
    t0 = time.perf_counter()
    _state.phase = name
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        _state.phases[name] = _state.phases.get(name, 0.0) + dt
        _state.phase = prev
        _update_vram_min()


def start_run(**meta):
    """Open a profiling run. No-op (False) when the profiler is disabled
    or the load hook cannot be installed."""
    if not enabled():
        return False
    if not _install_hook():
        return False
    _state.active = True
    _state.phases = {}
    _state.loads = []
    _state.phase = None
    _state.meta = dict(meta)
    _state.t0 = time.perf_counter()
    _state.vram_start = _state.vram_min = _state.vram_last = _sample_vram()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass
    return True


def end_run():
    """Close the run and emit one line; None when nothing was open."""
    if not _state.active:
        return None
    _state.active = False
    _state.phase = None
    total = time.perf_counter() - _state.t0
    _update_vram_min()
    line = _format_line(total)
    print(line, flush=True)
    return line


def _mb(nbytes):
    return int(round(nbytes / 1048576.0))


def _aggregate(loads):
    """[(seconds, [names]) ...] grouped by model name, biggest first.
    Seconds of a multi-model call are split evenly across its names."""
    acc = {}
    order = []
    for secs, names, _phase in loads:
        names = names or ["?"]
        share = secs / len(names)
        for name in names:
            if name not in acc:
                acc[name] = 0.0
                order.append(name)
            acc[name] += share
    return sorted(((n, acc[n]) for n in order), key=lambda item: -item[1])


def _phase_loads(phase_name):
    return _aggregate([(s, n, p) for (s, n, p) in _state.loads if p == phase_name])


def _total_loads():
    return _aggregate(_state.loads)


def _vram_str():
    if _state.vram_start is None:
        return "vram n/a"
    free_now = _state.vram_last if _state.vram_last is not None else _state.vram_start
    min_free = _state.vram_min if _state.vram_min is not None else _state.vram_start
    out = (f"vram free {_mb(_state.vram_start)}->{_mb(free_now)}MB "
           f"min {_mb(min_free)}MB")
    peak = None
    try:
        import torch
        if torch.cuda.is_available():
            peak = torch.cuda.max_memory_allocated()
    except Exception:
        peak = None
    if peak is not None:
        out += f" alloc_peak {_mb(peak)}MB"
    return out


def _format_line(total):
    """Deterministic one-line report of the run just closed."""
    meta = _state.meta
    try:
        w, h = meta.get("image") or (0, 0)
    except Exception:
        w, h = 0, 0
    parts = [f"[edit-profile] steps={meta.get('steps', '?')} "
             f"seed={meta.get('seed', '?')} img={w}x{h} total={total:.2f}s"]
    segs = []
    for name, secs in _state.phases.items():    # insertion order = call order
        seg = f"{name}={secs:.2f}"
        loads = _phase_loads(name)
        if loads:
            seg += "(load " + " ".join(f"{s:.2f} {n}" for n, s in loads) + ")"
        segs.append(seg)
    if segs:
        parts.append("| " + " ".join(segs))
    loads = _total_loads()
    if loads:
        parts.append("| loads " + " ".join(f"{s:.2f} {n}" for n, s in loads))
    parts.append("| " + _vram_str())
    return " ".join(parts)
