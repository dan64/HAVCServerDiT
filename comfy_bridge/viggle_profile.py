"""Opt-in per-image profiler for the viggle colorize path (dev tool; see VIGGLE_FAST.md).

When the environment variable `HAVC_VIGGLE_PROFILE` is truthy (1/true/yes/on),
every `colorize_viggle()` call logs one summary line with:

- the wall time per phase (prep / enhance / encode / setup / sampling / decode / post);
- the model loads that happened inside each phase (name + duration), fed by
  `comfy.model_management.load_models_gpu()`;
- the prefix-KV cache decisions taken during sampling (fill/reuse/recompute/off),
  fed by `comfy/ldm/qwen_image21/model.py`;
- the VRAM sampled at the phase boundaries.

The hooks are inert while disabled: the call sites pay a single flag check and
`phase()` returns a shared no-op context manager, so an unprofiled run behaves
exactly like before this module existed. The state is a module-level singleton:
the inference path is serialized (the server runs one job at a time), which is
the only usage this profiler is written for. A run that raises logs nothing;
the failure is reported by the caller as usual.
"""

import logging
import os
import time

logger = logging.getLogger("comfy_bridge.viggle_profile")

_TRUTHY = {"1", "true", "yes", "on"}


def _parse_env(value):
    """Truthy env values for HAVC_VIGGLE_PROFILE; anything else is off."""
    return str(value).strip().lower() in _TRUTHY


ENABLED = _parse_env(os.environ.get("HAVC_VIGGLE_PROFILE", ""))


def enable():
    """Force the profiler on (the env var is read only at import time)."""
    global ENABLED
    ENABLED = True


def disable():
    global ENABLED
    ENABLED = False


def _now():
    return time.perf_counter()


def _mem_snapshot():
    """Device free/total + torch allocator state, or None without CUDA."""
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return {"free": free, "total": total, "alloc": torch.cuda.memory_allocated()}
    except Exception:
        pass
    return None


def _fmt_s(seconds):
    return f"{seconds:.2f}"


def _fmt_mb(nbytes):
    return f"{int(nbytes / (1024 * 1024))}MB"


class _NoopPhase:
    """Shared no-op context manager used while the profiler is off."""

    __slots__ = ()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_NOOP_PHASE = _NoopPhase()


class _Phase:
    __slots__ = ("_run", "_name", "_t0")

    def __init__(self, run, name):
        self._run = run
        self._name = name
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = _now()
        self._run.stack.append(self._name)
        return self

    def __exit__(self, *exc):
        elapsed = _now() - self._t0
        if self._run.stack and self._run.stack[-1] == self._name:
            self._run.stack.pop()
        self._run.record_phase(self._name, elapsed)
        return False


