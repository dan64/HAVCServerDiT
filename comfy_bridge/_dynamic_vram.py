"""DynamicVRAM (comfy-aimdo) bootstrap for the embedded ComfyUI core.

ComfyUI's ``main.py`` switches the allocator over to comfy-aimdo when that
package is installed and the platform supports it::

    comfy_aimdo.control.init(...)                # process setup (pre-torch)
    ...
    comfy_aimdo.control.init_devices(...)        # per-device hooks
    comfy.model_patcher.CoreModelPatcher = comfy.model_patcher.ModelPatcherDynamic
    comfy.memory_management.aimdo_enabled = True

With that in place a model is staged in RAM and its weights are faulted into
VRAM on demand (``ModelPatcherDynamic``) instead of going through the classic
lowvram patch streaming of the legacy ``ModelPatcher``. A server that embeds
the core without running ``main.py`` -- this one -- keeps the legacy path,
which is measurably slower on a VRAM-constrained card: on the RTX 5070 Ti
16 GB the same FLUX.2 fp8 2-step pass runs at 4.4 s/step in ComfyUI v0.37
("Model Flux2 prepared for dynamic VRAM loading. 33813MB Staged") against the
6.5 s/step of the legacy path ("loaded partially; ... lowvram patches: 115"),
with a byte-identical core (2026-10-14 logs).

``init_process()`` mirrors the process half of that bootstrap and runs before
torch is imported (``comfy_bridge/__init__.py`` calls it); ``enable()``
mirrors the device half and must run before the first model is loaded (the
pipeline loaders call it). Both are idempotent and never raise: any failure
leaves the legacy ``ModelPatcher`` in place, exactly like the "No working
comfy-aimdo install detected" branch of ``main.py``.

Set ``HAVC_DYNAMIC_VRAM=0`` to skip both steps -- the equivalent of ComfyUI's
``--disable-dynamic-vram``. When the ComfyUI CLI arguments are visible they
are honoured as well (``--cpu``, ``--highvram``, ``--disable-dynamic-vram``,
``--reserve-vram``, ``--vram-headroom``, ``--disable-nvml-pressure``); with
the defaults of a plain launch this is the same configuration the reference
workflow runs with.
"""

import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

# HAVC_DYNAMIC_VRAM values that keep the legacy ModelPatcher.
_DISABLE_VALUES = {"0", "false", "no", "off", "disable", "disabled"}

_lock = threading.Lock()
_process_initialized = False
_process_ok = False
_enabled = None  # None = not evaluated yet, True/False once decided

# ---------------------------------------------------------------------------
# Between-units allocator flush (HAVC_UNIT_FLUSH)
#
# comfy-aimdo's README: "you should generally do completely flush the pytorch
# caching allocator before each new model run, which avoids completely un-used
# reservations from taking priority over the next models weights". Our phase-B
# loop re-stages the UNet once per unit (one frame, or one pair canvas), so the
# documented hygiene belongs between two units. ComfyUI's own prompt loop does
# exactly this -- gc.collect() + soft_empty_cache(), gated to at most once per
# 10 s (main.py, gc_collect_interval) -- and is the environment where the int4
# checkpoint ran its batches cleanly.
# ---------------------------------------------------------------------------
_FLUSH_OFF = {"0", "false", "no", "off", "disable", "disabled", "never"}
_FLUSH_ON = {"1", "true", "yes", "on", "force"}
_DEFAULT_FLUSH_INTERVAL = 10.0  # ComfyUI's gc_collect_interval

_flush_last = 0.0
_flush_lock = threading.Lock()


