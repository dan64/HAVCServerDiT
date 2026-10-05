# AGENTS.md — HAVCServerDiT (cartella progetto)

> **Memoria di lavoro del progetto** per agenti AI e sviluppatori.
> Copre il filone **"installazione semplificata"**: installer grafico, distribuzione
> come wheel pip, procedura di update. Va aggiornato a ogni avanzamento —
> vedi §9 per le regole di manutenzione.
>
> **Ultimo aggiornamento:** 2026-10-05
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

## 0. Come riprendere (handoff — aggiornato al 2026-10-05; SDK 10, VS 2026, M1–M2 — log (21)–(24))

**Dove sta il lavoro**: branch `feature/installer` nel worktree
`D:\PProjects\HAVCServerDiT_installer`; la cartella principale
`D:\PProjects\HAVCServerDiT` è su `main` (la sua vecchia copia superata di
`AGENTS.md` è stata rimossa: finché il branch non arriva su `main`, la memoria
è solo qui). Ultimo commit **pushato**: `7dc346a`; da lì tutto procede a
**commit locali** — push rimandati finché non c'è "qualcosa di stabile"
(regola in §9). Ultimo commit locale della sessione 2: `b8df5c2` (più questo
commit di chiusura).

**Stato a fine sessione 2**: Fase 0 chiusa e verificata (update incrementale
0.1.0→0.1.1 testato, log (14)); decisioni Fase 1 prese (D8–D11, §2); **spec
del manager scritta** (`installer/PHASE1_SPEC.md`); mirror nunchaku pubblicato
(release `nunchaku-1.2.1`); codice, commenti, UI e spec allineati
all'inglese (log (16), (19)).

**Prossimo passo — M4**: rifinitura UI/log, scorciatoie/registrazione, tag di
test, poi run in VM (spec §13). M1–M3 completate; prima installazione reale
riuscita il 05-10 (`D:\HAVC_Manager_Test` — log (28)); update/ripara/rollback/
lock verificati sul campo (log (29)); **modello di default qwen21-viggle**
(nessuna scelta modello nel manager — log (30); sotto 32 GB RAM → longcat-gguf
Q3, log (34)); **disinstallo verificato sul campo** (log (35)). Restano:
pubblicare la release (staging `v0.1.5` in `dist/` — sblocca anche l'URL
manifest di default) e il run in VM; da reinstallare l'install di test
(disinstallata nel test, log (35)).
**Decisione SDK chiusa (05-10)**: target **.NET 10** — SDK **10.0.401**
installato machine-wide (standalone) e **VS 2026** (Community v18.10)
installato lo stesso giorno: l'MSBuild 18.10 compila `net10` (smoke WPF verde)
→ IDE pronto. Vincolo noto: VS 2022 non compila `net10` (l'SDK 10.0.4xx
richiede MSBuild ≥ 18.0; con VS 17.14 il resolver ripiega su SDK 9 →
NETSDK1045). Build sempre possibile anche via `dotnet` CLI (MSBuild 18
interno).

**Installazione di test**: `D:\HAVCServerDiT_Test` — stack completo,
aggiornata a havc 0.1.1 (smoke/update/idempotenza: `install-run8/9/10.log`
nella radice). Check rapido: `venv\Scripts\havc-doctor.exe` (9 verdi); avvio:
doppio click su `HAVC.vbs`.

**Installazione test del manager (wizard)**: `D:\HAVC_Manager_Test` (modelli
`D:\HAVCModels`) — installata il 05-10 via wizard (log (28)), aggiornata fino
a havc **0.1.5**; **disinstallata** il 05-10 nel test di uninstall riuscito
(log (35)) → da reinstallare (con `--manifest` locale finché la release non
è pubblicata). Log dei run in `<install>\logs\bootstrap-*.jsonl`.

**Release coinvolte** (repo `dan64/HAVCServerDiT`; `gh` autenticato come
`dan64`):
- `runtime-312` — mirror del runtime Python (python-build-standalone pinnato)
- `nunchaku-1.2.1` — mirror della wheel nunchaku ufficiale (invariata)
- `v1.0.0` — `tools.zip` + `NVEncC_9.17_x64.zip`
- `v0.1.0-alpha` — release di prova dell'installer (wheel `havc`, asset,
  `release.json`)

**Comandi pronti** (dev Python = `.venv-dev` nel worktree; CWD **neutrale**,
mai il checkout — bug del 04-10):

