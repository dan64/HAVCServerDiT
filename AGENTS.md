# AGENTS.md — HAVCServerDiT (cartella progetto)

> **Memoria di lavoro del progetto** per agenti AI e sviluppatori.
> Copre il filone **"installazione semplificata"**: installer grafico, distribuzione
> come wheel pip, procedura di update. Va aggiornato a ogni avanzamento —
> vedi §9 per le regole di manutenzione.
>
> **Ultimo aggiornamento:** 2026-10-04
>
> Contesto cartelle: questa è la cartella **pubblica** del progetto
> (`D:\PProjects\HAVCServerDiT`, remote `github.com/dan64/HAVCServerDiT`).
> Esiste una cartella di **sviluppo locale** `_dev` (`D:\PProjects\HAVCServerDiT_dev`,
> remote bare locale `E:\REPO\HAVCServerDiT_dev.git`) con un *suo* `AGENTS.md`
> che documenta architettura e cronologia del progetto (backend, GUI, sessioni) —
> questo file invece è focalizzato sul piano installer/release.
> `_dev` è un laboratorio locale **deliberato**: non va pubblicato; la promozione
> verso il repo pubblico è un passo manuale separato (sincronizzazione per copia
> file — le due storie git sono separate, 0 commit in comune).

---

## 1. Obiettivo

Il progetto è **gratuito e open source**. L'installazione attuale è troppo
complessa per utenti Windows non tecnici: richiede git, Python 3.12 "esatto",
pip con pin di versione, patch di `site-packages`, download di pesi e tool
esterni. Obiettivo di questo filone di lavoro:

1. **Installer grafico** (proposta principale: un'app **C#/WPF "manager"**
   auto-contenuta; vedi §4) che esegue l'intera procedura di installazione.
