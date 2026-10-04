"""HAVC — Hybrid Automatic Video Colorizer (server stack).

Questo pacchetto contiene gli strumenti di installazione/verifica
(`havc-install`, `havc-doctor`) e i dati (config, lockfile) inclusi nella
wheel. Il server e la pipeline restano nei moduli top-level storici
(`dit_rpc_server`, `dit_colorize_main`) per compatibilità con il layout del
repo. Specifica: installer/PHASE0_SPEC.md.
"""

__version__ = "0.1.1"