class _Run:
    """State for one profiled colorize call."""

    __slots__ = ("active", "label", "fields", "total", "phases", "order",
                 "stack", "loads", "cache", "cache_store", "cache_dtype",
                 "cache_size", "mem_first", "mem_last", "mem_min_free",
                 "mem_peak_alloc", "_t0")

    def __init__(self):
        self.active = False

    def start(self, label=None, **fields):
        self.active = True
        self.label = label
        self.fields = dict(fields)
        self.total = 0.0
        self.phases = {}
        self.order = []
        self.stack = []
        self.loads = []  # (phase-or-None, model name, seconds)
        self.cache = []
        self.cache_store = None
        self.cache_dtype = None
        self.cache_size = None
        self.mem_first = _mem_snapshot()
        self.mem_last = self.mem_first
        self.mem_min_free = self.mem_first["free"] if self.mem_first else None
        self.mem_peak_alloc = self.mem_first["alloc"] if self.mem_first else None
        self._t0 = _now()

    def sample_mem(self):
        snap = _mem_snapshot()
        if snap is None:
            return
        self.mem_last = snap
        if self.mem_min_free is None or snap["free"] < self.mem_min_free:
            self.mem_min_free = snap["free"]
        if self.mem_peak_alloc is None or snap["alloc"] > self.mem_peak_alloc:
            self.mem_peak_alloc = snap["alloc"]

    def record_phase(self, name, seconds):
        if name not in self.phases:
            self.phases[name] = 0.0
            self.order.append(name)
        self.phases[name] += max(0.0, seconds)
        self.sample_mem()

    def current_phase(self):
        return self.stack[-1] if self.stack else None

    def mark_load(self, name, seconds):
        self.loads.append((self.current_phase(), name, max(0.0, seconds)))

    def mark_cache(self, decision, store=None, dtype=None, size=None):
        self.cache.append(decision)
        if store is not None:
            self.cache_store = str(store)
        if dtype is not None:
            self.cache_dtype = str(dtype)
        if size is not None:
            self.cache_size = size

    def _loads_by_phase(self):
        agg = {}
        for phase, name, seconds in self.loads:
            key = phase or "other"
            total, names = agg.get(key, (0.0, []))
            agg[key] = (total + seconds, names + [name])
        return agg

    def format_line(self):
        parts = ["[viggle-profile]"]
        if self.label:
            parts.append(str(self.label))
        for key, value in self.fields.items():
            parts.append(f"{key}={value}")
        total = max(0.0, self.total)
        parts.append(f"total={_fmt_s(total)}s")
        loads = self._loads_by_phase()
        phase_bits = []
        accounted = 0.0
        for name in self.order:
            seconds = self.phases[name]
            accounted += seconds
            bit = f"{name}={_fmt_s(seconds)}"
            if name in loads:
                l_total, l_names = loads[name]
                shown = ",".join(l_names[:3]) + (f",+{len(l_names) - 3}" if len(l_names) > 3 else "")
                bit += f"(load {_fmt_s(l_total)} {shown})"
            phase_bits.append(bit)
        other = total - accounted
        if other > 0.05:
            phase_bits.append(f"unaccounted={_fmt_s(other)}")
        if phase_bits:
            parts.append("| " + " ".join(phase_bits))
        if self.loads:
            parts.append("| loads " + " ".join(f"{_fmt_s(secs)} {name}" for _, name, secs in self.loads))
        if "other" in loads:  # loads that never fell inside a phase (should not happen)
            l_total, l_names = loads["other"]
            parts.append("| other-load=" + _fmt_s(l_total) + " " + ",".join(l_names[:3]))
        if self.cache:
            seg = ">".join(self.cache)
            if self.cache_store:
                seg += f" store={self.cache_store}"
            if self.cache_dtype:
                seg += f" dtype={self.cache_dtype}"
            if self.cache_size is not None:
                seg += " " + _fmt_mb(self.cache_size)
            parts.append("| cache: " + seg)
        if self.mem_first is not None:
            bits = [f"free {_fmt_mb(self.mem_first['free'])}->{_fmt_mb(self.mem_last['free'])}"]
            if self.mem_min_free is not None:
                bits.append(f"min {_fmt_mb(self.mem_min_free)}")
            if self.mem_peak_alloc is not None:
                bits.append(f"alloc_peak {_fmt_mb(self.mem_peak_alloc)}")
            parts.append("| vram " + " ".join(bits))
        return " ".join(parts)

    def end(self):
        if not self.active:
            return None
        self.total = _now() - self._t0
        self.active = False
        self.sample_mem()
        return self.format_line()


_RUN = _Run()


def start_run(label=None, **fields):
    """Begin a profiling run; no-op while disabled."""
    if ENABLED:
        _RUN.start(label=label, **fields)


def end_run():
    """Close the run and emit the summary line; no-op while disabled."""
    if ENABLED:
        line = _RUN.end()
        if line:
            logger.info(line)


def phase(name):
    """Context manager timing one phase; a shared no-op while disabled."""
    if ENABLED and _RUN.active:
        return _Phase(_RUN, name)
    return _NOOP_PHASE


def load_begin():
    """Start timing a model load; returns a token, or None when not profiling."""
    if ENABLED and _RUN.active:
        return _now()
    return None


def load_end(token, names):
    """Record a completed load (empty names -> nothing to report)."""
    if token is None or not names:
        return
    names = list(dict.fromkeys(names))
    label = names[0] if len(names) == 1 else "+".join(names)
    _RUN.mark_load(label, _now() - token)


def mark_cache(decision, store=None, dtype=None, size=None):
    """Record one prefix-KV cache decision; no-op while disabled."""
    if ENABLED and _RUN.active:
        _RUN.mark_cache(decision, store=store, dtype=dtype, size=size)
