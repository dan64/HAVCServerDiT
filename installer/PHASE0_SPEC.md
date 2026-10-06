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

- Versione `0.1.1` (PEP 440); fonte unica `havc/__init__.py::__version__`
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
  - `config/*.json` → `havc/configs/`;
  - `requirements/*.txt` → `havc/requirements/`;
  - GUI → `havc/gui/` (`CMNET2_colorize_client_GUI.py`,
    `load_image_DtD_GUI.py`, `scripts/*.vpy`): è il **front-end di default**
    dell'installazione (vedi §4, passi 12-17).
- **Esclusi dalla wheel**: cache Python (`.pyc`, `__pycache__`) e backup
  (`.bak`/`.orig`/`.rej`). **`comfy_bridge/` non è più nella wheel** (dal
  2026-10-05): il runtime ComfyUI venduto si distribuisce come zip pinnato
  (`comfy_bridge_v0.30.zip`, script `installer/build_comfy_zip.py`) ed è
  estratto nella root dell'installazione dal passo `comfy-bridge` (D14). Lo
  zip esclude — come prima la wheel — **`comfy_bridge/blueprints/`** (96 file
  di materiale UI, nessun riferimento nel runtime: nessun caso d'uso).
  Effetto sulla wheel: ~10,7 MB → ~0,11 MB.
- **Nota di build**: il build hook azzera le destinazioni dentro `build/lib`
  prima di ogni copia (copia deterministica) — senza questo, i file già copiati
  dalle build precedenti restano impacchettati da `bdist_wheel` anche se
  rimossi/esclusi dal sorgente (bug trovato e corretto il 2026-10-04 proprio
  con l'esclusione di `blueprints/`; dal 2026-10-05 lo stesso meccanismo
  rimuove dalla `build/lib` la copia storica di `comfy_bridge/`).
- Risoluzione percorsi a runtime: `havc.paths` cerca prima la copia inclusa
  nella wheel, poi il checkout. `dit_colorize_main.py` risolve
  `comfy_bridge/` come sibling del proprio file: dalla 0.1.8 i due
  `dit_*.py` e il tree `comfy_bridge/` stanno tutti nella **root**
  dell'installazione (passi `server`/`comfy-bridge`), quindi import e
  percorsi dei modelli coincidono per costruzione (fix del 2026-10-05); nel
  repo il sibling è la cartella del progetto.
- **Layout di installazione** (root gestita dal bootstrap/manager):
  `<install>\runtime\python\` (runtime Python provisionato, §4-bis),
  `<install>\venv\` (ambiente), `<install>\cache\` (archivi scaricati e
  verificati), `<install>\config\` (config di pipeline, condivise da GUI e
  server), `<install>\gui\` (GUI + `scripts/*.vpy` + `gui_cmnet2_settings.json`),
  `<install>\tools\` (x265/x264/mkvmerge/NVEncC),
  `<install>\comfy_bridge\` (runtime ComfyUI dal zip pinnato + `models\`),
  `<install>\work\` (cartella di lavoro di default), launcher nella radice
  (**front-end di default: la GUI**).
- Modelli: dentro l'installazione, in `<install>\comfy_bridge\models\…`
  (auto-download dei backend; **preservati** a update/ripara/disinstallazione
  salvo richiesta esplicita — D14, 2026-10-05). La cartella modelli utente
  configurabile (scelta nel wizard) è stata ritirata (D14); la cache HF sta
  nella posizione di default (`hf_cache` vuoto).
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
  (pin presi dall'ambiente di riferimento `_dev`, 2026-10-04);
- `assets.txt` — versioni attese delle wheel installate da **file locali**
  (es. `diffusers==0.37.0.dev0`): non è installato da pip, serve ai check di
  idempotenza del bootstrap e a `havc doctor`.

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

1. `preflight` — host Python ≥ 3.9, lockfile presente;
2. `runtime` — provisioning del Python 3.12 (§4-bis): usa `--runtime-zip`, la
   copia in `<install-dir>\cache\` (se lo sha256 corrisponde) o scarica
   l'archivio pinnato; verifica sha256; estrae in `<install-dir>\runtime\python`;
   controlla la versione finale;
3. `venv` — crea il venv di destinazione dal runtime (se manca) e mantiene
   l'alias `<install>\.venv` (junction → `venv`): la GUI cerca il python del
   server in `.venv\Scripts\python.exe` (layout dev) — fix del 05-10, log
   (42) di AGENTS.md;
4. `pip` — aggiorna pip solo se sotto la soglia minima;
5. `torch` — `pip install -r requirements/torch.txt --index-url <CUDA 13.0>`;
6. `nunchaku` — `pip install -r requirements/nunchaku.txt`;
7. `torch-repin` — `--force-reinstall` **solo se** nunchaku ha spostato torch
   (il check confronta le versioni: più mirato del re-pin incondizionato di
   `install.cmd`);
8. `patch` — applica la patch di compatibilità nunchaku (skip se già applicata
   o se nunchaku non è installato);
9. `diffusers` — installa la wheel locale (cercata in `--assets-dir`,
   default `packages/`);
10. `deps` — `pip install -r requirements/core.txt`;
11. `wheel` — installa la wheel del progetto (`--wheel`, con `--no-deps`);
12. `server` — copia `dit_rpc_server.py` e `dit_colorize_main.py` dalla wheel
    (site-packages del venv) nella root di `<install>`, riscritti se diversi:
    la GUI avvia il server da lì (file path + `--module-dir`);
13. `comfy-bridge` — scarica/verifica `comfy_bridge_v0.30.zip` (pinnato,
    sha256; `--comfy-zip` per staging/offline) e lo estrae in
    `<install>\comfy_bridge`, **preservando `models/`**; marker `.source` per
    l'idempotenza;
14. `configs` — copia le config di pipeline in `<install>\config`: le mancanti
    sempre; con `--update-configs` sostituisce anche quelle **diverse** dalla
    versione packaged (backup `<nome>.json.bak` accanto); senza flag le
    differenze sono elencate nel motivo di skip (il manager chiede conferma
    prima di passare il flag — 06-10, log (45));
15. `gui` — copia i file GUI in `<install>\gui` (script principale, helper,
    `scripts/*.vpy`, `samples/` — dalla copia inclusa nella wheel o dal
    checkout); aggiorna i file se il contenuto differisce (skip solo se
    identici);
16. `gui-deps` — `pip install -r requirements/gui.txt` + wheel `vscmnet2` e
    `spatial_correlation_sampler` da `--assets-dir`;
17. `cmnet2-plugins` — estrae `plugins_win.zip` (vs-cmnet2 v1.0.0, sha256)
    in `vscmnet2\plugins\`;
18. `cmnet2-weights` — scarica il checkpoint DINOv3 (`cmnet2` v1.3.0) e
    `dinov3-vitb16.zip` (v1.1.0, estratto) in `vscmnet2\weights\`;
19. `cmnet2-dinov2` — pesi DINOv2 legacy (`cmnet2` v1.0.0), **saltato di
    default**; si attiva con `--with-dinov2`;
20. `tools` — estrae in `<install>\tools` sia `tools.zip` (x265/x264/mkvmerge)
    sia `NVEncC_9.17_x64.zip` (NVEncC 9.17, pacchetto flat); entrambi pinnati
    (Release v1.0.0, sha256 verificato), o `--tools-zip` per la parte tools.zip;
21. `gui-settings` — pre-seeda `gui_cmnet2_settings.json` (solo se assente):
    percorsi di `scripts/`, `vspipe`, tool, cartella di lavoro e `model_name`
    di default (`qwen21-viggle`, o `longcat-gguf` con precision `q3` via
    `--default-model`); su file esistente riempie solo i valori vuoti
    (`model_name`/`model_precision`), senza mai sovrascrivere;
22. `launchers` — scrive i launcher in `<install>`: `HAVC.cmd`/`HAVC.vbs`
    (**front-end di default = GUI**), `HAVC-Server.cmd` (server con scelta
    modello), `HAVC-Doctor.cmd`, `start_server.cmd`/`run_server_qwen21.cmd` +
    i wrapper per-modello `run_server_{fp4,int4,longcat,q3}.cmd` (avvio in
    console per la modalità *External console* della GUI e uso manuale;
    stessi nomi argomento dello storico `start_server.cmd`, come da tabella
    del README); riscritti se il contenuto differisce;
23. `verify` — esegue `havc doctor --json` **nel venv di destinazione**;
    un FAIL qui è un errore del bootstrap.

Flag: `--install-dir` (obbligatorio), `--python`, `--runtime-zip`,
`--tools-zip`, `--with-dinov2`, `--update-configs` (sostituisce i config
**diversi**, `.bak` accanto), `--use-system-python`, `--assets-dir`,
`--wheel`, `--comfy-zip <zip>` (comfy_bridge locale per staging/offline),
`--default-model <nome>` (modello GUI di default nel seed settings),
`--only a,b`, `--plan`, `--dry-run`, `--json-progress`.

Exit code: `0` = ok (anche se tutto era già a posto), `1` = passo fallito,
`2` = errore d'uso.

Sicurezza: non tocca nulla fuori da `--install-dir` (a parte la cache pip);
nessun privilegio di amministratore; nessuna cancellazione.

### Provisioning del runtime (§4-bis)

Il passo `runtime` installa un Python **python-build-standalone** (Astral;
x86_64 Windows per ora), pinnato per versione e sha256 nelle costanti `RUNTIME`
di `havc/runtime.py`. Perché questa build: l'embed ufficiale di python.org è
privo di tkinter (serve alla GUI), venv ed ensurepip — la build scelta include
tutto (tkinter 8.6, venv, ensurepip, pip) e si estrae senza installer né
registry. Lo sha256 pinnato è verificato anche contro il `digest` ufficiale
dell'asset GitHub (2026-10-04).

**Fatto (2026-10-04)**: il mirror è pubblicato come release `runtime-312`
(asset invariato, sha256 verificato anche dal `digest` GitHub e con un download
end-to-end dal mirror); `RUNTIME["url"]` punta al mirror.

Modalità operative:

- **checkout** (default): gira dal repo, `--assets-dir` default `packages/`;
- **staged**: `--assets-dir`/`--wheel`/`--runtime-zip` puntano a file locali;
- **macchina pulita (flusso manager)**: il manager estrae il runtime
  dall'asset pinnato, installa la wheel nel runtime
  (`runtime\python -m pip install --no-deps havc-*.whl`) e lancia
  `runtime\python -m havc.install --install-dir <root>` — il bootstrap non
  richiede quindi un Python preesistente;
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

- `plan` — `steps[]` con `{id, title, hint, skip_reason}`: **emesso all'avvio
  di ogni run** (nei run normali `skip_reason` è `null` e gli stati arrivano
  con gli eventi successivi; in modalità `--plan` i `skip_reason` sono
  calcolati e non viene eseguito nulla);
- `step_begin` — `id`, `title`;
- `step_ok` — `id`, `detail`;
- `step_skip` — `id`, `reason`;
- `step_error` — `id`, `error`, `remediation`;
- `log` — `level` (`cmd` | `out` | `err` | `dry-run`), `message`;
- `result` — `ok`, `steps`, `skipped`.

**Cancel cooperativo (Fase 1)**: se all'avvio di un passo esiste
`<install>\cache\.stop-request`, il bootstrap si ferma prima di eseguirlo
(il file viene rimosso all'avvio di ogni run). Usato dal pulsante *Cancel*
del manager.

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

Allegato a ogni release GitHub. Generazione:
`python installer/make_release.py --tag vX.Y.Z --artifacts-dir <dir>` — calcola
sha256/dimensioni dagli artefatti locali e legge versione e blocco `runtime`
dalle fonti uniche (`havc/__init__.py`, `havc/runtime.py`); `--verify
<manifest>` ricontrolla un manifest esistente contro gli artefatti. CI
(GitHub Actions) al tag in seguito. **L'installer/manager non conosce versioni:
le legge qui.**

Campi: `schema`, `channel`, `app`, `app_version`, `published_at`,
`requires_python`, `requires_env_rebuild`, `bootstrap_min_version`,
`runtime` (`name`, `url`, `sha256`, `python`, `kind`, `mirror_of` — la build
Python provisionata, §4-bis), `wheels[]` (`name`, `url`, `sha256`, `size`,
`kind`, `install`), `assets[]` (wheel di terze parti, es. diffusers, e
`comfy_bridge_v0.30.zip` con `kind: comfy-bridge`),
`weights[]` e `tools[]` (riservati alle fasi GUI, per ora vuoti), `notes_url`.

Regole: **sha256 obbligatori** per ogni artefatto; `requires_env_rebuild` a
`true` quando cambia la versione di Python o il lock in modo sostanziale
(il manager ricostruisce il venv); il manifest è additivo — nuovi campi non
rompono i manager vecchi.

Esempio completo: `installer/release.example.json`.

---

## 7. `havc doctor`

Check (in ordine): `env` (venv attivo), `python` (3.12), `packages` (tutti i
pin del lock soddisfatti), `nunchaku-patch`, `cuda` (import torch + GPU
visibile), `gpu` (`nvidia-smi`: nome, driver, VRAM), `gui` (GUI presente
accanto al venv — warn, non fail, per installazioni server-only), `cmnet2`
(plugin e pesi DINOv3 se `vscmnet2` è installato — warn), `havc`
(versione e path).

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
- provisioning del runtime: estrazione da `--runtime-zip` e creazione del venv
  dal runtime (`venv: 3.12.15 | tkinter 8.6`), idempotenza alla riesecuzione;
- download reale dell'archivio (21 MB) via `urllib` con verifica sha256
  (controllata anche contro il `digest` ufficiale GitHub); rifiuto con sha256
  errato (exit 1); uso della cache e di `--use-system-python`;
- **mirror pubblicato** (release `runtime-312`) e download end-to-end **dal
  mirror** verificato (sha256 ok); `RUNTIME["url"]` punta al mirror;
- esclusione di `comfy_bridge/blueprints/` dalla wheel: −96 file / −389.901
  byte (11.034.021 → 10.644.120); contenuti riverificati (407 file
  comfy_bridge, 0 voci 'blueprint', tutti i file chiave presenti);
- generatore `release.json` (`installer/make_release.py`): generazione su
  staging (wheel `havc` + asset diffusers), `--verify` ok, rifiuto di
  `--version` incoerente, verifica fallita su artefatto troncato (exit 1);
- **prima release di prova pubblicata**: `v0.1.0-alpha` (prerelease) con wheel
  `havc`, asset diffusers e `release.json`; digest GitHub coerenti col
  manifest, manifest remoto identico al locale, URL raggiungibili, `v1.0.0`
  resta la release "Latest" (asset aggiornati il 04-10 dopo i fix sotto);
- **end-to-end su cartella di test** (`D:\HAVCServerDiT_Test`, flusso manager
  runtime→wheel nel runtime→bootstrap): installazione completa con download
  reale (runtime dal mirror, torch, nunchaku), venv creato dal runtime, passo
  `--wheel` provato, doctor tutto verde, console script presenti nel venv.
  Il test ha trovato e fatto correggere: (a) check di skip e `verify`
  sensibili al CWD (un checkout/`havc.egg-info` nel CWD ombreggiava il venv —
  ora i processi figli girano con CWD neutrale); (b) pin `diffusers` mancante
  nel lock (aggiunto `requirements/assets.txt`);
- **GUI come front-end dell'installazione** (2026-10-04): passi
  `configs/gui/gui-deps/tools/gui-settings/launchers` provati sul folder di
  test — launcher con CRLF verificati, settings pre-seedati, tool esterni
  estratti da `tools.zip`, import delle dipendenze GUI ok (FreeSimpleGUI,
  tkinterdnd2, VapourSynth, vscmnet2), smoke di avvio della GUI senza errori;
  `havc doctor` a **22 pacchetti** con check `gui` verde; rerun
  completamente idempotente. Asset di `v0.1.0-alpha` aggiornati (wheel con GUI,
  `vscmnet2`, `spatial_correlation_sampler`, `release.json`);
- **vs-cmnet2 completata dall'installer** (2026-10-04): passi `cmnet2-plugins`,
  `cmnet2-weights`, `cmnet2-dinov2` — plugin (vs-cmnet2 v1.0.0) e pesi DINOv3
  (cmnet2 v1.3.0/v1.1.0) scaricati con verifica sha256 e depositati in
  `vscmnet2\`; dimensioni identiche al byte all'installazione di riferimento;
  rerun idempotente; `havc doctor` a **9 check verdi** (incluso `cmnet2`);
  dry-run del flag `--with-dinov2` verificato. Corretto il link morto in
  `docs/gui.md` (il checkpoint DINOv3 sta nella v1.3.0, non v1.2.0).
- **NVEncC pubblicato e integrato** (2026-10-04): `NVEncC_9.17_x64.zip`
  (100,6 MB) caricato nella Release v1.0.0 accanto a `tools.zip` (digest
  verificato); passo `tools` esteso (gestisce entrambi gli archivi, estrazione
  "flat" supportata); download reale + estrazione provati (22 file),
  `NVEncC64.exe --version` → 9.17 (r3600); rerun idempotente;
- **Pesi DINOv2 legacy provati davvero** (2026-10-04): passo `cmnet2-dinov2`
  con `--with-dinov2` — 4 file (~720 MB) scaricati da cmnet2 v1.0.0, sha256
  verificati (spot-check sul checkpoint da 494 MB), dimensioni identiche al
  byte; rerun idempotente.
- **update incrementale verificato** (2026-10-04, da `v0.1.0` a `0.1.1`,
  staging locale): eseguiti solo `wheel`/`gui`/`launchers`, `verify` verde,
  rerun idempotente; il test ha fatto correggere i passi `gui`/`launchers`
  (skip "su presenza" → confronto di contenuto: le modifiche ai file gestiti
  ora si propagano con l'update); log `install-run8/9/10.log` in
  `D:\HAVCServerDiT_Test`.

Da fare prima di chiudere la Fase 0:

- (facoltativo, pre-release) run su VM/Sandbox "macchina pulita" per le
  assunzioni fuori dallo stack (niente Python/git/cache preesistenti).

---

## 10. Compatibilità

Nessun cambiamento per installazioni e workflow esistenti: `install.cmd`,
`quick_update.cmd`, gli script `.cmd` e il layout del repo restano identici.
I nuovi file sono additivi; la wheel è costruita dallo stesso albero sorgente.
