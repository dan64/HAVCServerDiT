# Fase 1 — Manager C#: specifica tecnica

> Documento di lavoro (italiano). Riferimenti: `AGENTS.md` §2 (D1, D8–D11),
> §4c, §5, §6; `installer/PHASE0_SPEC.md` (bootstrap, lockfile, `release.json`,
> protocollo eventi).
> **Stato: v1 — 2026-10-04.** Ambito: app WPF "HAVC Setup" per installazione,
> update, riparazione e disinstallazione dell'ambiente. Fuori ambito: rebuild
> automatico del venv, modalità Server-only/GUI-only, auto-update del manager,
> firma del codice (differita, D1).

---

## 1. Obiettivo

Il manager è l'unico artefatto che l'utente scarica e avvia: un'app C# **WPF
self-contained single-file** (D9) che orchestra il bootstrap `havc-install` e
l'ambiente descritto da `release.json`. L'utente finale non vede mai git,
Python, pip o PowerShell.

Principi:

- **Orchestrazione, non reimplementazione**: i passi di installazione vivono
  nel bootstrap (Fase 0, già verificato); il manager decide *quando* eseguirli e
  *cosa* scaricare, e presenta stato/progresso/errori. Ogni nuovo passo nasce
  nel bootstrap, non nel manager.
- **Niente Inno o packager esterni** (D8): l'exe è l'installer; nessun doppio
  strato.
- **Per-utente, senza admin**; tutto ciò che è pesante (runtime, venv, cache,
  modelli) vive dentro la cartella di installazione — i modelli in
  `<install>\comfy_bridge\models`, preservati in disinstallazione (D14).
- **Update = rerun convergente**: stessa logica "install = update da stato
  vuoto" del bootstrap (flusso già verificato end-to-end v0.1.0 → 0.1.1,
  log (14)).

### Ambito v0 (Fase 1)

1. wizard di prima installazione (*Server+GUI* soltanto, D10);
2. **update incrementale** da `release.json`, con rollback automatico su
   verifica fallita;
3. **ripara** (rerun convergente sulla versione installata);
4. **controlla aggiornamenti**;
5. avvio GUI/server + scorciatoie + voce di disinstallazione;
6. **disinstallazione** (modelli mai cancellati di default, D10);
7. stato locale `install.json` + log.

### Fuori ambito v0 (candidati Fase 2)

- rebuild automatico del venv (`requires_env_rebuild=true` → v0 blocca con
  messaggio, §6.7);
- modalità *Server only* e *GUI-only* (richiedono profili di dipendenze
  dedicati);
- auto-update del manager (v0: link al download);
- installazione silenziosa/enterprise (`--silent`), migrazione automatica di
  cartelle modelli preesistenti, telemetria (mai).

---

## 2. Piattaforma, build, convenzioni

- **OS**: Windows 10 (1809+) / Windows 11, x64. Per-utente, **mai admin**.
- **Runtime .NET**: WPF, publish **self-contained single-file**
  (`PublishSingleFile`, `IncludeNativeLibrariesForSelfExtract`); nessun .NET
  da installare sull'utente. Target: **LTS corrente** al momento dello
  sviluppo (sulla macchina di sviluppo ci sono SDK 5.0 e 9.0; il 9 è STS —
  valutare l'LTS all'avvio dei lavori).
- **Layout nel repo**: `manager/` con `HavcManager.sln`, progetti
  `HavcManager.Core` (logica pura, testabile) e `HavcManager.App` (WPF).
  Versione propria del manager (indipendente da `havc`), in
  `Directory.Build.props`.