```powershell
# smoke ambiente di test (atteso: tutto-skip + doctor verde)
Set-Location $env:TEMP
& D:\HAVCServerDiT_Test\runtime\python\python.exe -m havc.install --install-dir D:\HAVCServerDiT_Test

# piano col codice del worktree (veloce, read-only)
Set-Location D:\PProjects\HAVCServerDiT_installer
& .\.venv-dev\Scripts\python.exe -m havc.install --install-dir D:\HAVCServerDiT_Test --plan

# nuova versione: build wheel → staging → manifest
& .\.venv-dev\Scripts\python.exe -m build --wheel --outdir dist
& .\.venv-dev\Scripts\python.exe installer\make_release.py --tag vX --artifacts-dir dist\staging-vX
& .\.venv-dev\Scripts\python.exe installer\make_release.py --verify dist\staging-vX\release.json --artifacts-dir dist\staging-vX

# update end-to-end sul test install (pattern log (14)): wheel nuova nel runtime,
# poi rerun bootstrap con --wheel/--assets-dir → log in install-runN.log
& D:\HAVCServerDiT_Test\runtime\python\python.exe -m pip install --force-reinstall --no-deps dist\staging-vX\havc-<ver>-py3-none-any.whl
```

*EOL*: i file del repo sono **LF** (`.gitattributes`); chi riscrive file
(l'agente o uno script) usi i bytes — niente traduzione newline.

**Mappa del codice nuovo (Fase 0)**: `havc/install.py` = bootstrap 21 passi
(`havc-install`); `havc/doctor.py` = check ambiente (`havc-doctor`);
`havc/runtime.py` = runtime pinnato (download/estrazione); `havc/lockfile.py`
= parsing dei pin; `havc/progress.py` = eventi `--json-progress`;
`havc/paths.py` = percorsi wheel/checkout; `installer/make_release.py` =
manifest `release.json`; `setup.py` = build hook della wheel;
`patch_nunchaku.py` = patch nunchaku. Strumenti una tantum in `dist/`
(ignorata da git): `i18n_strings.py`, `spec_ui_english.py`.

**Regola d'oro**: `havc-install` è idempotente e convergente — rieseguirlo sul
test install deve finire tutto-skip; è il primo smoke per verificare che
l'ambiente è integro.

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
  (x265/x264/mkvmerge + NVEncC 9.17 — il pacchetto `.7z` è stato ripubblicato
  come `NVEncC_9.17_x64.zip` nella Release v1.0.0 e integrato il 04-10).
  I launcher sono generati dal bootstrap (ASCII, scritti con CRLF).
- **D7 — vs-cmnet2 completata dall'installer** (04-10): plugin e pesi
  scaricati automaticamente e pinnati (sha256) — `plugins_win.zip`
  (vs-cmnet2 v1.0.0), checkpoint DINOv3 + `dinov3-vitb16.zip` (cmnet2
  **v1.3.0**/v1.1.0), pesi DINOv2 legacy (cmnet2 v1.0.0) opzionali dietro
  `--with-dinov2`. Attenzione: il link "v1.2.0" nei README (GUI e vs-cmnet2)
  è morto — corretto qui in `GUI/README_GUI.md`, da correggere anche nel
  README di vs-cmnet2.
- **D8 — Inno Setup scartato del tutto** (04-10): non come motore (già deciso)
  e nemmeno come guscio esterno di Fase 2. Non aggiunge nulla: SmartScreen è
  neutro rispetto al packaging (conta firma+reputazione del file; dal 2024
  nemmeno i certificati EV bypassano), e wizard/scorciatoie/voce di
  disinstallazione/uninstaller sono già responsabilità del manager. Si
  rivaluta solo su un requisito concreto (es. distribuzione aziendale
  silenziata).
- **D9 — UI del manager: C# WPF** (04-10): scelta **WPF** al posto di Avalonia
  (il target resta Windows-only; il cross-platform non è un requisito).
- **D10 — Default del wizard** (04-10): default **Server+GUI** (in Fase 1 solo
  questa modalità, + update/ripara; "Server only"/"GUI-only" rimandate). Pesi
  **DINOv2** (~720 MB) inclusi nell'installazione standard. Cartella modelli
  **unica** (cache HF + modelli comfy, con override di `COMFYUI_MODELS_DIR` da
  implementare): pre-compilata "intelligente" (unità con più spazio libero,
  avviso sotto soglia ~50 GB) e **modificabile durante l'installazione**;
  riusata negli update senza riscaricare; in disinstallazione i modelli
  **restano** (cancellazione solo su richiesta esplicita).
- **D11 — Nunchaku: pin + patch + mirror della wheel intatta** (04-10). Si
  resta sull'approccio attuale (patch chirurgica in `patch_nunchaku.py`, con
  `--check`; funziona senza issue e il progetto nunchaku non ha fix in
  programma), ma la wheel upstream **non modificata** viene mirrorata in una
  release del nostro repo — stesso schema di `runtime-312`: asset invariato,
  sha256 `20d8c4ce…` verificato contro il digest GitHub (111.735.072 byte) —
  **pubblicata il 04-10** (release `nunchaku-1.2.1`, download end-to-end
  verificato); `requirements/nunchaku.txt` punta al mirror. La wheel *già
  patchata* (vendorizzata) resta
  un'opzione rinviata con criterio.

