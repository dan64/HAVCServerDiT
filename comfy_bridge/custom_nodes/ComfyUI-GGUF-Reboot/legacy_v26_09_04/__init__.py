"""Previous implementation of the vendored Reboot modules (pre-v26-10-11).

Byte-for-byte copies of the upstream v26-09-04+6 (48de657, 2026-09-23) files
that the vendored copy shipped before the v26-10-11 update: loader.py, ops.py,
quant_ops.py and their dequant.py dependency.

They are selected at pipeline load when ``fix_qwen21_enabled`` is False (see
../havc_flags.py): with the flag off the GGUF-text-encoder path behaves
exactly as it did before the update -- most notably the mmproj sidecar lookup
of gguf_mmproj_loader() does *not* know the Qwen3VL alias, so a
"Qwen3VL-..." mmproj next to a "Qwen3-VL-..." encoder is not found (the
silent text-only breakage of upstream issue #23), and ambiguous matches do
not raise.
"""