def _flush_setting():
    """The flush interval in seconds from HAVC_UNIT_FLUSH, or None to disable.

    * unset -> auto: the default interval while DynamicVRAM is active, off
      otherwise (the comfy-aimdo advice is about its own staged weights)
    * "0" / "off" / "false" / "no" / "disable" -> disabled
    * "1" / "on" / "true" / "yes" / "force" -> enabled, default interval
    * a positive number -> that interval in seconds (use a tiny value, e.g.
      "0.001", to flush after *every* unit)
    """
    raw = os.environ.get("HAVC_UNIT_FLUSH", "").strip().lower()
    if not raw:
        return _DEFAULT_FLUSH_INTERVAL if _enabled else None
    if raw in _FLUSH_OFF:
        return None
    if raw in _FLUSH_ON:
        return _DEFAULT_FLUSH_INTERVAL
    try:
        secs = float(raw)
    except ValueError:
        logger.warning("HAVC_UNIT_FLUSH=%r is neither a switch nor a number: "
                       "using the default", raw)
        return _DEFAULT_FLUSH_INTERVAL if _enabled else None
    return secs if secs > 0 else None


def flush_interval():
    """Seconds between allocator flushes, or None when the feature is off."""
    return _flush_setting()


def flush_between_units():
    """Allocator hygiene between two units of a phase-B loop (never raises).

    Mirrors ComfyUI's prompt loop (gc.collect + soft_empty_cache, at most once
    per interval) and comfy-aimdo's advice to flush the caching allocator before
    each new model run. Controlled by HAVC_UNIT_FLUSH (see _flush_setting):
    default off unless DynamicVRAM is active, where it uses a 10 s gate.
    Returns True when a flush actually ran.
    """
    global _flush_last
    interval = _flush_setting()
    if interval is None:
        return False
    now = time.monotonic()
    with _flush_lock:
        if interval > 0 and (now - _flush_last) < interval:
            return False
        _flush_last = now
    try:
        import gc

        import comfy.model_management

        gc.collect()
        comfy.model_management.soft_empty_cache()
    except Exception as exc:  # never break a colorize run for hygiene
        logger.debug("flush_between_units: %s", exc)
        return False
    if os.environ.get("HAVC_AIMDO_PROBE"):
        logger.info("aimdo probe [flush]: allocator flushed between units")
    return True


# ---------------------------------------------------------------------------
# Residency probe (HAVC_AIMDO_PROBE=1)
#
# Diagnostic for the DynamicVRAM staging tail: aimdo faults weights in on
# demand and, once a page has been evicted, sets a watermark so that weights
# above it fail the fault and get copied to a temporary buffer at every layer
# call instead of staying resident (see comfy-aimdo's README). Which of the two
# regimes a unit lands in is what makes the same pass take 7 s or 18 s. This
# logs, around the sampling and the decode, the VBAR's own counters plus the
# driver's free VRAM and the pytorch allocator's figures, so the two regimes
# can be told apart from a log instead of guessed from timings.
#
# Off unless HAVC_AIMDO_PROBE is set: no behaviour change, no cost.
# ---------------------------------------------------------------------------