- **Artefatto**: `HAVC-Setup-<ver>.exe` (asset della release; nome definitivo
  deciso all'upload). A installazione avvenuta il manager si copia in
  `<install>\HAVCManager.exe`.
- **Convenzioni**: codice e commenti in **inglese** (`AGENTS.md` §9); stringhe
  UI centralizzate (`.resx`), **UI in inglese** (v0; altre lingue
  eventualmente in seguito, senza modifiche strutturali). Anche le stringhe
  visibili di bootstrap/doctor (mostrate nel progresso) sono in inglese.
- **Firma**: nessuna per ora (D1); l'avvertenza SmartScreen va nelle note
  della release (il packaging è irrilevante per SmartScreen — vedi D8).

---

## 3. Architettura

- **HavcManager.Core**: `ManifestClient` (fetch/parse `release.json`),
  `Downloader` (HttpClient + verifica sha256), `BootstrapRunner` (subprocess +
  parser eventi `--json-progress`), `StateStore` (`install.json`), `Preflight`
  (OS/GPU/spazio), `UpdateEngine` (classifica, rollback), `ProcessGuard` (lock
  istanze), `Log`.
- **HavcManager.App**: pagine WPF, view-model, dialog.

Flusso generale:

```
[Preflight] → [manifest] → [download runtime+wheel+asset in cache]
            → [runtime\python -m pip install <wheel>]
            → [runtime\python -m havc.install --json-progress]
            → [verify OK?] → [stato + scorciatoie + registrazione]
                 └── FAIL → [rollback] → [stato dirty]
```

- **Regole fisse**: CWD del bootstrap = cartella di installazione (mai un
  checkout — bug CWD del 2026-10-04); output in UTF-8; ogni download verificato
  sha256 prima dell'uso.

---

## 4. Stato locale — `install.json` (schema v1)

Scritto e letto **solo dal manager** (il bootstrap v0 resta stateless).
Path: `<install>\install.json`. Campi:

- `schema`: 1;
- `manager_version`: versione del manager che ha scritto lo stato;
- `app_version`: versione `havc` installata;
- `installed_at`, `updated_at`: timestamp ISO-8601;
- `install_dir`: percorso assoluto; `models_dir` è accettato per compatibilità
  (schema additivo) ma dalla 0.1.8 non viene più scritto — i modelli stanno
  in `<install>\comfy_bridge\models` (§7, D14);
- `runtime`: `{name, sha256, python}` — runtime provisionato (dal manifest);
- `components`: `["server", "gui"]` (fissa in v0);
- `dinov2`: true (D10);
- `backend_default`: modello di default per *Start server* (v0: `"qwen21"`
  con ≥ 32 GB di RAM, `"longcat3"` sotto soglia — `longcat_gguf_q3.json`;
  modificabile a mano). Il manager non offre scelta modello: gli altri
  modelli si selezionano dalla GUI di HAVC;
- `last_verify`: `{ts, ok, app_version}` — esito dell'ultima verifica
  `havc doctor`;
- `previous`: `{app_version, wheel, sha256}` — snapshot per il rollback.
- `dirty`: `true` quando un update è fallito **e** il rollback non è
  riuscito (§6.3); si azzera con un ripara/update riuscito.

Regole: schema **additivo** (campi nuovi non rompono manager vecchi);
`lock_hash`/`env_version` rimandati (il manifest non li espone ancora: campi
additivi quando ci saranno). Le ultime **2 wheel** restano in
`<install>\cache\`; il manifest dell'ultimo check resta in
`<install>\cache\release.json`.

Registro (HKCU): `Software\HAVCServerDiT` → `InstallDir`; voce di
disinstallazione in `...\CurrentVersion\Uninstall\HAVCServerDiT`
(DisplayName, DisplayIcon, DisplayVersion, Publisher, UninstallString).

---

## 5. Contratto con il bootstrap

Invocazione standard dal manager:

```
<install>\runtime\python\python.exe -m havc.install
    --install-dir <install>
    --wheel <cache>\havc-<ver>-py3-none-any.whl
    --assets-dir <cache>\assets
    --with-dinov2
    --default-model qwen21-viggle  # sotto 32 GB di RAM: longcat-gguf
    --json-progress
```

- **Eventi** consumati (PHASE0_SPEC §5): `plan`, `step_begin`, `step_ok`,
  `step_skip`, `step_error`, `log`, `result`. La UI mappa: step → riga di
  stato; `log` → pannello espandibile; `step_error.error`/`remediation` →
  dialog con rimedio.
- **Exit code**: `0` = ok (anche tutto-skip), `1` = passo fallito (→ rollback
  negli update), `2` = errore d'uso (bug del manager).
- Il passo `verify` interno esegue già `havc doctor` e fallisce il run se il
  doctor segnala FAIL: il run è riuscito solo con exit 0 **e** `result.ok`.
- Prima del run il manager aggiorna la wheel del bootstrap nel runtime:
  `runtime\python -m pip install --force-reinstall --no-deps <wheel>` (flusso
  a due stadi, già verificato).
- **Nuove opzioni bootstrap (Fase 1)**:
  - `--comfy-zip <zip>` (**implementato il 05-10**, con
    `comfy_bridge_v0.30.zip`): comfy_bridge locale per staging/offline; il
    passo `comfy-bridge` usa anche la copia in `--assets-dir` (dal manifest)
    e in mancanza scarica dall'URL pinnato (sha256). Il seed/wiring dei
    settings GUI (`model_name`/`model_precision`) è di `--default-model`;
  - `--default-model <nome>` (**implementato nel bootstrap il 05-10**): nome
    GUI del modello di default per il seed/wiring dei settings
    (`longcat-gguf` seeda anche `model_precision` = `q3`); il manager lo
    passa a install/update/ripara — `qwen21-viggle`, oppure `longcat-gguf`
    quando il preflight rileva RAM < 32 GB;
  - `--with-dinov2` già esiste: il manager lo passa **sempre** (D10).
- `--runtime-zip`/`--tools-zip` non usati dal manager (download diretti da URL
  pinnati, con cache nella cartella di installazione).
- **Cancel cooperativo (implementato nel bootstrap il 05-10)**: per fermare un
  run il manager crea `<install>\cache\.stop-request`; il bootstrap lo
  controlla tra un passo e l'altro e si ferma a fine passo corrente (file
  rimosso all'avvio di ogni run). Secondo click del *Cancel*: kill del processo.

---

## 6. Flussi

### 6.1 Rilevamento e ingressi

Il manager (exe scaricato, o `<install>\HAVCManager.exe`) all'avvio cerca
un'installazione esistente: `--install-dir` esplicito →
`HKCU\Software\HAVCServerDiT\InstallDir` → default
`%LOCALAPPDATA%\HAVCServerDiT` (con `install.json` valido). Trovata →
schermata *Update / Repair / Uninstall / Open*; non trovata → wizard di
prima installazione.

### 6.2 Prima installazione (flusso a due stadi)

1. **Preflight**: OS; `nvidia-smi` (nome, driver, VRAM — assente: avviso non
   bloccante); **requisiti del modello di default** (qwen21-viggle: ≥ 12 GB
   VRAM e ≥ 32 GB RAM; sotto 32 GB di RAM il default passa a **longcat-gguf
   Q3** — seed GUI + `backend_default`; avvisi non bloccanti); spazio:
   install ≥ ~30 GB (indicativo — include i pesi: i modelli stanno
   nell'installazione, D14);
   connettività al manifest (se offline: **fallback al `release.json` accanto
   all'exe** — se presente e `--manifest` non è stato passato — altrimenti
   avviso con l'opzione manifest locale).
2. **Folders**: install dir (default `%LOCALAPPDATA%\HAVCServerDiT`); opzioni
   scorciatoie (Start Menu ON, desktop opzionale). Niente scelta "cartella
   modelli" (D14): i modelli stanno nell'installazione.
3. **Manifest**: fetch `release.json` (override `--manifest`/`--release-tag`
   per i test; **fallback a `<exe folder>\release.json`** se il fetch di rete
   fallisce e `--manifest` non è stato passato); mostra versione e note.
4. **Download**: archivio runtime + wheel `havc` + asset wheel +
   `comfy_bridge_v0.30.zip` →
   `<install>\cache\` (nomi originali), ognuno verificato sha256; riuso dei
   file in cache se il digest combacia.
5. **Stadio 1**: estrazione runtime in `<install>\runtime\python` (tar.gz,
   `System.Formats.Tar`); `runtime\python -m pip install --no-deps <wheel>`.
6. **Stadio 2**: run bootstrap (§5) con progresso live sui 23 passi.
7. **Chiusura**: scorciatoie (Start Menu: "HAVC" → `HAVC.vbs`; "HAVC Manager"
   → `HAVCManager.exe`), registrazione disinstallazione, copia del manager in
   `<install>\HAVCManager.exe`, scrittura `install.json`, pagina finale
   (*Open GUI* / *Start server* / *Open work folder* / *log*).

### 6.3 Update incrementale (con rollback)

1. **Lock istanze** (§6.6).
2. Fetch manifest; se `app_version` == `install.json.app_version` → *already
   up to date*; se `requires_env_rebuild` → §6.7.
3. Download delta: nuova wheel (sha256) e asset il cui sha256 differisce
   dalla cache; la wheel precedente resta in cache.
4. **Conferma config** (06-10): se qualche config in `<install>\config`
   differisce da quello dentro la wheel nuova (file presenti su entrambi i
   lati), dialog *Update configuration files* con l'elenco (Yes =
   sostituisci, tenendo `<nome>.json.bak`; No = conserva). La scelta passa
   il flag `--update-configs` al bootstrap. Nessun dialog se l'elenco è
   vuoto; il rollback non chiede mai.
5. Stadio 1 (bootstrap nel runtime) → stadio 2 (run bootstrap con la nuova
   wheel) → exit 0 + `result.ok`.
6. **PASS** → `previous` = snapshot corrente, `app_version` = nuova,
   `last_verify` aggiornato; messaggio con `notes_url`.
7. **FAIL** → **rollback**: reinstallare la wheel precedente nel runtime e nel
   venv (rerun bootstrap con la wheel precedente — il passo `wheel` fa
   `--force-reinstall`) → verify; se anche il rollback fallisce → stato
   `dirty`, dialog con percorso log e istruzioni. Nessun retry automatico.

### 6.4 Ripara

Rerun bootstrap sulla versione installata (wheel già in cache) — stessa
macchina dell'update, senza download nuovo. Usato anche per completare un
`dirty`. Se qualche config installato differisce da quello nella wheel,
l'utente riceve la stessa conferma dell'update (dialog *Update
configuration files*; il rollback non chiede mai).

### 6.5 Disinstallazione

Conferma; checkbox *Also delete the model files* (**default OFF**);
lock istanze; rimozione: scorciatoie, chiave `Uninstall`,
`Software\HAVCServerDiT`, cartella di installazione — con un'eccezione:
`<install>\comfy_bridge\models` **viene preservata** (i modelli costano
decine di GB e un reinstall sulla stessa cartella li riusa), a meno che la
checkbox sia spuntata. Il manager si auto-rimuove: copia di sé in `%TEMP%`,
rilancio da lì (`--uninstall-run`, `--uninstall-delete-models` se richiesto),
`InstallTreeCleanup.Delete` sul percorso.

### 6.6 Lock istanze

Prima di qualunque run che tocchi venv/torch: enumerare i processi con
eseguibile sotto `<install>` (python.exe/pythonw.exe del venv o runtime). Se
presenti: dialog *Close the GUI/server to continue* con *Retry* /
*Terminate now* (kill con conferma). Mai procedere con istanze attive.

### 6.7 `requires_env_rebuild` — v0: blocco esplicito

Se il manifest lo richiede (es. cambio Python): v0 mostra la procedura manuale
(nuova installazione in cartella nuova, poi rimozione della vecchia) e non
tenta il rebuild. Il rebuild automatico (venv accanto → verifica → swap →
rimozione) è Fase 2.

---

## 7. Modelli e comfy_bridge (D14, 2026-10-05 — sostituisce la "cartella modelli" D10)

- **I modelli vivono dentro l'installazione**: `<install>\comfy_bridge\models\…`
  (unet/clip/loras/vae + `.cache` dei download). Il runtime ComfyUI
  (`comfy_bridge/`, zip pinnato `comfy_bridge_v0.30.zip`) è estratto nella
  root; import e percorsi modelli coincidono per costruzione (PHASE0 §2).
- **Preservati** a update/ripara; in disinstallazione restano salvo la
  checkbox *Also delete the model files* (§6.5). Reinstall sulla stessa
  cartella ⇒ riuso senza riscarichi.
- **Niente cartella modelli nel wizard** (`--models-dir` ritirata): la cache
  HF usa la posizione di default (`hf_cache` vuoto) ed è condivisa con gli
  altri ambienti.
- I pesi cmnet2 (~1 GB) restano nel pacchetto `vscmnet2`; la soglia disco del
  preflight (install) è ~30 GB (runtime + tool + pesi tipici).

---

## 8. UI (WPF)

**Tutte le stringhe UI sono in inglese** (titoli delle schermate, pulsanti,
dialog, messaggi); quelle citate qui sotto sono i testi di riferimento
(stringhe centralizzate in `.resx`).

Schermate v0 (wizard):

1. **Start** — installazione esistente: *Update / Repair / Uninstall /
   Open*; altrimenti **Welcome** (*Start installation*).
2. **Preflight** — esiti dei check (inclusi VRAM e RAM rispetto ai requisiti
   del modello di default, qwen21-viggle: ≥ 12 GB VRAM, ≥ 32 GB RAM; sotto
   i 32 GB di RAM il default diventa longcat-gguf Q3).
3. **Folders** — install dir, scorciatoie (nota: i modelli stanno in
   `<install>\comfy_bridge\models`).
4. **Components** — *Server+GUI* (fisso in v0); riga informativa: *DINOv2
   weights included*.
5. **Summary** — cosa verrà scaricato.
6. **Progress** — barra + lista dei 23 passi con stato (*pending* / *running* /
   *skipped* / *ok* / *error*), log espandibile, pulsante *Cancel* (termina a
   fine passo corrente; lo stato resta recuperabile con *Repair*).
7. **Finish** — *Open GUI* · *Start server* · *Open work folder* · *Show log*.

Finestra principale (installato): stato (versione app, esito ultima verifica,
cartella di installazione, spazio), pulsanti **Open GUI**, **Start server** (avvia col
modello di default `backend_default`; gli altri modelli si scelgono dalla GUI
di HAVC), **Check for updates**, **Repair**,
**Uninstall**, **Log**; sezione *About* con link al download del manager
aggiornato (v0: link, niente auto-update).

Dialog principali: *Update available* (versione + note), *Close the GUI/server
to continue* (§6.6), *Update failed — rolled back*, *Update failed* (stato
`dirty`), conferma di disinstallazione (con checkbox *Also delete the models
folder*); in caso di rollback, messaggio dedicato + log.

---

## 9. Log e diagnosi

- `<install>\logs\manager-<yyyyMMdd>.log` (testo; rotazione semplice: ultimi
  10 file);
- output bootstrap per run: `<install>\logs\bootstrap-<ts>.jsonl` (eventi
  grezzi);
- ogni errore in UI: messaggio + `remediation` (dal bootstrap) + pulsante
  *Open log*;
- la finestra principale mostra l'esito dell'ultima verifica (`last_verify`).

---

## 10. Sicurezza

- HTTPS obbligatorio; **sha256 verificato su ogni artefatto** prima dell'uso
  (runtime, wheel, asset);
- nessun privilegio admin; scritture solo entro: install dir, models dir,
  cache pip, HKCU, Start Menu/Desktop;
- nessuna esecuzione di codice non verificato; nessun git; nessun
  servizio/scheduler; nessun dato inviato (no telemetria);
- il manifest è **l'unica fonte delle versioni**; il manager non ha versioni
  hard-coded di `havc` (solo del proprio schema).

---

## 11. Distribuzione e aggiornamento del manager

- Asset della release: `HAVC-Setup-<ver>.exe` (+ `release.json`); note con
  avvertenza SmartScreen (D1: *Windows protected your PC* → *More info* → *Run anyway*) e sha256 pubblicati.
- URL manifest di default:
  `https://github.com/dan64/HAVCServerDiT/releases/latest/download/release.json`;
  per i test: `--release-tag <tag>` oppure `--manifest <file|url>`. Se il
  fetch fallisce e `--manifest` non è stato passato, il manager ripiega sul
  **`release.json` nella cartella dell'exe** (uso "portable"/offline).
- Politica release (05-10): fino alla prima release **ufficiale** (che
  partirà dalla versione **1.1.0**) le release del flusso installer sono
  **pre-release** (mai "Latest": il marker resta su `v1.0.0` legacy) →
  l'URL manifest di default resta non risolvibile fino ad allora; i test
  usano `--release-tag <tag>` o il fallback locale (§6.2).
- Canali `stable`/`beta` (campo `channel` del manifest): v0 = stable; il
  supporto beta è una preferenza futura.
- Auto-update del manager: v0 **solo link** al download; in Fase 2, campo
  additivo `manager` nel manifest + sostituzione guidata.

---

## 12. Test e verifica

- **Unit** (`HavcManager.Core`, xUnit): parsing del manifest, confronto
  versioni, verifica sha256, macchina a stati di update/rollback, generazione
  dello stato.
- **Integrazione** (manifest locale via `--manifest file`):
  - install nuova in cartella scratch (asset reali dalla cache);
  - update vA→vB su copia del test install (`D:\HAVCServerDiT_Test`),
    rieseguendo il flusso già verificato a mano (log (14));
  - ripara dopo corruzione intenzionale (file GUI modificato → ripristino;
    config rimossa → ricopiata);
  - rollback forzato (wheel "nuova" corrotta → rollback atteso e stato
    coerente);
  - lock istanze (GUI avviata → blocco e terminazione).
- **End-to-end** su VM pulita (checklist PHASE0_SPEC §9 + wizard completo)
  prima della release.
- Smoke rapido su ogni build: `--plan` del bootstrap + `havc doctor`.

---

## 13. Milestone Fase 1

- **M1** — skeleton: soluzione `manager/`, Core (manifest, downloader, runner),
  UI minima *Start installation*.
- **M2** — prima installazione end-to-end (preflight, cartelle, download, due
  stadi, progresso, chiusura, disinstallazione). **Completata il 05-10**
  (log (24) in `AGENTS.md`).
- **M3** — update incrementale + rollback + ripara (sul test install) + lock
  istanze. **Completata il 05-10** (log (29) in `AGENTS.md`).
- **M4** — rifinitura UI, log, scorciatoie/registrazione, tag di test; poi run
  in VM. **Rifinitura completata il 06-10** (log (46): retention log,
  validazione manifest, link *Open log folder* nei dialog d'errore, refresh
  della registrazione; scorciatoie/registro verificati sul campo). **Run in
  VM saltata** su richiesta dell'autore (06-10); "tag di test" = le
  pre-release `v0.1.x` già usate per i test reali. Aperto: asset
  `HAVC-Setup-<ver>.exe` (publish single-file del manager, §11).

---

## 14. Decisioni recepite

- **D1** niente firma (SmartScreen accettata + istruzioni); **D8** niente Inno
  (l'exe è l'installer); **D9** UI WPF;
- **D10** (rivista da **D14**, 2026-10-05): wizard *Server+GUI* (v0), DINOv2
  inclusi; i modelli stanno in `<install>\comfy_bridge\models` (preservati in
  disinstallazione salvo richiesta), niente cartella modelli utente;
- **D11** nunchaku pin + patch + mirror (nessun impatto sul manager oltre agli
  URL);
- Fase 0 (PHASE0_SPEC): `--json-progress`, "install = update", `release.json`,
  `havc doctor`, layout di installazione.

**Questioni da chiudere all'avvio dei lavori**: nome definitivo dell'exe;
target .NET (LTS corrente); dettagli estetici della UI.
