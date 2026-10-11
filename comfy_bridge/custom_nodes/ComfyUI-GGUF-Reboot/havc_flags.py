"""HAVC runtime switch for the vendored Reboot copy.

The v26-10-11 update changed the GGUF-text-encoder path (mmproj sidecar lookup
for Qwen3-VL, metadata extraction, K-quant / Q8 fallbacks). HAVC keeps the
previous copy of the changed modules in ``legacy_v26_09_04/`` and selects the
implementation at pipeline load:

    fix_qwen21_enabled=True   -> the v26-10-11 code (default)
    fix_qwen21_enabled=False  -> the previous implementation (48de657 /
                                 v26-09-04+6), exactly as it was

Resolution order for one load (see ``reboot_modules``):
    1. the explicit argument: the pipeline config's ``fix_qwen21_enabled``
       key, read by dit_rpc_server / dit_colorize_main for the qwen21
       families
    2. the HAVC_FIX_QWEN21 environment variable (1/true/on/yes -> True,
       0/false/off/no -> False; anything else -> default)
    3. DEFAULT_FIX_QWEN21_ENABLED (True: keep the updated code)

Only the GGUF-text-encoder branch of the pipeline loader imports these
modules; the native int8-ConvRot safetensors path never touches Reboot, so
the switch is a no-op there.
"""

import importlib
import os

DEFAULT_FIX_QWEN21_ENABLED = True
_ENV_VAR = "HAVC_FIX_QWEN21"
LEGACY_PACKAGE_SUFFIX = ".legacy_v26_09_04"


def _env_flag():
    raw = os.environ.get(_ENV_VAR)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in ("1", "true", "on", "yes"):
        return True
    if value in ("0", "false", "off", "no"):
        return False
    return None


def resolve_fix_qwen21(explicit=None):
    """The effective flag: explicit argument > HAVC_FIX_QWEN21 > default."""
    if explicit is not None:
        return bool(explicit)
    env = _env_flag()
    if env is not None:
        return env
    return DEFAULT_FIX_QWEN21_ENABLED


def fix_qwen21_enabled():
    """The flag as resolved without an explicit argument (env or default)."""
    return resolve_fix_qwen21(None)


def reboot_modules(fix_qwen21=None):
    """(loader, ops) modules for the requested implementation.

    Both come from the same implementation (updated or legacy) so a single
    pipeline load never mixes them. The modules stay cached per process, so
    switching the flag affects the loads that happen afterwards.
    """
    package = __name__.rsplit(".", 1)[0]
    base = package if resolve_fix_qwen21(fix_qwen21) else package + LEGACY_PACKAGE_SUFFIX
    return (importlib.import_module(base + ".loader"),
            importlib.import_module(base + ".ops"))