- **D12 — Modello di default: qwen21-viggle, nessuna scelta nel manager**
  (05-10). Il manager non offre scelta modello: *Start server* avvia col
  default registrato (`backend_default` = `"qwen21"` → `qwen21_viggle.json`);
  il seed dei settings GUI installa `model_name`/`model_precision` (solo se
  assenti); il preflight verifica i requisiti del default (≥ 12 GB VRAM e
  ≥ 32 GB RAM, avvisi non bloccanti) e **sotto i 32 GB di RAM il default
  diventa longcat-gguf Q3** (`backend_default` = `"longcat3"`, seed
  `longcat-gguf` + precision `q3`; con 16 GB è l'unico modello che gira).
  Gli altri modelli si scelgono dalla GUI di HAVC.

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
- **Inno Setup: NON come motore.** Inno non ha un downloader nativo e questa installazione *è* fatta di download (GB); usarlo con Pascal Script significherebbe riscrivere peggio il bootstrap. ~~Al massimo, in Fase 2, guscio esterno opzionale (copia file del manager + `[Run]`); non richiede di riprogettare nulla~~ → **scartato del tutto il 04-10 (D8)**: nessun vantaggio (SmartScreen neutro; funzioni già coperte dal manager).
- **Provisioning Python** (pollo-uovo del bootstrap): ~~raccomandato l'installer ufficiale python.org 3.12 silenzioso per-utente~~ → **risolto il 04-10 (D5)**: build **python-build-standalone** pinnata (versione + sha256, mirror `runtime-312`), estratta in `<install>\runtime\python`; include tkinter 8.6, venv ed ensurepip. Niente Python di sistema. L'**embeddable zip resta escluso** (verificato: privo di tkinter/venv/ensurepip).

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
  uninstaller. *Stima grezza: ~1 settimana.*
- **Fase 3 — (solo se mai) firma del codice.** Nessun impatto sull'architettura.

**Stato Fase 0 (04-10, chiusura sessione):** **completata.** Realizzati e
verificati: wheel `havc` (+GUI, +comfy_bridge), lockfile unico, `havc-install`
(21 passi: runtime pinnato, stack server, GUI, tool esterni, plugin+pesi
vs-cmnet2), `havc doctor` (9 check), generatore `release.json`, release di
prova `v0.1.0-alpha`, installazione di test completa in
`D:\HAVCServerDiT_Test`, **update incrementale 0.1.0 → 0.1.1** (wheel
sostituita, refresh di GUI/launcher, `verify` verde, rerun idempotente — log
(14)). Spec: `installer/PHASE0_SPEC.md`. Resta solo il run facoltativo su VM
pulita.

**Stato Fase 1 (04-10):** decisioni prese (§7 chiusa: D8–D11) e **spec scritta**:
`installer/PHASE1_SPEC.md` (architettura, flussi, stato, contratto col
bootstrap). M1 completata (log (23)); M2 completata (log (24));
prossimo passo: M3 (update/ripara).

---

## 7. Questioni aperte (decisioni da prendere)

*Tutte risolte al 04-10 (D4, D5, D8, D9, D10, D11); sezione mantenuta come
storico.*

1. ~~Dove sviluppare la Fase 0~~ → **risolta il 04-10 (D4)**: branch
   `feature/installer` in un worktree separato; venv leggeri di sviluppo
   (`.venv-dev`, `.venv-test`, ignorati da git); icona installer committata.
2. ~~Inno Setup~~ → **risolta il 04-10 (D8)**: scartato del tutto (non motore
   né guscio); si rivaluta solo su requisito concreto (es. distribuzione
   aziendale silenziata).
3. ~~UI C#: WPF vs Avalonia~~ → **risolta il 04-10 (D9)**: **WPF**
   (Windows-only; il cross-platform non è un requisito).
4. ~~Provisioning Python~~ → **risolta il 04-10 (D5)**: build
   python-build-standalone pinnata (mirror `runtime-312`); niente python.org,
   niente embed (privo di tkinter/venv).
5. ~~Default del wizard~~ → **risolta il 04-10 (D10)**: *Server+GUI* (Fase 1
   solo questa modalità); pesi DINOv2 inclusi; cartella modelli unica
   pre-compilata (unità con più spazio, avviso sotto soglia) e modificabile.
6. ~~Wheel nunchaku patchata vendorizzata~~ → **risolta il 04-10 (D11)**: si
   mantiene pin + patch (`--check`), con **mirror della wheel ufficiale
   intatta** nel nostro repo (schema `runtime-312`); vendorizzazione rinviata
   con criterio.

---

## 8. Riferimenti

- `install.cmd`, `quick_update.cmd`, `start_server.cmd`, `run_server_*.cmd` — installazione e avvio attuali
- `installer/PHASE0_SPEC.md` — specifica Fase 0 (packaging, lockfile, bootstrap, `release.json`)
- `installer/PHASE1_SPEC.md` — specifica del manager C# (Fase 1: wizard, update/ripara, stato locale)
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
- **Lingua del codice**: commenti e docstring nei file pubblici vanno in
  **inglese** (convenzione dell'autore, 04-10; vale anche per il futuro
  codice C#); l'italiano resta per l'interazione, questa memoria e le spec.
- **Lingua delle stringhe utente**: **inglese** — UI del manager e messaggi
  visibili di bootstrap/doctor (decisione del 04-10); altre lingue solo in
  seguito, con stringhe centralizzate.
- **Push**: rimandati per scelta dell'autore (04-10) finché non c'è
  "qualcosa di stabile"; il tracciamento delle modifiche sono i **commit
  locali** (si committa man mano, senza attese; il push solo su segnale
  dell'autore).
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
- **2026-10-04 (11)** — **NVEncC pubblicato e integrato.**
  `NVEncC_9.17_x64.zip` (100,6 MB, prebuilt) caricato nella Release v1.0.0
  accanto a `tools.zip`; passo `tools` esteso: scarica/estrae entrambi gli
  archivi (estrazione "flat" supportata in `extract_archive`,
  `required_root=None`); check di idempotenza su x265 **e** NVEncC64.
  Verifiche su `D:\HAVCServerDiT_Test`: download reale + estrazione (22 file),
  `NVEncC64.exe --version` → 9.17 (r3600), rerun "tool esterni già presenti".
  Release v1.0.0: corpo aggiornato con la nota dell'asset.
- **2026-10-04 (12)** — **Pesi DINOv2 legacy provati davvero**
  (`--with-dinov2`): 4 file (~720 MB) da cmnet2 v1.0.0 scaricati e depositati
  (weights/ + models/checkpoints/), sha256 spot-check ok, dimensioni identiche
  al byte; rerun idempotente. Il folder di test ora ha tutti e tre i set
  (DINOv3, DINOv2, plugin).
- **2026-10-04 (13)** — **Sessione chiusa.** Stato consolidato nella nuova §0
  ("Come riprendere"). In questa sessione: Fase 0 portata a completamento
  sostanziale — packaging wheel (con GUI e comfy_bridge), runtime pinnato
  (D5), provisioning completo di vs-cmnet2 (plugin + pesi DINOv3/DINOv2, D7),
  NVEncC pubblicato e integrato, GUI come front-end di default (D6) con
  launcher, generatore `release.json`, release di prova `v0.1.0-alpha`,
  installazione di test completa e verificata in `D:\HAVCServerDiT_Test`.
  Prossimo: test del flusso di update, poi Fase 1 (manager C#).
- **2026-10-04 (14)** — **Update incrementale verificato (Fase 0 chiusa);
  fix convergenza `gui`/`launchers`.** Test a due versioni sul test install:
  da havc `0.1.0` a una nuova `0.1.1` (staging locale `dist/staging-v0.1.1`,
  manifest rigenerato e verificato). Il test ha esposto un gap di convergenza:
  i passi `gui` e `launchers` facevano skip "su presenza" — le modifiche a
  quei file in una nuova versione non sarebbero mai arrivate all'installazione
  (dimostrato: contenuto divergente lasciato lì dal rerun 0.1.0). Fix in
  `havc/install.py`: confronto di contenuto (aggiorna solo se diverso;
  idempotente). Flusso verificato: smoke tutto-skip → wheel 0.1.1 nel runtime
  → run9 (eseguiti solo `wheel`, `gui` a 9 file, `launchers`; `verify` verde)
  → run10 idempotente tutto-skip; `havc doctor` 9/9 verdi; havc 0.1.1 in venv
  e runtime; hash del file GUI installato == sorgente; demo repair (config
  rimossa → ricopiata). Log: `install-run8/9/10.log` in `D:\HAVCServerDiT_Test`.
  Resta solo il run facoltativo su VM pulita; prossimo: Fase 1 (manager C#).
- **2026-10-04 (15)** — **Decisioni di Fase 1 prese; §7 chiusa (D8–D11).**
  D8: Inno Setup scartato del tutto (SmartScreen neutro rispetto al
  packaging: conta firma+reputazione, dal 2024 nemmeno EV bypassa).
  D9: UI **C# WPF**. D10: wizard = default *Server+GUI* (Fase 1 solo questa
  modalità + update/ripara); pesi **DINOv2 inclusi** nell'installazione
  standard; cartella modelli **unica** (cache HF + comfy), pre-compilata
  "intelligente" (unità con più spazio, avviso sotto soglia) e modificabile
  durante l'installazione, riusata negli update, mai cancellata in
  disinstallazione. D11: nunchaku resta **pin + patch**, con **mirror della
  wheel ufficiale intatta** nel nostro repo (schema `runtime-312`; sha256 dal
  digest GitHub `20d8c4cef6664c2dd6f2d44155e6dd2d4d36163439f70da31ef945af3c8c6149`,
  111.735.072 byte); vendorizzata rinviata con criterio; pubblicazione del
  mirror = passo separato, su ok. Prossimo deliverable: **spec del manager C#**.
- **2026-10-04 (16)** — **Convenzione lingua: codice e commenti in inglese.**
  Su richiesta dell'autore: convertiti commenti e docstring del codice nuovo
  (`havc/*.py`, `installer/make_release.py`, `setup.py`, `pyproject.toml`,
  `requirements/*.txt`, `$comment` di `release.example.json`); regola
  registrata in §9. Le stringhe visibili all'utente restano in italiano.
- **2026-10-04 (17)** — **Mirror nunchaku pubblicato.** Release
  `nunchaku-1.2.1` con l'asset ufficiale invariato (111.735.072 byte; sha256
  confermato dal `digest` GitHub e con download end-to-end dal mirror);
  `requirements/nunchaku.txt` punta al mirror. Committate le modifiche
  pendenti (decisioni D8–D11, conversione lingua, mirror nunchaku).
- **2026-10-04 (18)** — **Spec del manager C# scritta**
  (`installer/PHASE1_SPEC.md`): architettura Core/App, flussi install/update/
  ripara/disinstalla, `install.json` schema v1, contratto col bootstrap
  (`--json-progress`, nuove opzioni `--models-dir` e `--with-dinov2` sempre),
  cartella modelli (D10), distribuzione (D1/D8). Prossimo: avvio sviluppo
  (M1 — skeleton WPF + Core).
- **2026-10-04 (19)** — **Stringhe utente in inglese (decisione).** UI del
  manager e messaggi visibili del nuovo stack (bootstrap, doctor, progress,
  make_release): convertite in questo giro le stringhe di `havc/*.py` e
  `installer/make_release.py` (script di conversione con asserzioni in
  `dist/`); spec Fase 1 aggiornata (§2).
- **2026-10-04 (20)** — **Sessione 2 chiusa.** §0 riscritta come handoff
  operativo (stato, prossimo passo M1 + decisione SDK .NET, comandi pronti,
  mappa del codice nuovo, policy push). Nella sessione: update test (log 14),
  decisioni Fase 1 (D8–D11), spec `installer/PHASE1_SPEC.md`, mirror
  `nunchaku-1.2.1`, conversione inglese (commenti, stringhe, spec).
- **2026-10-05 (21)** — **Decisione SDK chiusa: .NET 10 (10.0.401).** SDK
  installato machine-wide (installer ufficiale standalone; il tentativo winget
  falliva sul bootstrapper burn con `0x800700A1` "Failed to find local
  per-machine appdata directory"). Verificato che il VS Installer della linea
  VS 2022 17.14 non offre componenti .NET 10 (max 9.0, dal manifest ufficiale).
  Smoke WPF `net10.0-windows` **verde via CLI** (`dotnet new`/build, exe
  prodotto); **MSBuild di VS 2022 rifiuta net10** (risolve SDK 9.0.318 →
  NETSDK1045): l'SDK 10.0.4xx richiede MSBuild ≥ 18.0
  (`minimumMSBuildVersion`), cioè la linea VS 2026 (tabella ufficiale: SDK
  10.0.4xx ↔ VS 18.9, minimo VS 18.0). Sviluppo via CLI; VS 2026 per l'IDE
  valutabile a parte. Prossimo: M1 (skeleton manager).
- **2026-10-05 (22)** — **VS 2026 installato (Community, workload .NET
  desktop).** vswhere: istanza v18.10.12224.181 in
  `C:\Program Files\Microsoft Visual Studio\18\Community` (complete, no
  reboot); MSBuild 18.10.1 compila lo smoke WPF `net10.0-windows` (con VS 2022
  falliva: NETSDK1045). Toolchain completa: `dotnet` CLI 10.0.401 + VS 2026.
  Prossimo: M1 (skeleton manager).
- **2026-10-05 (23)** — **M1 completata: skeleton del manager.** Creato
  `manager/` (`HavcManager.sln` classico — l'SDK 10 ormai defaulta `.slnx`,
  tenuto il formato da spec): `HavcManager.Core` (net10.0) con `ManifestClient`
  funzionante (fetch/parse del manifest) e stub documentati per `Downloader`,
  `BootstrapRunner` (eventi `--json-progress`), `StateStore`/`InstallState`
  (schema v1), `Preflight`, `UpdateEngine`, `ProcessGuard`, `ManagerLog`;
  `HavcManager.App` (WPF, net10.0-windows) con pagina *Start installation*
  minima e stringhe in `Resources/Strings.resx`
  (`PublicResXFileCodeGenerator`: `x:Static` risolve a runtime → servono
  membri pubblici, trovato allo smoke). `Directory.Build.props` (manager
  0.1.0), `global.json` (SDK 10.0.401); `.gitignore`/`.gitattributes`
  aggiornati (bin/obj, LF per i sorgenti .NET). Verifiche: build verde con
  `dotnet` CLI e MSBuild VS 2026; smoke di avvio GUI ok. Prossimo: M2 (prima
  installazione end-to-end).
- **2026-10-05 (24)** — **M2 completata: prima installazione end-to-end.**
  Bootstrap (Python): nuovo `--models-dir` (wiring §7 — `hf_cache`/`cache_dir`
  solo se vuoti, `HAVC_MODELS_DIR` nei launcher; mai sovrascritto un valore
  esistente), cancel cooperativo (`.stop-request`, stop a fine passo), fix
  `paths.configs_dir()` dal checkout (cercava `configs/` invece di `config/`)
  e guardia venv in `vscmnet2_dir` (`--plan` su cartella vuota). Manager: Core
  implementato (Downloader sha256+cache, StateStore, Preflight,
  BootstrapRunner con eventi+jsonl, `PythonRuntime` per il tar.gz,
  `DownloadPlan`, `InstallFlow` a due stadi); progetto test xUnit (19 unit +
  2 integrazione gated); **wizard WPF completo** (Welcome→Preflight→Folders→
  Components→Summary→Progress→Finish + pagina Installed con disinstallazione
  e auto-rimozione, scorciatoie Start Menu, registrazione HKCU; opzioni
  `--manifest/--release-tag/--install-dir/--uninstall`). Verifiche: build 0
  warning (CLI + VS 2026); unit 19/19; integrazione 2/2 (runtime reale
  estratto + pip + `--plan` in scratch con la wheel nuova; download reale con
  sha256); smoke del wizard ok. Prossimo: M3 (update/ripara).
- **2026-10-05 (25)** — **Prep test/e2e: havc 0.1.2 + staging.** Bump
  versione a **0.1.2** (wheel con `--models-dir`/cancel: la 0.1.1 "vecchia" e
  la nuova sarebbero state indistinguibili — `wheel_check` confronta la
  versione). Creata `dist/staging-v0.1.2` (wheel + asset + `release.json`
  generato e verificato) pronta da pubblicare come release **`v0.1.2`**;
  creato `dist/test-manifest-local.json` (wheel/asset in `file://`, runtime
  dal mirror) per provare il wizard end-to-end senza pubblicare.
- **2026-10-05 (26)** — **Fix: crash del manager alla pagina Progress
  (segnalato dall'utente al primo run reale).** `ProgressBar.Value/Maximum`
  sono TwoWay di default e il VM espone proprietà read-only →
  `InvalidOperationException` appena aperta la pagina Progress (`Mode=OneWay`
  su entrambe). Aggiunto anche un handler `DispatcherUnhandledException` che
  mostra l'eccezione invece di far sparire l'app in silenzio. Verifica nuova:
  **test UI automatizzato** (PowerShell + UI Automation) che pilota il wizard
  reale (scratch + manifest locale): Start→Preflight→Folders→Components→
  Summary→Install→Progress; a 45 s download completati (runtime 22 MB +
  wheel + asset) e runtime estratto; `Cancel` → `.stop-request` scritto;
  `Force stop` → processo vivo; Event Log pulito dopo il fix. Resta: run
  completo col bootstrap pesante (utente/VM) e pagine Finish/Installed da
  esercitare davvero.
- **2026-10-05 (27)** — **Icona dell'app.** Il manager usa
  `installer/Icona-havc-dit.ico` (già versionata, multi-size 16–256):
  `<ApplicationIcon>` sull'exe + risorsa WPF per `Window.Icon` (finestra
  principale e dialog di disinstallazione); le scorciatoie Start Menu/desktop
  puntano all'exe del manager come sorgente icona (`IconLocation`), così anche
  "HAVC" (target `.vbs`) mostra l'icona. La voce di disinstallazione
  (`DisplayIcon`) già puntava a `HAVCManager.exe`. Verifiche: build 0 warning;
  frame dell'ico trovati dentro l'exe (256×256 e 32×32); smoke finestra ok.
- **2026-10-05 (28)** — **Prima installazione reale riuscita + fix progressbar.**
  Run completo dell'utente su `D:\HAVC_Manager_Test`: 21/21 passi (18 ok, 3
  skip), `verify: doctor: all checks OK`, install.json + scorciatoie + registro
  + manager copiato (`bootstrap-20261005-153453.jsonl`, ~5m20s). Bug trovato:
  **la progressbar restava a 0** — il bootstrap emette l'evento `plan` solo in
  modalità `--plan`, quindi nei run reali il manager non riceveva mai la lista
  dei 21 passi. Fix: `plan` emesso **a inizio di ogni run** (PHASE0_SPEC §5
  aggiornata) + robustezza nel VM (righe create se manca il piano). Bump
  **0.1.3** (wheel col fix; staging `v0.1.3` rigenerata in `dist/`, `v0.1.2`
  locale rimossa perché superata; manifest locale di test aggiornato).
  Verifiche: convergenza sull'install reale (tutto-skip, plan in prima riga,
  exit 0); test UI automatizzato: **barra letta via UIA = 2/21 e in
  avanzamento**, cancel cooperativo ok, nessun crash. Nota: l'install di test
  è stato aggiornato a 0.1.3 (runtime+venv) via bootstrap; `install.json`
  riporterà 0.1.3 al prossimo run del manager (M3).
- **2026-10-05 (29)** — **M3 completata: update con rollback, ripara, lock.**
  Core: `ProcessGuard` (processi sotto l'install), `UpdateEngine` (classifica
  up-to-date/update/rebuild + wheel in cache), campo additivo `dirty` nello
  stato, `InstallFlow.RunRepairAsync` (stadio 1+2 sul wheel in cache, zero
  download). UI: pagina Installed completa (stato, ultima verifica, spazio,
  scelta modello, Check for updates, Repair, About), dialoghi inglesi dedicati
  (`MessageDialog`, `ProcessLockWindow`), lock istanze prima dei run. Verifiche
  sul campo (test install): **update reale 0.1.2→0.1.3 riuscito** (previous
  salvato); **ripara** riuscito; **rollback reale** (update 0.1.9 con wheel
  corrotta → "previous version was restored", stato intatto); **lock**
  (sleeper → dialog → Terminate now → repair ok). 24 test verdi. Fix: `Icon`
  dei dialoghi in sottocartella → URI root-relative; log di check
  aggiornamenti nel manager log. Prossimo: M4 + release/VM.
- **2026-10-05 (30)** — **Modello di default qwen21-viggle; via la scelta
  modello dal manager.** Manager: rimossa la combo *Model* dalla pagina
  Installed (`Backends`/`SelectedBackend` via dalla VM; stringa `ModelLabel`
  ritirata); *Start server* usa `backend_default` con fallback `"qwen21"`;
  `FinalizeInstall` scrive `qwen21`; preflight: via il "suggerimento
  backend", nuovo check **VRAM (default model)** (`memory.total` da
  nvidia-smi; warning non bloccante sotto 12 GiB). Bootstrap: seed/wiring
  `model_name = qwen21-viggle` nei settings GUI (costante
  `DEFAULT_MODEL_NAME`; solo se assente, come `hf_cache`); step rinominato
  "GUI settings (seeded/wired when missing)". Bump havc **0.1.4** (wheel +
  staging `v0.1.4` + `test-manifest-local.json`); `staging-v0.1.3` rimossa
  (superata). Spec: PHASE1 §4/§5/§6.2/§7/§8, PHASE0 punto 19. Verifiche:
  build 0 warning; unit 24/24; bootstrap sul test install **21 passi (17
  skip)** → `wheel`+`gui-settings`+`verify` ok, doctor 9/9 con havc 0.1.4;
  rerun `--only gui-settings` → skip e file identico (hash); UI (UIA):
  Installed senza combo e con *Start server*; Preflight con riga VRAM
  ("15.9 GB … ≥ 12.0 GB del modello di default") e nessun "Suggested
  backend". Sul test install: settings GUI con `model_name`, `install.json`
  allineato (backend `qwen21`, app/last_verify 0.1.4, wheel 0.1.4 in
  `cache/`).
- **2026-10-05 (31)** — **Fix: l'exe copiato in `<install>` non partiva
  (build multi-file).** Trovato per strada verificando la pagina Installed:
  `CopyManagerTo` copiava solo l'exe framework-dependent → host error
  `0x8000809A` all'avvio (mancano `HavcManager.App.dll` e i file host).
  Ora `ShellIntegration.CopyApplicationFiles` copia accanto all'apphost
  l'exe + `HavcManager.App.dll` + `HavcManager.Core.dll` + `*.deps.json`/
  `*.runtimeconfig.json` (no-op su single-file publish: `Assembly.Location`
  vuoto); usata da `CopyManagerTo` e dalla copia temp dell'uninstall (ora in
  cartella dedicata `%TEMP%\HAVCManager-uninstall-*`, rimossa interamente
  dal worker). Verifiche: build 0 warning; unit 24/24; deploy reale della
  funzione sulla cartella di test → l'exe installato parte (finestra "HAVC
  Setup", Installed senza combo, Start server; versione 0.1.4). Da provare
  al primo disinstallo reale: il percorso uninstall end-to-end.
