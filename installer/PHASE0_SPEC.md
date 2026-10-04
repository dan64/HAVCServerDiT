# Fase 0 — Fondamenta: specifica tecnica

> Documento di lavoro (italiano). Riferimenti: `AGENTS.md` §4–§7.
> **Stato: v1 — 2026-10-04**, accompagna i primi componenti implementati
> (`pyproject.toml`, wheel `havc`, lockfile `requirements/`, `havc.doctor`,
> `havc.install`).
> Ambito: packaging wheel, lockfile unico, bootstrap idempotente, `havc doctor`,
> contratto `release.json`, protocollo `--json-progress`.
> Fuori ambito: wheel GUI, dati utente, manager C# (Fasi 1–2).

---

## 1. Deliverable della Fase 0

1. wheel `havc` (stack server) costruibile dal repo e installabile in un venv pulito;
2. lockfile unico versionato (`requirements/`);
3. `havc-install` — bootstrap idempotente/convergente, con `--json-progress`;
4. `havc doctor` — verifica non distruttiva dell'ambiente;
5. contratto `release.json` (schema + esempio; generazione automatica più avanti);
6. verifica su ambiente pulito (checklist §9).

Risultato atteso: **installazione "one command"** dello stack server, senza git
per l'utente finale, e testabilità. La modalità completamente remota (download
degli asset dal manifest) si completa quando esiste la prima release di prova —
lo schema è già fissato qui.

---

## 2. Packaging — wheel `havc`

- Versione `0.1.0` (PEP 440); fonte unica `havc/__init__.py::__version__`
  (`[tool.setuptools.dynamic]`).
- `requires-python = "==3.12.*"` — le wheel nunchaku e
  spatial_correlation_sampler sono cp312: un ambiente 3.11/3.13 va rifiutato,
  non aggiustato.
- **`dependencies = []` è voluto**: l'installazione è orchestrata dal bootstrap
  (ordine preciso, index CUDA dedicato, wheel da URL, patch post-install).
  `pip install havc.whl` da solo non è il percorso supportato; usare
  `havc-install` (o `--no-deps` per utenti esperti).
- Entry point: `havc-server`, `havc-doctor`, `havc-install`, `havc-patch-nunchaku`.
- **Contenuto** (fonte unica = repo; le copie sono generate alla build dal
  build hook in `setup.py` — nessuna copia manuale da mantenere):
  - `havc/` (CLI `install`/`doctor`, `paths`, `lockfile`, `progress`);
  - `dit_rpc_server.py`, `dit_colorize_main.py`, `patch_nunchaku.py`
    (moduli top-level storici);
  - `comfy_bridge/**` (runtime ComfyUI vendored: file `.py` + dati, incluse le
    cartelle non importabili come `custom_nodes/ComfyUI-GGUF*`);
  - `config/*.json` → `havc/configs/`;
  - `requirements/*.txt` → `havc/requirements/`.
