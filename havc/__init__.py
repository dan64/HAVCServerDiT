"""HAVC — Hybrid Automatic Video Colorizer (server stack).

This package contains the installation/verification tooling
(`havc-install`, `havc-doctor`) and the data (config, lockfile) bundled in
the wheel. The server and the pipeline stay in the historical top-level
modules (`dit_rpc_server`, `dit_colorize_main`) for compatibility with the
repo layout. Specification: installer/PHASE0_SPEC.md.
"""

__version__ = "2.2.0"