- **2026-10-05 (32)** — **Requisito RAM del modello di default (32 GB).**
  Correzione dell'autore: qwen21-viggle richiede ≥ 12 GB VRAM **e ≥ 32 GB
  RAM** (non 32 GB VRAM). Preflight: nuova riga **System memory (default
  model)** (RAM fisica via `GlobalMemoryStatusEx`; sotto 32 GiB: warning non
  bloccante con suggerimento di un modello più leggero, longcat-gguf Q3 —
  indicato dall'autore: con 16 GB di RAM è l'unico che gira). Spec §6.2/§8
  aggiornate (VRAM + RAM). Verifiche: build 0 warning; unit 24/24; UI (UIA):
  riga presente con "111.8 GB … ≥ 32.0 GB"; copia installata del manager
  riaggiornata.
- **2026-10-05 (33)** — **Dimensioni dei pesi per config (check richiesto
  dall'autore).** Totali dei file caricati (misurati su disco in
  `_dev\comfy_bridge\models`, cache HF, HF API per i quant non scaricati):
  qwen21-viggle **≈ 13.9 GB** (unet 6.9 + clip 4.9 + mmproj 1.1 + vae 0.6 +
  lora 0.6); longcat-gguf q3→q8 **8.8 / 9.4 / 10.1 / 10.6 / 12.0 GB**
  (clip Qwen2.5-VL Q4_K_M 4.4 GB fisso + mmproj 1.3 + lct_vae 0.2);
  qwen-gguf q3→q8 **14.0 / 17.9 / 21.3 / 23.8 / 30.1 GB**; nunchaku-qwen fp4
  r32 **≈ 26.8 GB** (svdq 11.1 + text encoder bf16 15.4 + vae 0.2). Conferma
  D12: qwen21 (13.9 GB) non entra in 16 GB di RAM → soglia 32 GB; longcat q3
  (8.8 GB) è l'unico che gira con 16 GB.
