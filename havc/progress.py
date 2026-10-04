"""Emissione degli eventi di progresso: leggibile (default) o JSON (una riga per evento).

Protocollo: installer/PHASE0_SPEC.md §5. In modalità JSON *stdout* contiene
solo righe JSON; l'output dei processi figli viene incapsulato in eventi `log`.
"""

from __future__ import annotations

import json
import sys
import time


def force_utf8() -> None:
    """stdout/stderr in UTF-8: output stabile anche quando è rediretto (es. manager C#)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class Progress:
    def __init__(self, json_mode: bool = False):
        self.json_mode = json_mode

    def event(self, kind: str, **data) -> None:
        if self.json_mode:
            payload = {"event": kind, "ts": time.time(), **data}
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        else:
            self._human(kind, data)

    def _human(self, kind: str, data: dict) -> None:
        if kind == "plan":
            print("Piano di installazione:")
            for i, step in enumerate(data.get("steps", []), 1):
                mark = f"[salta: {step['skip_reason']}]" if step.get("skip_reason") else ""
                print(f"  {i:2d}. {step['id']:<12} {step['title']} {mark}")
        elif kind == "step_begin":
            print(f"\n[{data.get('id')}] {data.get('title')} ...")
        elif kind == "step_ok":
            detail = f" ({data['detail']})" if data.get("detail") else ""
            print(f"[{data.get('id')}] OK{detail}")
        elif kind == "step_skip":
            print(f"[{data.get('id')}] saltato: {data.get('reason')}")
        elif kind == "step_error":
            print(f"[{data.get('id')}] ERRORE: {data.get('error')}")
            if data.get("remediation"):
                print(f"          -> {data['remediation']}")
        elif kind == "log":
            print(f"    {data.get('message')}")
        elif kind == "result":
            print(f"\nEsito: {'OK' if data.get('ok') else 'FALLITO'}")
        # altri eventi: ignorati in modalità umana
