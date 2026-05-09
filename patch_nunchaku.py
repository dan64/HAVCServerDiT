"""
patch_nunchaku.py
-----------------
Patches nunchaku 1.2.1 transformer_qwenimage.py to be compatible with the
diffusers QwenEmbedRope API introduced in diffusers >= 0.37.0.dev0.

Problem
-------
nunchaku 1.2.1 calls pos_embed with the deprecated `txt_seq_lens` positional
argument, which is always None in practice:

    image_rotary_emb = self.pos_embed(img_shapes, txt_seq_lens, device=...)

The new diffusers QwenEmbedRope.forward() raises:
    ValueError: Either `max_txt_seq_len` or `txt_seq_lens` must be provided.

Fix
---
Replace the broken call with one that derives `max_txt_seq_len` directly from
encoder_hidden_states.shape[1], which is the correct value:

    text_seq_len = encoder_hidden_states.shape[1] if encoder_hidden_states is not None else None
    if text_seq_len is None:
        raise ValueError("encoder_hidden_states must be provided to compute text sequence length")
    image_rotary_emb = self.pos_embed(img_shapes, max_txt_seq_len=text_seq_len, device=...)

Usage
-----
    python patch_nunchaku.py              # patch
    python patch_nunchaku.py --check      # check if patch is needed / already applied
    python patch_nunchaku.py --revert     # revert to original (from .bak)
"""

import argparse
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Patch strings
# ---------------------------------------------------------------------------

OLD_LINE = (
    "        image_rotary_emb = self.pos_embed(img_shapes, txt_seq_lens, device=hidden_states.device)"
)

NEW_LINES = """\
        # image_rotary_emb = self.pos_embed(img_shapes, txt_seq_lens, device=hidden_states.device)
        # [patch_nunchaku.py] txt_seq_lens is always None in nunchaku 1.2.1; derive
        # max_txt_seq_len from encoder_hidden_states to satisfy the new diffusers API.
        text_seq_len = encoder_hidden_states.shape[1] if encoder_hidden_states is not None else None
        if text_seq_len is None:
            raise ValueError("encoder_hidden_states must be provided to compute text sequence length")
        image_rotary_emb = self.pos_embed(img_shapes, max_txt_seq_len=text_seq_len, device=hidden_states.device)\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_target_file() -> Path:
    """Locate nunchaku's transformer_qwenimage.py inside the active Python env."""
    try:
        import nunchaku  # noqa: F401
    except ImportError:
        print("[ERROR] nunchaku is not installed in the current environment.")
        sys.exit(1)

    import nunchaku.models.transformers.transformer_qwenimage as _m
    return Path(_m.__file__).resolve()


def check(target: Path) -> str:
    """Return 'patched', 'original', or 'unknown'."""
    text = target.read_text(encoding="utf-8")
    if "[patch_nunchaku.py]" in text:
        return "patched"
    if OLD_LINE in text:
        return "original"
    return "unknown"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def do_check(target: Path) -> None:
    state = check(target)
    print(f"File  : {target}")
    if state == "patched":
        print("Status: already patched — nothing to do.")
    elif state == "original":
        print("Status: original (not yet patched) — run without --check to apply.")
    else:
        print("Status: unknown — the expected line was not found.")
        print("        The nunchaku version may differ from 1.2.1.")
    sys.exit(0)


def do_patch(target: Path) -> None:
    state = check(target)

    if state == "patched":
        print(f"[INFO] {target.name} is already patched — nothing to do.")
        sys.exit(0)

    if state == "unknown":
        print(f"[ERROR] Could not find the expected line in {target}.")
        print("        The nunchaku version may differ from 1.2.1+cu12.8torch2.9.")
        sys.exit(1)

    # Backup original
    backup = target.with_suffix(".py.bak")
    shutil.copy2(target, backup)
    print(f"[INFO] Backup saved to: {backup}")

    # Apply patch
    text = target.read_text(encoding="utf-8")
    patched = text.replace(OLD_LINE, NEW_LINES, 1)
    target.write_text(patched, encoding="utf-8")
    print(f"[OK]   Patch applied to: {target}")


def do_revert(target: Path) -> None:
    backup = target.with_suffix(".py.bak")
    if not backup.exists():
        print(f"[ERROR] No backup found at {backup}. Cannot revert.")
        sys.exit(1)

    shutil.copy2(backup, target)
    print(f"[OK]   Reverted {target.name} from backup.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch nunchaku 1.2.1 for diffusers >= 0.37.0.dev0 compatibility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check",  action="store_true", help="Check patch status without modifying files")
    parser.add_argument("--revert", action="store_true", help="Revert to original using the .bak backup")
    args = parser.parse_args()

    target = find_target_file()

    if args.check:
        do_check(target)
    elif args.revert:
        do_revert(target)
    else:
        do_patch(target)


if __name__ == "__main__":
    main()