- Esclusi dalla wheel: solo cache Python (`.pyc`, `__pycache__`) e backup
  (`.bak`/`.orig`/`.rej`). Ottimizzazione futura possibile:
  `comfy_bridge/blueprints/` (3,1 MB, template GUI ComfyUI, **non referenziato
  dal codice** — verificato con grep sull'intero albero) — da rimuovere solo
  dopo un ciclo di verifica in VM (§9).
- Risoluzione percorsi a runtime: `havc.paths` cerca prima la copia inclusa
  nella wheel, poi il checkout. `dit_colorize_main.py` continua a risolvere
  `comfy_bridge/` come sibling del proprio file — vale sia nel repo sia in
  `site-packages`.
- Modelli: comportamento invariato (auto-download sotto
  `comfy_bridge/models/…` dentro il venv; `COMFYUI_MODELS_DIR` forzato da
  `comfy_bridge/_bootstrap.py`). Il passaggio a una cartella modelli utente
  configurabile (scelta nel wizard) è materia delle Fasi 1–2.
- Wheel GUI (`havc-gui`): rinviata. Le dipendenze GUI e i percorsi dei dati
  utente (settings, tool esterni, cartella di lavoro) richiedono un progetto a
  parte — non basta impacchettare i file così come sono.

---

## 3. Lockfile (`requirements/`)

- `torch.txt` — `torch`/`torchvision`/`torchaudio` **2.10.0+cu130**, da
  installare con `--index-url https://download.pytorch.org/whl/cu130`.
- `nunchaku.txt` — wheel diretta da GitHub release (piattaforma-specifica:
  Windows / cp312 / CUDA 13.0 / torch 2.10).
- `core.txt` — `transformers`, `accelerate`, `huggingface_hub`, `pillow`,
  `scipy`, `av`, `torchsde`, `gguf`, `comfy-aimdo`, `comfy-kitchen`
  (pin presi dall'ambiente di riferimento `_dev`, 2026-10-04).

Regole:

- **Ogni bump di versione si fa qui, prima che altrove.**
- In Fase 0 `install.cmd`, `quick_update.cmd` e i README continuano a esistere
  invariati (compatibilità con le installazioni esistenti) e vanno riconciliati
  a mano: il passaggio a wrapper sottili del bootstrap è Fase 2.
- La wheel incorpora una copia del lock (`havc/requirements/`): doctor e
  bootstrap la trovano anche a installazione avvenuta.

---

## 4. Bootstrap `havc-install`

Principio: **"install = update da stato vuoto"**. Ogni passo esegue prima un
*check* read-only; se lo stato è già quello desiderato il passo viene saltato
con un motivo, altrimenti esegue l'azione. Idempotente per costruzione:
rieseguire il bootstrap è l'operazione di *update* e di *repair*.

Passi, nell'ordine:

1. `preflight` — Python host 3.12, lockfile presente, risoluzione dell'interprete;
2. `venv` — crea il venv di destinazione se manca;
3. `pip` — aggiorna pip solo se sotto la soglia minima;
4. `torch` — `pip install -r requirements/torch.txt --index-url <CUDA 13.0>`;
5. `nunchaku` — `pip install -r requirements/nunchaku.txt`;
6. `torch-repin` — `--force-reinstall` **solo se** nunchaku ha spostato torch
   (il check confronta le versioni: più mirato del re-pin incondizionato di
   `install.cmd`);
7. `patch` — applica la patch di compatibilità nunchaku (skip se già applicata
   o se nunchaku non è installato);
8. `diffusers` — installa la wheel locale (cercata in `--assets-dir`,
   default `packages/`);
9. `deps` — `pip install -r requirements/core.txt`;
10. `wheel` — installa la wheel del progetto (`--wheel`, con `--no-deps`);
11. `verify` — esegue `havc doctor --json` **nel venv di destinazione**;
    un FAIL qui è un errore del bootstrap.

Flag: `--env-dir` (obbligatorio), `--python`, `--assets-dir`, `--wheel`,
`--only a,b`, `--plan`, `--dry-run`, `--json-progress`.

Exit code: `0` = ok (anche se tutto era già a posto), `1` = passo fallito,
`2` = errore d'uso.

Sicurezza: non tocca nulla fuori da `--env-dir` (a parte la cache pip);
nessun privilegio di amministratore; nessuna cancellazione.

Modalità operative:

- **checkout** (default): gira dal repo, `--assets-dir` default `packages/`;
- **staged**: `--assets-dir`/`--wheel` puntano a file scaricati a mano;
- **remota** (futuro, stesso schema): il manager scarica wheel e asset dal
  manifest `release.json` e invoca gli stessi passi.

Stato locale (`install.json`): **rinviato alla Fase 1** — schema minimo
previsto in §8. Il bootstrap v0 non scrive stato.

---

## 5. Protocollo `--json-progress`

- `stdout` = **solo righe JSON**, una per evento (line-delimited JSON).
- `stderr` riservato a crash/traceback.
- L'output dei processi figli (pip ecc.) viaggia come eventi `log`.

Eventi:

- `plan` — `steps[]` con `{id, title, hint, skip_reason}` (in modalità `--plan`);
- `step_begin` — `id`, `title`;
- `step_ok` — `id`, `detail`;
- `step_skip` — `id`, `reason`;
- `step_error` — `id`, `error`, `remediation`;
- `log` — `level` (`cmd` | `out` | `err` | `dry-run`), `message`;
- `result` — `ok`, `steps`, `skipped`.

Tutti gli eventi hanno `event` e `ts` (epoch). Esempio:

```json
{"event": "step_begin", "ts": 1759500000.1, "id": "torch", "title": "PyTorch 2.10.0+cu130"}
{"event": "log", "ts": 1759500001.2, "level": "out", "message": "Collecting torch==2.10.0+cu130"}
{"event": "step_ok", "ts": 1759500123.4, "id": "torch", "detail": "PyTorch 2.10.0+cu130"}
{"event": "result", "ts": 1759500600.0, "ok": true, "steps": 11, "skipped": 3}
```

Il manager C# (Fase 1) consuma questi eventi per UI/progress; `--plan
--json-progress` fornisce il piano del wizard.

---

## 6. `release.json` — contratto di release

Allegato a ogni release GitHub. Generazione: script locale in Fase 0, poi CI
(GitHub Actions) al tag. **L'installer/manager non conosce versioni: le legge
qui.**

Campi: `schema`, `channel`, `app`, `app_version`, `published_at`,
`requires_python`, `requires_env_rebuild`, `bootstrap_min_version`,
`wheels[]` (`name`, `url`, `sha256`, `size`, `kind`, `install`),
`assets[]` (wheel di terze parti, es. diffusers), `weights[]` e `tools[]`
(riservati alle fasi GUI, per ora vuoti), `notes_url`.

Regole: **sha256 obbligatori** per ogni artefatto; `requires_env_rebuild` a
`true` quando cambia la versione di Python o il lock in modo sostanziale
(il manager ricostruisce il venv); il manifest è additivo — nuovi campi non
rompono i manager vecchi.

Esempio completo: `installer/release.example.json`.

---

## 7. `havc doctor`

Check (in ordine): `env` (venv attivo), `python` (3.12), `packages` (tutti i
pin del lock soddisfatti), `nunchaku-patch`, `cuda` (import torch + GPU
visibile), `gpu` (`nvidia-smi`: nome, driver, VRAM), `havc` (versione e path).

- Status: `ok` / `warn` / `fail` / `skip`; exit code `0` se nessun `fail`.
- `--json` = report macchina-leggibile (un oggetto JSON);
- `--fast` = salta i check CUDA/GPU (lenti, per iterazioni rapide);
- `--lock-dir` = lockfile alternativo (default: quello incluso nella wheel).

Uso: passo `verify` del bootstrap; in Fase 1 diventa il "report di salute" del
manager (stesso comando, stesso output).

---

## 8. Stato locale `install.json` (rinviato alla Fase 1)

Campi previsti: `schema`, `app_version`, `lock_hash`, `env_version`,
`python`/venv path, componenti installati (server/gui), pesi (nome + hash),
tool (versione), esito ultima verifica, snapshot precedente (per il rollback).
Scritto/letto dal manager; il bootstrap v0 non lo tocca.

---

## 9. Verifica (checklist Fase 0)

Verificato il 2026-10-04 (in questo branch):

- build della wheel + ispezione dei contenuti (config, requirements,
  comfy_bridge, moduli top-level, entry point, assenza di cache Python);
- install in venv pulito (`--no-deps`) + esecuzione di `havc-doctor` e
  `havc-install --plan`;
- `havc doctor` eseguito contro l'ambiente di riferimento `_dev`;
- esecuzione reale dei primi passi (`--only preflight,venv,pip`) in un venv
  usa-e-getta.

Da fare prima di chiudere la Fase 0:

- run **end-to-end su VM/Sandbox pulita** (senza e con GPU): bootstrap completo
  + `havc doctor` verde;
- prova del passo `--wheel` con la wheel buildata;
- prima release di prova con `release.json` generato + verifica del flusso di
  update incrementale tra due versioni;
- pulizia: valutare l'esclusione di `comfy_bridge/blueprints/` dalla wheel.

---

## 10. Compatibilità

Nessun cambiamento per installazioni e workflow esistenti: `install.cmd`,
`quick_update.cmd`, gli script `.cmd` e il layout del repo restano identici.
I nuovi file sono additivi; la wheel è costruita dallo stesso albero sorgente.