2. **Distribuzione del codice Python del progetto come wheel pip**
   (installabile dall'installer stesso).
3. **Procedura di update** quando il programma è già installato
   (requisito esplicito dell'utente, 2026-10-04).

---

## 2. Decisioni prese (confermate)

- **D1 — Niente firma del codice** per ora (04-10): l'autore non intende
  spendere per un certificato; nella release dell'installer va un avviso su
  SmartScreen ("Windows ha protetto il PC" → *Ulteriori informazioni* →
  *Esegui comunque*) + checksum SHA256 pubblicati. La firma si può aggiungere
  in qualsiasi momento **senza cambiare l'architettura**.
- **D2 — L'installer deve prevedere l'update** di un'installazione esistente
  (04-10). Requisito esplicito: ri-esecuzione del setup = modalità update,
  oltre al controllo aggiornamenti dall'app.
- **D3 — `_dev` resta un laboratorio locale** (04-10): nessuna pubblicazione,
  nessun backup/push su GitHub della sua storia. Il lavoro installer riguarda
  il repo pubblico (per CI/release/update).
- **D4 — Lo sviluppo della Fase 0 avviene sul repo pubblico** (04-10), su
  branch dedicato `feature/installer` in un **worktree separato**
  (`D:\PProjects\HAVCServerDiT_installer`), così la cartella principale resta
  operativa. I `.cmd` e i workflow esistenti restano invariati.
- **D5 — Runtime Python provisionato e pinnato; git escluso** (04-10). Niente
  Python di sistema e niente embed ufficiale (verificato: privo di
  tkinter/venv/ensurepip). Si usa una build **python-build-standalone**
  (Astral) `3.12.15 install_only_stripped` — 21 MB, sha256 `6fba7f2a…`,
  verificato anche contro il `digest` GitHub — mirrorato il 04-10 nella release
  `runtime-312` (asset invariato; download dal mirror verificato end-to-end).
  L'installer **non installa git**:
  all'utente finale non serve (né per installare né per aggiornare).
- **D6 — La GUI è il front-end di default dell'installazione** (04-10). Il
  launcher principale (`HAVC.cmd` / `HAVC.vbs`, doppio click) apre la GUI, che
  gestisce il server come già fa dal 2026-09-30; il server console resta
  disponibile con `HAVC-Server.cmd [int4|fp4|q3|q4|longcat|qwen21]`.
  Layout: `<install>\gui` (GUI + scripts + settings pre-seedati),
  `<install>\config` (condivise da GUI e server), `<install>\tools`
  (x265/x264/mkvmerge — NVEncC ancora da integrare: è un `.7z`). I launcher
  sono generati dal bootstrap (ASCII, scritti con CRLF).
- **D7 — vs-cmnet2 completata dall'installer** (04-10): plugin e pesi
  scaricati automaticamente e pinnati (sha256) — `plugins_win.zip`
  (vs-cmnet2 v1.0.0), checkpoint DINOv3 + `dinov3-vitb16.zip` (cmnet2
  **v1.3.0**/v1.1.0), pesi DINOv2 legacy (cmnet2 v1.0.0) opzionali dietro
  `--with-dinov2`. Attenzione: il link "v1.2.0" nei README (GUI e vs-cmnet2)
  è morto — corretto qui in `GUI/README_GUI.md`, da correggere anche nel
  README di vs-cmnet2.

---

## 3. Fatti verificati (stato al 2026-10-04)

Installazione Python (server), da `install.cmd` — 6 passi numerati (1, 2, 2b, 3, 4, 5):

- PyTorch 2.10.0+cu130 da `https://download.pytorch.org/whl/cu130` (torchvision/torchaudio abbinati)
- Nunchaku 1.2.1 da URL wheel GitHub release (`nunchaku-1.2.1+cu13.0torch2.10-cp312...whl`)
- **Re-pin di torch** (Nunchaku può trascinare una versione più nuova via `accelerate`)
- `python patch_nunchaku.py` (patch a `site-packages`, ha `--check`/`--revert` con `.bak`)
- diffusers 0.37.0.dev0 da **wheel locale** in `packages/` (mai da GitHub: le dev build ≥0.39 rompono l'API)
- Restanti deps con pin: `transformers==4.57.6`, `accelerate==1.12.0`, `huggingface_hub>=0.26.0`,
  `Pillow>=10.0.0`, `scipy`, `av`, `torchsde`, `gguf`, `comfy-aimdo==0.5.5`, `comfy-kitchen==0.2.35`

Installazione GUI (`GUI/README_GUI.md`), passi ulteriori:

- `pip install -r GUI/requirements.txt` → Pillow, tkinter_embed, FreeSimpleGUI, send2trash, tkinterdnd2, `VapourSynth==74`
- wheel `vscmnet2` da `packages/` (es. `vscmnet2-1.2.1-py3-none-any.whl`)
- wheel `spatial_correlation_sampler-0.5.0-cp312-cp312-win_amd64.whl` (**compilata per cp312 + torch 2.10+cu130: combo esatta**)
- **pesi DINOv3 scaricati a mano** in `.venv\Lib\site-packages\vscmnet2\weights\` (+ `dinov3-vitb16.zip` da estrarre) — unico download rimasto manuale
- **tool esterni non-Python** in `GUI/tools/`: x265, x264, mkvmerge (`tools.zip` della Release 1.0.0), NVEncC (da GitHub) — non versionati
- Python **3.12 obbligatorio** (le wheel nunchaku e spatial_correlation_sampler sono cp312)

Altri fatti rilevanti:

- I **pin sono duplicati in 4 posti**: `install.cmd`, `quick_update.cmd`, `README.md`, `GUI/README_GUI.md` → rischio drift.
- Il progetto **già distribuisce wheel** in `packages/` (diffusers, vscmnet2, spatial_correlation_sampler) e `dist/` (tools.zip, wheel storiche): la pratica esiste.
- **Ambiente di riferimento per i pin = `_dev/.venv`** (2026-10-04: torch 2.10.0+cu130, nunchaku 1.2.1+cu13.0torch2.10, diffusers 0.37.0.dev0, comfy-kitchen 0.2.35, comfy-aimdo 0.5.5, transformers 4.57.6, vscmnet2 1.2.1, VapourSynth 74). Il `.venv` della cartella pubblica **non** è allineato (vscmnet2 1.0.4, diffusers 0.38.0, comfy-kitchen 0.2.10): non usarlo come riferimento.
- Pesi DiT auto-scaricati al primo avvio (nunchaku ~15-30 GB); cache HuggingFace controllabile via `cache_dir` nel config (default `~/.cache/huggingface`).
- `installer/` in questa cartella contiene per ora solo `installer/Icona-havc-dit.ico` — **non versionato**; da committare quando parte il lavoro installer.
- Repo pubblico verificato pulito (04-10): solo `main` + tag `v1.0.0`; nessun artefatto del laboratorio in nessun commit; nessun repo `_dev` su GitHub (la vecchia push interrotta non ha lasciato ref visibili).
- Rapporto tra le due cartelle: contenuti **byte-identici** per i file condivisi, storie git **separate** — la sincronizzazione è per copia file (pratica attuale, nessun merge possibile).

---

## 4. Architettura proposta (3 pezzi)

### a) Bootstrap Python — la verità (idempotente, convergente)

- **Principio guida: "install = update da stato vuoto".** Ogni passo *verifica prima di agire* e salta ciò che è già a posto → aggiornare e riparare sono lo stesso codice dell'installare.
- Comando `havc-install` con **`--json-progress`** su stdout (una riga JSON per evento: fase, percentuale, messaggio, errore) — l'interfaccia che rende l'installer grafico un guscio sottile.
- **Wheel del progetto**: `havc` (server: `dit_rpc_server.py`, `dit_colorize_main.py`, `comfy_bridge/`, `config/`) + `havc-gui` (GUI + `scripts/` + assets), con entry points `havc-server`, `havc-gui`, `havc-doctor`, `havc-install`.
- **`havc doctor`**: check unico e riusabile (import, versioni vs lockfile, patch nunchaku, `torch.cuda.is_available()`, tool presenti, pesi presenti, GPU/driver). È anche il criterio PASS/FAIL di fine update.
- **Lockfile unico** (`requirements-lock.txt` + constraints): l'unica fonte delle versioni, condivisa da wheel, bootstrap, `install.cmd`/`quick_update.cmd` (che restano come wrapper per utenti esperti), CI.
- **Cosa NON è pip-abile** (resta responsabilità del bootstrap): torch cu130 (l'`--index-url` non è esprimibile nei metadata di un pacchetto), wheel nunchaku + patch (valutare in futuro una wheel nunchaku già patchata vendorizzata), binari esterni, pesi. Driver NVIDIA: **solo check**, mai installazione.

### b) Manifest di release — il contratto

- `release.json` allegato a ogni release GitHub. Contenuto: `app_version`, elenco wheel + **sha256**, hash del lockfile, flag `requires_env_rebuild` (es. cambio Python), aggiornamenti di pesi/tool **con hash** (per scaricare solo i delta), note di versione.
- **L'installer non conosce nessuna versione: le legge qui.**
- Generazione: dapprima con script locale nel repo; in seguito GitHub Actions al tag (CI opzionale all'inizio — quello che conta è che gli artefatti nascano nel repo pubblico).

### c) Manager C# — il guscio

- App C# **self-contained single-file** (nessun runtime .NET da installare); UI wizard + progresso + log + bottoni "Apri GUI", "Avvia server", "Controlla aggiornamenti", "Ripara".
- Al primo avvio: preflight (GPU/VRAM/spazio disco via `nvidia-smi`), scelta backend suggerita dalla GPU, componenti, cartelle; crea scorciatoie (Start Menu/desktop) e voce di disinstallazione. L'utente finale **non vede mai git**.
- **Inno Setup: NON come motore.** Inno non ha un downloader nativo e questa installazione *è* fatta di download (GB); usarlo con Pascal Script significherebbe riscrivere peggio il bootstrap. Al massimo, in Fase 2, guscio esterno opzionale (copia file del manager + `[Run]`); non richiede di riprogettare nulla.
- **Provisioning Python** (pollo-uovo del bootstrap): raccomandato l'**installer ufficiale python.org 3.12 silenzioso per-utente** (`/quiet InstallAllUsers=0 PrependPath=0` — include tkinter, che serve alla GUI, e non richiede admin). L'**embeddable zip è sconsigliato** (niente tkinter → GUI rotta). `uv`/python-build-standalone da valutare (veloce), ma verificare che i build includano tkinter.

---

## 5. Procedura di update (design)

**Stato locale** — `install.json` nella cartella di installazione: schema/versioni
(`app_version`, hash lockfile, versione env), path Python/venv, componenti
installati, backend scelti, pesi (nome+hash), tool, esito ultima verifica,
snapshot precedente per rollback.

**Dove si installa** — default `%LOCALAPPDATA%\HAVCServerDiT` (per-utente, no
admin), cartella scegliibile. **Nel wizard va esposta la cartella dei modelli**
(`HF_HOME`/`cache_dir`): i 15-30 GB non devono finire silenziosamente su C:.

**Algoritmo** (stesso motore per setup re-run e check in-app):

1. Lock di istanza: se server o GUI gestita sono in esecuzione, chiedere di chiuderli (mai aggiornare torch mentre è importato).
2. Fetch di `release.json` (fallback offline: l'installazione esistente continua a funzionare).
3. Classifica: **incrementale** (stesso env) o **rebuild** (`requires_env_rebuild`, es. cambio Python).
4. Incrementale: scarica wheel nuove in `cache/` + verifica sha256 → `pip install --force-reinstall --no-deps` del pacchetto principale → riconcilia le dipendenze dal lockfile (pip è idempotente) → ri-applica la patch (`--check`) → aggiorna pesi/tool **solo se hash cambiati** → migrazione settings (la GUI ha già la migrazione automatica).
5. Rebuild (raro): nuovo venv accanto → installa lì → verifica → swap cartelle → rimuovi il vecchio. Mai ricreare il venv "per default" (torch da solo sono GB).
6. **Verifica finale `havc doctor`**: PASS → stato ok; FAIL → **rollback** (reinstalla la wheel precedente dal `cache/`, stato `dirty`, dialog con percorso log). Si tengono le ultime 2 versioni per il rollback.

**Ingressi**: (a) ri-run del setup → rileva l'installazione esistente e propone
*Aggiorna / Ripara / Disinstalla*; (b) "Controlla aggiornamenti" nel manager.
**Update del manager stesso**: ri-scarica l'exe dal release (link nel dialog);
l'update dell'ambiente è indipendente (e resta il punto forte della separazione).

**Modalità di installazione** (wizard): *Server only* / *Server+GUI* / *GUI-only*
(il progetto già supporta client e server su macchine diverse).

---

## 6. Piano a fasi

- **Fase 0 — Fondamenta (nessuna UI).** Wheel del progetto + lockfile unico +
  `havc doctor` + bootstrap idempotente con `--json-progress`. Test end-to-end
  su **VM/Windows Sandbox pulita** (mai sul daily driver). Risultato: installazione
  "one command" anche senza GUI, e testabilità. *Stima grezza: 1-2 settimane.*
- **Fase 1 — Manager C# v0.** Wizard, progresso, state file, update via
  manifest. *Stima grezza: 2-4 settimane.*
- **Fase 2 — Rifiniture.** Rollback/repair in UI, scelta cartella modelli,
  eventuale guscio Inno opzionale, uninstaller. *Stima grezza: ~1 settimana.*
- **Fase 3 — (solo se mai) firma del codice.** Nessun impatto sull'architettura.

**Stato Fase 0 (04-10):** avviata sul branch `feature/installer`. Spec:
`installer/PHASE0_SPEC.md`. Primi componenti implementati e verificati
(wheel `havc`, lockfile, `havc-install`, `havc doctor`). Prossimi passi della
Fase 0: run end-to-end su VM/Sandbox pulita, prima release di prova con
`release.json`, verifica dell'update incrementale.

---

## 7. Questioni aperte (decisioni da prendere)

1. ~~Dove sviluppare la Fase 0~~ → **risolta il 04-10 (D4)**: branch
   `feature/installer` in un worktree separato; venv leggeri di sviluppo
   (`.venv-dev`, `.venv-test`, ignorati da git); icona installer committata.
2. **Inno Setup:** confermare "non motore" (raccomandazione); eventualmente
   guscio in Fase 2.
3. **UI C#:** **WPF** (raccomandato, solo-Windows) vs Avalonia (se un domani
   cross-platform).
4. **Provisioning Python:** python.org silenzioso per-utente (raccomandato) vs
   `uv` (da verificare tkinter).
5. **Default del wizard:** componenti preselezionati (proposta: *Server+GUI*) e
   default cartella modelli.
6. **Wheel nunchaku patchata vendorizzata** (eliminerebbe il post-step di patch
   a `site-packages`, più deterministico) — da valutare.

---

## 8. Riferimenti

- `install.cmd`, `quick_update.cmd`, `start_server.cmd`, `run_server_*.cmd` — installazione e avvio attuali
- `installer/PHASE0_SPEC.md` — specifica Fase 0 (packaging, lockfile, bootstrap, `release.json`)
- `GUI/README_GUI.md` — installazione GUI, pesi DINOv3, tool esterni
- `packages/`, `dist/` — wheel e tool già distribuiti
- `_dev/AGENTS.md` (in `D:\PProjects\HAVCServerDiT_dev`) — architettura e cronologia del progetto
- `patch_nunchaku.py` — patch con `--check`/`--revert` (già idempotente-friendly)

---

## 9. Manutenzione di questo file

- Ogni avanzamento aggiunge una voce datata in coda alla sezione pertinente;
  le decisioni passano da §7 (aperte, con raccomandazione) a §2 (prese,
  con data) senza riscrivere le voci precedenti.
- Convenzione: prosa in **italiano**, identificatori/percorsi/comandi in
  inglese o nella forma originale.
- Non duplicare qui l'architettura del progetto (vive in `_dev/AGENTS.md`);
  questo file resta focalizzato su installer/wheel/update/release.

### Log aggiornamenti

- **2026-10-04** — Creato il file. Contenuto: obiettivo (§1), decisioni D1-D3
  (§2), fatti verificati su installazione/repo (§3), architettura a 3 pezzi (§4),
  design della procedura di update (§5), piano a fasi (§6), questioni aperte (§7).
- **2026-10-04 (2)** — **Fase 0 avviata.** Creato il worktree
  `D:\PProjects\HAVCServerDiT_installer` sul branch `feature/installer`.
  Scritta la spec `installer/PHASE0_SPEC.md` e implementati i primi
  componenti: wheel `havc` (build hook che incorpora `config/`,
  `requirements/`, `comfy_bridge/` — sorgente unica nel repo), lockfile
  `requirements/{torch,nunchaku,core}.txt` (pin dall'ambiente di riferimento
  `_dev`), `havc-install` (bootstrap idempotente, `--json-progress`),
  `havc doctor`. Verifiche: build wheel 11,0 MB (503/503 file `comfy_bridge`,
  zero cache, entry point corretti), install in venv pulito, `doctor` **tutto
  verde** sull'ambiente `_dev` (inclusi patch nunchaku e CUDA), `--plan` e run
  reale parziale idempotente. Prossimi: end-to-end su VM/Sandbox, release di
  prova con `release.json`, flusso di update incrementale.
- **2026-10-04 (3)** — **Provisioning del runtime implementato (D5).** Nuovo
  passo `runtime` in `havc-install`: archivio python-build-standalone 3.12.15
  pinnato (versione + sha256), download via `urllib` → verifica → estrazione in
  `<install>\runtime\python`; varianti `--runtime-zip` (staged/offline),
  cache locale, `--use-system-python` (sviluppo); nuovo flag `--install-dir`
  (sostituisce `--env-dir`). Verifiche: estrazione locale e download reale
  (21 MB) con sha256 ok, venv creato dal runtime con tkinter funzionante
  (`venv: 3.12.15 | tkinter 8.6`), idempotenza, rifiuto con sha256 errato
  (exit 1), eventi JSON. Resta da fare: upload del mirror (`runtime-312`) su
  ok dell'utente; poi `RUNTIME["url"]` passa al mirror.
- **2026-10-04 (4)** — **Mirror del runtime pubblicato.** Release `runtime-312`
  su GitHub con l'asset pinnato (22.011.023 byte; sha256 confermato dal
  `digest` GitHub). `RUNTIME["url"]` ora punta al mirror; download end-to-end
  dal mirror verificato (sha256 ok); `v1.0.0` resta la release "Latest".
- **2026-10-04 (5)** — **`comfy_bridge/blueprints/` escluso dalla wheel**
  (scelta utente, opzione b): 96 file / 3,1 MB (80 template UI + 14 shader
  `.frag`), nessun riferimento nel codice. Wheel: 11.034.021 → 10.644.120 byte
  (−389.901 compressi). Trovato e corretto per strada un bug del build hook:
  i file già in `build/lib` restavano impacchettati nelle build successive —
  ora la destinazione viene azzerata prima di ogni copia (copia
  deterministica). Da confermare col run end-to-end in VM: se un percorso reale
  dovesse mai richiedere i blueprint, basta togliere la voce da `COPIES` in
  `setup.py`.
- **2026-10-04 (6)** — **Generatore `release.json`** (`installer/make_release.py`):
  scansiona gli artefatti, calcola sha256/dimensioni, legge versione e blocco
  `runtime` dalle fonti uniche, scrive il manifest; `--verify` ricontrolla un
  manifest esistente. Test: generazione su staging (wheel `havc` 0.1.0 +
  diffusers), verify ok, rifiuto di `--version` incoerente, verify fallita su
  artefatto troncato (exit 1). Staging pronto in `dist/staging-v0.1.0/`
  (fuori dal repo) per la prima release di prova.
- **2026-10-04 (7)** — **Release di prova `v0.1.0-alpha` pubblicata**
  (prerelease, `--latest=false`): asset = wheel `havc` 0.1.0, wheel diffusers,
  `release.json` (manifest generato da `installer/make_release.py`, URL sul
  tag corretto). Post-verifica: digest GitHub coerenti col manifest, manifest
  remoto identico al locale, `HEAD` della wheel 200, `v1.0.0` resta "Latest".
  Prossimo uso: test del flusso di update (Fase 1) e riferimento per il run
  in VM.
- **2026-10-04 (8)** — **End-to-end su cartella di test + 2 bug corretti.**
  Installazione completa in `D:\HAVCServerDiT_Test` col flusso a due stadi del
  futuro manager (runtime dal mirror → wheel nel runtime → `havc.install`).
  Il primo run ha rivelato due bug di CWD: i check di skip leggevano metadata
  ombreggiati dal checkout nel CWD (`havc.egg-info` → il passo `wheel` non
  installava il progetto nel venv!) e `verify` importava `havc` dalla sorgente
  invece che dal venv. Fix: CWD neutrale per tutti i processi figli in
  `havc/install.py`. Trovato anche che il pin `diffusers` mancava nel lock
  (aggiunto `requirements/assets.txt`). Wheel ricostruita e asset della
  release `v0.1.0-alpha` aggiornati (`--clobber`); run finale tutto verde con
  `havc doctor` a 15 pacchetti conformi e console script (`havc-server.exe`,
  `havc-doctor.exe`) presenti nel venv.
- **2026-10-04 (9)** — **GUI integrata nell'installazione (front-end di
  default, D6).** Nuovi passi del bootstrap: `configs`, `gui` (file + `.vpy`
  dalla copia nella wheel), `gui-deps` (FreeSimpleGUI/tkinterdnd2/
  tkinter-embed/Send2Trash/VapourSynth==74 + wheel `vscmnet2` e
  `spatial_correlation_sampler`), `tools` (tools.zip pinnato v1.0.0, sha256),
  `gui-settings` (pre-seed solo se assente), `launchers` (`HAVC.cmd`/`.vbs` →
  GUI, `HAVC-Server.cmd`, `HAVC-Doctor.cmd`). Verifiche su
  `D:\HAVCServerDiT_Test`: tutto verde (`havc doctor` a **22 pacchetti** + check
  `gui`), rerun tutto-skip, launcher CRLF verificati, import GUI ok, smoke di
  avvio senza errori. Asset `v0.1.0-alpha` aggiornati (wheel con GUI,
  `vscmnet2`, `spatial_correlation_sampler`, `release.json`). Da fare: NVEncC
  (è un `.7z`), avvio GUI dal manager C#, wiring remoto degli asset.
- **2026-10-04 (10)** — **vs-cmnet2 completata automaticamente (D7).** Nuovi
  passi `cmnet2-plugins` (31 MB), `cmnet2-weights` (~1,05 GB: checkpoint
  DINOv3 da cmnet2 v1.3.0 + `dinov3-vitb16.zip` da v1.1.0) e `cmnet2-dinov2`
  (legacy, `--with-dinov2`, ~740 MB). Download con verifica sha256 + cache;
  check di idempotenza su presenza/dimensione. Verifiche su
  `D:\HAVCServerDiT_Test`: download reali ok, dimensioni identiche al byte
  all'installazione di riferimento, rerun tutto-skip, `havc doctor` a 9 check
  verdi (nuovo check `cmnet2`), dry-run del flag DINOv2 ok. Fix del link
  morto (v1.2.0→v1.3.0) in `GUI/README_GUI.md`.