def probe_vram():
    """(driver_free_mb, driver_total_mb, torch_reserved_mb, torch_alloc_mb)."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free_b, total_b = torch.cuda.mem_get_info()
        dev = torch.cuda.current_device()
        return (free_b / 2 ** 20, total_b / 2 ** 20,
                torch.cuda.memory_reserved(dev) / 2 ** 20,
                torch.cuda.memory_allocated(dev) / 2 ** 20)
    except Exception:
        return None


def probe_residency(model, label=""):
    """Log the aimdo VBAR stats of one ModelPatcher (HAVC_AIMDO_PROBE only).

    Reports: VBAR loaded bytes / watermark / resident pages, the driver's free
    VRAM and the pytorch allocator's reserved+allocated bytes. Returns the dict
    it logged, or None when the probe is off or the model has no VBAR.
    """
    if not os.environ.get("HAVC_AIMDO_PROBE"):
        return None
    info = {"label": label}
    try:
        vbars = getattr(getattr(model, "model", None), "dynamic_vbars", None) or {}
        vbar = None
        device = getattr(model, "load_device", None)
        if vbars:
            vbar = vbars.get(device)
            if vbar is None:
                vbar = next(iter(vbars.values()))
        if vbar is not None:
            vbar_loaded = vbar.loaded_size()
            total_pages = vbar.get_nr_pages()
            resident = sum(1 for f in vbar.get_residency() if f & 1)
            info.update(vbar_loaded_mb=vbar_loaded / 2 ** 20,
                        vbar_watermark_mb=vbar.get_watermark() / 2 ** 20,
                        vbar_pages=total_pages, vbar_resident_pages=resident)
        vr = probe_vram()
        if vr is not None:
            info.update(driver_free_mb=vr[0], driver_total_mb=vr[1],
                        torch_reserved_mb=vr[2], torch_alloc_mb=vr[3])
    except Exception as exc:  # never break a run for a diagnostic
        logger.debug("probe_residency: %s", exc)
        return None
    parts = []
    if "vbar_loaded_mb" in info:
        parts.append("vbar %.0f MB loaded, watermark %.0f MB, resident %d/%d pages"
                     % (info["vbar_loaded_mb"], info["vbar_watermark_mb"],
                        info["vbar_resident_pages"], info["vbar_pages"]))
    if "driver_free_mb" in info:
        parts.append("driver free %.0f/%.0f MB"
                     % (info["driver_free_mb"], info["driver_total_mb"]))
        parts.append("torch reserved %.0f MB, alloc %.0f MB"
                     % (info["torch_reserved_mb"], info["torch_alloc_mb"]))
    if parts:
        logger.info("aimdo probe [%s]: %s", label, " | ".join(parts))
    return info


def _disabled_by_env():
    return (os.environ.get("HAVC_DYNAMIC_VRAM", "").strip().lower()
            in _DISABLE_VALUES)


def _visible_args():
    """``comfy.cli_args.args`` when that module is already imported, else None.

    Never imports ``comfy.cli_args``: ``init_process()`` runs while the
    embedding is still free to hand the core its own argv (the offline probes
    set "--cpu" there), and importing the module would freeze the parse.
    Without it the ComfyUI defaults are assumed -- ``reserve_vram`` unset and
    NVML pressure on -- which is what the reference workflow runs with.
    """
    mod = sys.modules.get("comfy.cli_args")
    return getattr(mod, "args", None) if mod is not None else None


def _aimdo_version():
    try:
        import importlib.metadata
        return importlib.metadata.version("comfy-aimdo")
    except Exception:
        return "?"


def _call_init(control, args=None):
    """``comfy_aimdo.control.init(...)`` with main.py's protocol fallbacks.

    Returns True when the comfy-aimdo library is loaded (its older protocols
    do not all report a return value).
    """
    reserve = getattr(args, "reserve_vram", None)
    simple_headroom = None if reserve is None else int(reserve * 1024 ** 3)
    nvml_pressure = not bool(getattr(args, "disable_nvml_pressure", False))
    try:
        control.init(simple_vram_headroom=simple_headroom, nvml_pressure=nvml_pressure)
    except TypeError:
        try:
            # comfy-aimdo 0.4.10 protocol (no NVML toggle)
            control.init(simple_vram_headroom=simple_headroom)
        except TypeError:
            # comfy-aimdo 0.4.9 protocol
            control.init()
    return getattr(control, "lib", None) is not None


def init_process():
    """Process half of the DynamicVRAM bootstrap (pre-torch, idempotent).

    Loads the comfy-aimdo library and applies the VRAM headroom / NVML
    pressure policy. Returns True when the library is available; never raises.
    """
    global _process_initialized, _process_ok
    if _process_initialized:
        return _process_ok
    with _lock:
        if _process_initialized:
            return _process_ok
        _process_initialized = True
        _process_ok = False

        # ComfyUI parity: the Windows mimalloc purge delay is set before torch
        # (and its allocator) is loaded. Unconditional there, unconditional here.
        if os.name == "nt":
            os.environ.setdefault("MIMALLOC_PURGE_DELAY", "0")

        if _disabled_by_env():
            logger.info("DynamicVRAM: disabled by HAVC_DYNAMIC_VRAM")
            return False

        args = _visible_args()
        if args is not None:
            try:
                from comfy.cli_args import enables_dynamic_vram
                if not enables_dynamic_vram():
                    logger.info("DynamicVRAM: disabled by the ComfyUI arguments")
                    return False
            except Exception:
                pass

        try:
            import comfy_aimdo.control as control
        except Exception as exc:
            logger.debug("DynamicVRAM: comfy-aimdo not importable (%s)", exc)
            return False

        try:
            _process_ok = bool(_call_init(control, args))
        except Exception as exc:
            logger.debug("DynamicVRAM: comfy-aimdo process init failed (%s)", exc)
            _process_ok = False
        return _process_ok


def _device_supported(model_management):
    """main.py's dynamic_vram_supported(): Nvidia, or AMD with ROCm >= 7.14."""
    try:
        if model_management.is_nvidia():
            return True
        if model_management.is_amd() and model_management.rocm_version >= (7, 14):
            return True
    except Exception:
        pass
    return False