- **2026-10-05 (34)** — **RAM < 32 GB → default longcat-gguf Q3.** Manager:
  `PreflightReport.DefaultModelName` con `DecideDefaultModel` (< 32 GiB →
  longcat-gguf; ≥ o RAM ignota → qwen21-viggle; +3 unit test → 27/27); riga
  "System memory" sotto soglia → "the installer will use longcat-gguf (Q3)
  as the default model instead"; `--default-model` passato a
  install/update/ripara; `backend_default` = `longcat3` se longcat (nuovo
  arg launcher `longcat3` → `longcat_gguf_q3.json`). Bootstrap: opzione
  `--default-model` (seed/wiring `model_name` + `model_precision` q3 per
  longcat, solo se assenti). havc **0.1.5** (wheel + staging `v0.1.5` +
  `test-manifest-local.json`; `staging-v0.1.4` rimossa). Spec PHASE1
  §4/§5/§6.2/§8, PHASE0 §5/step 19. Verifiche: build 0 warning; unit 27/27;
  bootstrap su scratch (wiring longcat+q3, qwen21 senza precision, template
  nuovo file, launcher con `longcat3`; rerun → skip); run reale sul test
  install → wheel 0.1.5, launchers riscritti, doctor 9/9; UI (UIA): Installed
  0.1.5 senza combo, preflight con riga RAM OK (111.8 GB; il ramo longcat è
  coperto dai unit test).
- **2026-10-05 (35)** — **Disinstallo reale riuscito (test dell'autore) +
  nota manifest.** Il test di uninstall dell'autore ha cancellato tutto
  correttamente (cartella install, registro HKCU, scorciatoie, temp-copy —
  nessun residuo in `%TEMP%`): **conferma sul campo del fix (31)** (copia
  completa dell'app + rmdir della cartella temp). `D:\HAVCModels` è stata
  rimossa con la spunta *Also delete the models folder* (gate corretto in
  codice: `deleteModels && modelsDir`; era comunque vuota). Nota per i test:
  **il manifest di default del manager
  (`/releases/latest/download/release.json`) dà 404** finché non si pubblica
  una release con `release.json` (latest attuale = `v1.0.0`, senza asset
  manifest) → per i run locali passare
  `--manifest dist\test-manifest-local.json`; la pubblicazione di `v0.1.5`
  sblocca anche il default. L'install di test è quindi **da reinstallare**.