def enable():
    """Device half of the DynamicVRAM bootstrap (idempotent, never raises).

    Initializes comfy-aimdo for every torch device and, on success, points the
    core at ``ModelPatcherDynamic`` (``CoreModelPatcher`` + ``aimdo_enabled``),
    exactly like the block after ``dynamic_vram_supported()`` in main.py.
    Call it before the first model is loaded. Returns True when DynamicVRAM
    ended up enabled.
    """
    global _enabled
    if _enabled is not None:
        return _enabled
    with _lock:
        if _enabled is not None:
            return _enabled
        _enabled = False

        if not init_process():
            return False

        try:
            import comfy.memory_management as memory_management
            import comfy.model_management as model_management
            import comfy.model_patcher as model_patcher
            import comfy_aimdo.control as control

            args = _visible_args()
            if args is not None:
                from comfy.cli_args import enables_dynamic_vram
                if not enables_dynamic_vram():
                    logger.info("DynamicVRAM: disabled by the ComfyUI arguments "
                                "(cpu/highvram/gpu-only/novram/--disable-dynamic-vram)")
                    return False

            explicit = bool(getattr(args, "enable_dynamic_vram", False))
            if not explicit and not _device_supported(model_management):
                logger.info("DynamicVRAM: no supported device "
                            "(Nvidia, or AMD with ROCm >= 7.14)")
                return False
            if not explicit and model_management.torch_version_numeric < (2, 8):
                logger.warning("DynamicVRAM: pytorch %s < 2.8 - keeping the "
                               "legacy ModelPatcher",
                               ".".join(str(p) for p in model_management.torch_version_numeric))
                return False

            _call_init(control, args)  # re-apply the policy with the visible args

            headroom = int(getattr(args, "vram_headroom", 0) * 1024 ** 3)
            devices = [(d.index, headroom) for d in model_management.get_all_torch_devices()]
            if not devices:
                logger.info("DynamicVRAM: no CUDA device found")
                return False
            try:
                initialized = control.init_devices(devices)
            except TypeError:
                # comfy-aimdo 0.4.9 protocol (no per-device headroom)
                initialized = control.init_devices([d for d, _ in devices])
            if not initialized:
                logger.warning("DynamicVRAM: comfy-aimdo could not initialize the "
                               "device - keeping the legacy ModelPatcher")
                return False

            model_patcher.CoreModelPatcher = model_patcher.ModelPatcherDynamic
            memory_management.aimdo_enabled = True
            _enabled = True
            logger.info("DynamicVRAM enabled (comfy-aimdo %s): staged weights, "
                        "ModelPatcherDynamic", _aimdo_version())
            return True
        except Exception as exc:
            logger.warning("DynamicVRAM: bootstrap failed (%s) - keeping the "
                           "legacy ModelPatcher", exc)
            logger.debug("DynamicVRAM bootstrap traceback", exc_info=True)
            return False
