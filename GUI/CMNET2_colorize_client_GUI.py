"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2024-12-26
LastEditTime: 2026-01-14
-------------------------------------------------------------------------------
GUI Client per la colorizzazione batch via RPC.

La pipeline AI gira sul server (CMNET2_colorize_server.py).
Questo client si connette via XML-RPC e invia le richieste di colorizzazione.

Avvio:
    python CMNET2_colorize_client_GUI.py

Il server deve essere già avviato sulla macchina GPU prima di cliccare Connect.
-------------------------------------------------------------------------------
"""

import FreeSimpleGUI as sg
import subprocess
import threading
import os
import re
import json
import signal
import sys
import io
import time
import shutil
import xmlrpc.client
from pathlib import Path
from send2trash import send2trash
from PIL import Image

# ---------------------------------------------------------------------------
# Ensure local module is found
# ---------------------------------------------------------------------------
script_dir = Path(__file__).parent.resolve()
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# ---------------------------------------------------------------------------
# RPC Client wrapper
# Centralizza tutta la comunicazione con il server in un unico oggetto.
# ---------------------------------------------------------------------------

class _TimeoutTransport(xmlrpc.client.Transport):
    """
    Transport xmlrpc con timeout configurabile.
    Il Transport standard non espone il timeout: bisogna sottoclassarlo
    e impostarlo direttamente su HTTPConnection dentro make_connection().
    """
    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class CMNET2RpcClient:
    """
    Wrapper attorno a xmlrpc.client.ServerProxy.

    Due timeout distinti:
    - CONNECT_TIMEOUT (5s): usato da ping(), fallisce subito se il server
      non è raggiungibile invece di bloccare la GUI.
    - CALL_TIMEOUT (600s): usato per le chiamate di colorizzazione che
      possono impiegare molti secondi per immagine.
    """

    _CONNECT_TIMEOUT = 5    # secondi — per ping() / is_pipeline_loaded()
    _CALL_TIMEOUT    = 600  # secondi — per colorize_*() / load_pipeline()

    def __init__(self, host: str, port: int):
        uri = f"http://{host}:{port}"
        self._proxy_fast = xmlrpc.client.ServerProxy(
            uri,
            transport=_TimeoutTransport(self._CONNECT_TIMEOUT),
            allow_none=True,
        )
        self._proxy_slow = xmlrpc.client.ServerProxy(
            uri,
            transport=_TimeoutTransport(self._CALL_TIMEOUT),
            allow_none=True,
        )

    def ping(self) -> tuple[bool, str]:
        """
        Ritorna (True, "") se il server risponde entro 5 secondi.
        Ritorna (False, messaggio_errore) altrimenti.
        """
        try:
            ok = self._proxy_fast.ping() == "pong"
            return (ok, "" if ok else "Risposta inattesa dal server")
        except ConnectionRefusedError:
            return (False, "Connection refused — il server non è in ascolto")
        except TimeoutError:
            return (False, "Timeout — server non raggiungibile")
        except OSError as e:
            return (False, f"Errore di rete: {e}")
        except Exception as e:
            return (False, str(e))

    def load_pipeline(self, model_name, model_precision, model_rank,
                      model_inference_steps, cache_dir,
                      full_model_path="") -> dict:
        return self._proxy_slow.load_pipeline(
            model_name, model_precision, model_rank,
            model_inference_steps, cache_dir, full_model_path,
        )

    def is_pipeline_loaded(self) -> bool:
        return bool(self._proxy_fast.is_pipeline_loaded())

    def request_stop(self) -> bool:
        return bool(self._proxy_fast.request_stop())

    def clear_stop(self) -> bool:
        return bool(self._proxy_fast.clear_stop())

    def colorize_image(self, in_path, out_path, prompt,
                       img_size=0, steps=2) -> dict:
        return self._proxy_slow.colorize_image(
            str(in_path), str(out_path), prompt, img_size, steps)

    def colorize_image_pair(self, img1_path, img2_path,
                            out_dir, prompt, gap_px=8, steps=4) -> dict:
        return self._proxy_slow.colorize_image_pair(
            str(img1_path), str(img2_path), str(out_dir), prompt, gap_px, steps)

    def colorize_single_image(self, img_path, out_dir, prompt, steps=4) -> dict:
        return self._proxy_slow.colorize_single_image(
            str(img_path), str(out_dir), prompt, steps)


# ---------------------------------------------------------------------------
# CONFIGURATION MANAGEMENT
# ---------------------------------------------------------------------------
CONFIG_FILE = "gui_cmnet2_settings.json"


def load_all_configs():
    defaults = {
        # --- paths ---
        "vspipe_path":      r"",
        "x265_path":        r"",
        "script_dir":       r"",
        "extract_script":   "extract_refs_edge.vpy",
        "encode_script":    "encode_cmnet2.vpy",
        "base_dir":         r"",
        # --- model ---
        "model_name":             "nunchaku-qwen",
        "model_precision":        "fp4",
        "model_rank":             "32",
        "model_inference_steps":  "4",
        "steps":                  "2",
        "fast_pipe":              True,
        # --- encode ---
        "mkv_path":       r"",
        "hf_cache":       "",
        "prompt":         "Colorize this image, natural colors. Strictly preserve all shapes, edges and background details.",
        "shutdown_on_complete": False,
        "dupe_first_frame":     False,
        "do_step1":       False,
        "do_step2":       False,
        "do_step3":       True,
        "do_step4":       False,
        "sc_threshold":   "0.04",
        "sc_tht_ssim":    "0.0",
        "sc_min_int":     "15",
        "sc_mult_tht":    "10",
        "ref_override":   False,
        "frames_memory":  "20",
        "render_speed":   "auto",
        "crf":            "20.0",
        "merge_weight":   "0.40",
        "vbr_quality":    "27.00",
        "encoder":        "x265",
        "use_sharp":      True,
        # --- RPC ---
        "rpc_host":  "127.0.0.1",
        "rpc_port":  8765,
        # --- window ---
        "window_w": 820,
        "window_h": 640,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return {**defaults, **json.load(f)}
        except Exception:
            return defaults
    return defaults


def save_all_configs(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)


# ---------------------------------------------------------------------------
# UTILS
# ---------------------------------------------------------------------------
def scan_videos(directory):
    extensions = ('.mkv', '.mp4', '.avi', '.mov')
    if directory and os.path.isdir(directory):
        return [f for f in os.listdir(directory)
                if f.lower().endswith(extensions)]
    return []


def pil_to_png_data(pil_image, max_size=(370, 350)):
    if pil_image is None:
        return b''
    pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)
    with io.BytesIO() as output:
        pil_image.save(output, format="PNG")
        return output.getvalue()


def scan_files(directory, pattern):
    if not directory or not os.path.isdir(directory):
        return []
    try:
        files = os.listdir(directory)
        if pattern.startswith("*."):
            ext = pattern.replace("*", "").lower()
            return sorted([f for f in files if f.lower().endswith(ext)])
        else:
            regex = pattern.replace(".", r"\.").replace("*", ".*")
            return sorted([f for f in files
                           if re.match(regex, f, re.IGNORECASE)])
    except Exception:
        return []


def get_eta_string(current_step, total_steps, start_time):
    if current_step <= 4:
        return "Calculating..."
    elapsed_time = time.time() - start_time
    time_per_step = elapsed_time / current_step
    remaining_steps = total_steps - current_step
    eta_seconds = int(time_per_step * remaining_steps)
    if eta_seconds < 60:
        return f"{eta_seconds}s"
    elif eta_seconds < 3600:
        return f"{eta_seconds // 60}m {eta_seconds % 60}s"
    else:
        h = eta_seconds // 3600
        m = (eta_seconds % 3600) // 60
        s = eta_seconds % 60
        return f"{h}h {m}m {s}s"


def create_video_mkv(mkv_exe, video_h265_path, fps: str, log_fn=print):
    if video_h265_path == "":
        return None
    h265_path = Path(video_h265_path)
    output_file = h265_path.with_suffix(".mkv")
    if not os.path.isfile(video_h265_path):
        return None
    try:
        cmd = (f'"{mkv_exe}" -o "{output_file}" '
               f'--default-duration 0:{fps}fps "{h265_path}" ')
        log_fn("----------------------------------------------------------------")
        log_fn(f"[MKV] {cmd.strip()}")
        log_fn("----------------------------------------------------------------")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        log_fn(result.stderr + result.stdout)
        if output_file.exists() and output_file.stat().st_size > 0:
            send2trash(str(h265_path))
    except Exception as e:
        log_fn(f"⚠️ Error creating mkv video: {e}")
        return None


def get_video_info(vspipe_exe, video_path, script_dir_path, log_fn=print):
    info_vpy = os.path.join(script_dir_path, "vs_info.vpy")
    if not os.path.isfile(info_vpy):
        return None
    try:
        cmd = [vspipe_exe, "--info", info_vpy,
               "-a", f"VideoPath={video_path}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            log_fn(f"⚠️ Error getting video info: {result}")
            return None
        info = {}
        full_output = result.stderr + result.stdout
        for line in full_output.splitlines():
            l = line.strip().lower()
            if "fps:" in l:
                info["fps"] = l.split(":", 1)[1].strip().split(" ", 1)[0].strip()
            if "frames:" in l:
                info["frames"] = int(l.split(":", 1)[1].strip())
            if "width:" in l:
                info["width"] = l.split(":", 1)[1].strip()
            if "height:" in l:
                info["height"] = l.split(":", 1)[1].strip()
            if "format name:" in l:
                info["format"] = l.split(":", 1)[1].strip()
        return info
    except Exception as e:
        log_fn(f"⚠️ Error getting video info: {e}")
        return None


def update_video_info(window, info):
    window["-INF_RES-"].update(
        f"{info.get('width', '?')} x {info.get('height', '?')}")
    window["-INF_FPS-"].update(info.get('fps', '?'))
    window["-INF_FRAMES-"].update(info.get('frames', '?'))
    window["-INF_FORMAT-"].update(info.get('format', '?'))
    window["-FPS-"].update(info.get('fps', '24000/1001'))


# ---------------------------------------------------------------------------
# GLOBAL STATE
# ---------------------------------------------------------------------------
state = {
    "current_process": None,
    "stop_requested":  False,
    "rpc_client":      None,    # CMNET2RpcClient | None
    "rpc_connected":   False,
    "is_running":      False,
    "total_frames":    -1,
}


def log_gui_only(msg):
    window.write_event_value("-LOG-", msg)


def update_status(window, message, type="info"):
    colors = {
        "info":    "black",
        "error":   "red",
        "success": "#005500",
    }
    window["-STATUS-"].update(message, text_color=colors.get(type, "black"))


# ---------------------------------------------------------------------------
# RPC CONNECTION HELPER
# ---------------------------------------------------------------------------
_RPC_MAX_RETRIES = 5   # tentativi prima di arrendersi
_RPC_RETRY_DELAY = 2   # secondi tra un tentativo e il successivo


def _connect_thread(host: str, port: int, window):
    """
    Gira in un thread daemon: non blocca la GUI durante i retry.
    Comunica con il main thread solo via write_event_value.
    """
    def log(msg):
        window.write_event_value("-LOG-", msg)

    log(f"[RPC] Connessione a {host}:{port} (max {_RPC_MAX_RETRIES} tentativi)...")

    try:
        client = CMNET2RpcClient(host, int(port))
        err_msg = ""
        for attempt in range(1, _RPC_MAX_RETRIES + 1):
            ok, err_msg = client.ping()
            if ok:
                state["rpc_client"] = client
                state["rpc_connected"] = True
                log(f"[RPC] ✅ Connesso a {host}:{port}")
                window.write_event_value("-RPC_CONNECT_DONE-", (True, ""))
                return
            log(f"[RPC] Tentativo {attempt}/{_RPC_MAX_RETRIES} fallito: {err_msg}")
            if attempt < _RPC_MAX_RETRIES:
                time.sleep(_RPC_RETRY_DELAY)

        # Tutti i tentativi esauriti
        state["rpc_client"] = None
        state["rpc_connected"] = False
        log(f"[RPC] ❌ Connessione fallita dopo {_RPC_MAX_RETRIES} tentativi.")
        window.write_event_value("-RPC_CONNECT_DONE-", (False, err_msg))

    except Exception as e:
        state["rpc_client"] = None
        state["rpc_connected"] = False
        log(f"[RPC] ❌ Errore imprevisto: {e}")
        window.write_event_value("-RPC_CONNECT_DONE-", (False, str(e)))


# ---------------------------------------------------------------------------
# TASK LOGIC — subprocess (EXTRACT, ENCODE, MERGE) — invariati rispetto
# alla versione originale, girano localmente nel client.
# ---------------------------------------------------------------------------

def run_vspipe_task(cmd, window, task_name, log_fn):
    """Gestisce subprocess per lo Step 1 (EXTRACT)."""
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        text=True, bufsize=1, universal_newlines=True, shell=True,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                       if os.name == 'nt' else 0),
    )
    state["current_process"] = proc
    start_time = time.time()
    progress_re = re.compile(r"Frame:\s+(\d+)/(\d+)")
    curr = total = 0
    for line in proc.stderr:
        if state["stop_requested"]:
            break
        if "Output" in line:
            log_fn(f"[{task_name}] {line.strip()}", gui_only=False)
        else:
            log_fn(f"[{task_name}] {line.strip()}", gui_only=True)
        match = progress_re.search(line)
        if match:
            curr, total = int(match.group(1)), int(match.group(2))
            eta = get_eta_string(curr, total, start_time)
            update_status(
                window,
                f"Status: ETA EXTRACT: {eta}...", "info")
            p = int((curr / total) * 100)
            window.write_event_value("-PROGRESS-", (p, f"{p}% {curr}/{total}"))
    proc.wait()
    window.write_event_value("-PROGRESS-", (100, f"100% {total}/{total}"))
    update_status(window, "Status: OK", "info")
    return proc.returncode


# ---------------------------------------------------------------------------
# ORCHESTRATOR — gira in un thread separato (daemon)
# ---------------------------------------------------------------------------
def orchestrator(init_values, window):
    state["is_running"] = True
    state["stop_requested"] = False

    # --- Log file ---
    log_file = None
    video_name = init_values["-VIDEO_DROPDOWN-"]
    if video_name:
        video_base_path = os.path.splitext(video_name)[0]
        if "cmnet2" in str(video_base_path):
            log_path = Path(init_values["-BASE_DIR-"]) / f"{video_base_path}_dt-color_log.txt"
        else:
            log_path = Path(init_values["-BASE_DIR-"]) / f"{video_base_path}_cmnet2_dt-color_log.txt"
        log_file = open(log_path, "a", encoding="utf-8")
        print(f"\n--- SESSION STARTED: {time.strftime('%Y-%m-%d %H:%M:%S')} ---",
              file=log_file, flush=True)

    def log_message(msg, gui_only: bool = False):
        window.write_event_value("-LOG-", msg)
        if log_file and not gui_only:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}",
                  file=log_file, flush=True)

    # ---- subprocess helper (ENCODE) ----
    def run_command(full_cmd, total_frames, task_name):
        log_message("----------------------------------------------------------------")
        log_message(f"[{task_name}] {full_cmd.strip()}")
        log_message("----------------------------------------------------------------")
        proc = subprocess.Popen(
            full_cmd, shell=True,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            universal_newlines=True,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                           if os.name == 'nt' else 0),
        )
        state["current_process"] = proc
        frame_re = re.compile(r"(?:Frame:\s+|(\d+)\s+frames?:)")
        start_time = time.time()
        curr_frame = 0
        for line in proc.stderr:
            if state["stop_requested"]:
                break
            match = frame_re.search(line.strip())
            if match and total_frames > 0:
                try:
                    curr_frame = (int(match.group(1)) if match.group(1)
                                  else int(line.split('/')[-2].split()[-1]))
                except (ValueError, IndexError):
                    pass
                p = min(100, int((curr_frame / total_frames) * 100))
                eta = get_eta_string(curr_frame, total_frames, start_time)
                update_status(window, f"Status: ETA ENCODE: {eta}...", "info")
                log_gui_only(f"[ENCODE] {line.strip()}")
                window.write_event_value(
                    "-PROGRESS-", (p, f"{p}% {curr_frame}/{total_frames}"))
            else:
                if "----------------------" not in line:
                    log_message(f"[{task_name}] {line.strip()}")
        proc.wait()
        window.write_event_value(
            "-PROGRESS-", (100, f"100% {total_frames}/{total_frames}"))
        update_status(window, "Status: OK", "info")
        return proc.returncode

    # ---- STEP 1: EXTRACTION ----
    def do_extraction(values, window, orig_video_path):
        ref_dir = os.path.join(values["-BASE_DIR-"], "ref_tht10")
        extract_vpy = os.path.join(values["-SCRIPT_DIR-"], values["-EXTRACT_VPY-"])
        if not os.path.exists(ref_dir):
            os.makedirs(ref_dir)

        ScThreshold = values["-SC_THT-"]
        ScThtSSIM   = values["-SC_THT_SSIM-"]
        SCMinINT    = values["-SC_MIN_INT-"]
        ScMultTht   = values["-SC_MULT_THT-"]
        RefOverride = "True" if values["-REF_OVERRIDE-"] else ""
        vpy_args = (
            f'-a "ScThreshold={ScThreshold}" -a "ScThtSSIM={ScThtSSIM}" '
            f'-a "SCMinINT={SCMinINT}" -a "ScMultTht={ScMultTht}" '
            f'-a "RefOverride={RefOverride}"'
        )
        cmd = (f'"{values["-VSPIPE-"]}" "{extract_vpy}" . --progress '
               f'-a "VideoPath={orig_video_path}" '
               f'-a "RefDir={ref_dir}" {vpy_args}')
        log_message(f'ℹ️ Avvio estrazione con script: "{extract_vpy}"')
        ret = run_vspipe_task(cmd, window, "EXTRACT", log_message)

        info = get_video_info(
            values["-VSPIPE-"], orig_video_path, values["-SCRIPT_DIR-"], log_message)
        if info:
            out_dir = Path(ref_dir)
            total_frames = info["frames"]
            num_extract = len(list(out_dir.glob("*.jpg")))
            if num_extract > 0:
                log_message(
                    f"[EXTRACT] Esportate {num_extract} immagini di riferimento, "
                    f"circa 1 ogni {round(total_frames / num_extract)} frame")

        if ret == 0 and window["-DUPE_FIRST_FRAME-"].get():
            ref_dir_path = Path(ref_dir)
            ref_files = sorted(ref_dir_path.glob("ref_000*.jpg"))
            if len(ref_files) < 3:
                ref_files = sorted(ref_dir_path.glob("ref_00*.jpg"))
            if len(ref_files) >= 2:
                second_file = ref_files[1]
                target_file = ref_dir_path / "ref_000000.jpg"
                if target_file.exists():
                    send2trash(str(target_file))
                    log_message(f"ℹ️ {target_file.name} sovrascritto.")
                shutil.copy2(second_file, target_file)
                log_message(f"✅ Creato {target_file.name} da {second_file.name}")
            else:
                log_message("⚠️ Meno di 2 frame trovati — skip duplicazione.")

    # ---- STEP 2a: COLORIZE (standard, una immagine per volta) ----
    def do_colorize(values, window):
        rpc = state.get("rpc_client")
        if rpc is None:
            log_message("⚠️ Nessuna connessione al server RPC.")
            return

        # Carica pipeline se non già caricata
        if not rpc.is_pipeline_loaded():
            log_message(f'Caricamento pipeline AI sul server...')
            result = rpc.load_pipeline(
                values["-MODEL_NAME-"],
                values["-MODEL_PRECISION-"],
                values["-MODEL_RANK-"],
                values["-MODEL_INF_STEPS-"],
                values["-CACHE_DIR-"],
            )
            if not result.get("ok"):
                log_message(f"⚠️ Impossibile caricare pipeline: {result.get('msg')}")
                return
            log_message(f"✅ Pipeline caricata: {result.get('msg')}")

        rpc.clear_stop()

        in_dir  = Path(values["-BASE_DIR-"]) / "ref_tht10"
        out_dir = Path(values["-BASE_DIR-"]) / "ref_qwen"
        out_dir.mkdir(exist_ok=True)

        images = sorted([
            f for f in in_dir.iterdir()
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg')
        ])
        total_images = len(images)
        tot_time = 0.0
        count    = 0
        start_time = time.time()

        for i, img_path in enumerate(images):
            if state["stop_requested"]:
                rpc.request_stop()
                break
            if not window["-DO_STEP2-"].get():
                log_message("[COLORIZE] Task saltato dall'utente.")
                break

            curr_i = i + 1
            p = int((curr_i / total_images) * 100)
            window.write_event_value("-PROGRESS-", (p, f"{p}% {curr_i}/{total_images}"))
            eta = get_eta_string(curr_i, total_images, start_time)
            update_status(window, f"Status: ETA COLORIZE: {eta}...", "info")

            try:
                bw_img = Image.open(img_path).convert("RGB")
                window.write_event_value("-PREVIEW_BW-", bw_img)

                out_img_path = out_dir / (img_path.stem + ".jpg")
                prompt = values["-PROMPT-"]
                steps  = int(values.get("-STEPS-", cfg["steps"]))

                result = rpc.colorize_image(
                    str(img_path), str(out_img_path),
                    prompt, img_size=0, steps=steps,
                )
                if not result.get("ok"):
                    log_message(f"⚠️ {img_path.name}: {result.get('msg')}")
                    continue

                elapsed = result.get("elapsed", 0.0)
                skipped = result.get("skipped", False)

                if not skipped:
                    tot_time += elapsed
                    count += 1
                    color_img = Image.open(out_img_path).convert("RGB")
                    window.write_event_value("-PREVIEW_CLR-", color_img)
                else:
                    log_message(f"⚠️ {img_path.name}: saltata (troppo scura o già colorizzata)")

            except xmlrpc.client.Fault as e:
                log_message(f"RPC Fault su {img_path.name}: {e.faultString}")
            except Exception as e:
                log_message(f"Errore su {img_path.name}: {e}")

        window.write_event_value("-PROGRESS-",
                                 (100, f"100% {total_images}/{total_images}"))
        update_status(window, "Status: OK", "info")
        if count > 0:
            log_message(
                f"🎉 Done! {count} immagini in {tot_time:.2f}s "
                f"({tot_time / count:.2f}s/immagine)")

    # ---- STEP 2b: COLORIZE FAST (a coppie) ----
    def do_colorize_fast(values, window):
        rpc = state.get("rpc_client")
        if rpc is None:
            log_message("⚠️ Nessuna connessione al server RPC.")
            return

        # Carica pipeline se non già caricata
        if not rpc.is_pipeline_loaded():
            log_message("Caricamento pipeline AI sul server...")
            result = rpc.load_pipeline(
                values["-MODEL_NAME-"],
                values["-MODEL_PRECISION-"],
                values["-MODEL_RANK-"],
                values["-MODEL_INF_STEPS-"],
                values["-CACHE_DIR-"],
            )
            if not result.get("ok"):
                log_message(f"⚠️ Impossibile caricare pipeline: {result.get('msg')}")
                return
            log_message(f"✅ Pipeline caricata: {result.get('msg')}")

        rpc.clear_stop()

        in_dir  = Path(values["-BASE_DIR-"]) / "ref_tht10"
        out_dir = Path(values["-BASE_DIR-"]) / "ref_qwen"
        out_dir.mkdir(exist_ok=True)

        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
        out_stems  = {f.stem.lower() for f in out_dir.glob("*.jpg")}

        if out_stems:
            log_message(f"⚠️ {len(out_stems)} immagini già colorizzate — saranno saltate.")

        image_files = sorted([
            f for f in in_dir.iterdir()
            if f.suffix.lower() in extensions
            and f.stem.lower() not in out_stems
        ])
        tot_num_images = len(image_files)

        if tot_num_images == 0:
            log_message("ℹ️ Nessuna immagine da colorizzare.")
            return

        log_message(f"ℹ️ {tot_num_images} immagini da colorizzare.")

        # Raggruppa in coppie
        pairs = [image_files[i:i + 2] for i in range(0, tot_num_images, 2)]
        prompt     = values["-PROMPT-"]
        tot_time   = 0.0
        count      = 0
        n_images   = 0
        start_time = time.time()

        for pair in pairs:
            if state["stop_requested"]:
                rpc.request_stop()
                break
            if not window["-DO_STEP2-"].get():
                log_message("[COLORIZE] Task saltato dall'utente.")
                break

            n_images += len(pair)
            p = int((n_images / tot_num_images) * 100)
            window.write_event_value("-PROGRESS-", (p, f"{p}% {n_images}/{tot_num_images}"))
            eta = get_eta_string(n_images, tot_num_images, start_time)
            update_status(window, f"Status: ETA COLORIZE: {eta}...", "info")
            steps  = int(values.get("-STEPS-", cfg["steps"]))
            
            try:
                if len(pair) == 2:
                    result = rpc.colorize_image_pair(
                        str(pair[0]), str(pair[1]),
                        str(out_dir), prompt, gap_px=8, steps=steps
                    )
                    if not result.get("ok"):
                        log_message(f"⚠️ Coppia {pair[0].name}+{pair[1].name}: {result.get('msg')}")
                        continue
                    t = result.get("elapsed", 0.0)
                    if t > 0:
                        log_gui_only(
                            f"✅ Coppia: {pair[0].name}, {pair[1].name} "
                            f"[{t / 2:.2f}s/immagine]")
                    tot_time += t
                    count    += 2
                else:
                    result = rpc.colorize_single_image(
                        str(pair[0]), str(out_dir), prompt,
                    )
                    if not result.get("ok"):
                        log_message(f"⚠️ {pair[0].name}: {result.get('msg')}")
                        continue
                    t = result.get("elapsed", 0.0)
                    if t > 0:
                        log_message(
                            f"✅ Singola: {pair[0].name} [{t:.2f}s/immagine]")
                    tot_time += t
                    count    += 1

                # Anteprima
                bw_img = Image.open(pair[0]).convert("RGB")
                window.write_event_value("-PREVIEW_BW-", bw_img)
                elapsed = result.get("elapsed", 0.0)
                if elapsed > 0:
                    out_img_path = out_dir / (pair[0].stem + ".jpg")
                    if out_img_path.exists():
                        color_img = Image.open(out_img_path).convert("RGB")
                        window.write_event_value("-PREVIEW_CLR-", color_img)
                else:
                    log_message(f'⚠️ "{pair[0].name}": troppo scura, saltata')

            except xmlrpc.client.Fault as e:
                log_message(f"RPC Fault: {e.faultString}")
            except Exception as e:
                log_message(f"Errore su coppia {pair[0].name}: {e}")

        window.write_event_value("-PROGRESS-",
                                 (100, f"100% {n_images}/{tot_num_images}"))
        update_status(window, "Status: OK", "info")
        if count > 0:
            log_message(
                f"🎉 Done! {count} immagini in {tot_time:.2f}s "
                f"({tot_time / count:.2f}s/immagine)")

    # ---- STEP 3a: ENCODE x265 ----
    def do_encode_x265(values, window, orig_video_path):
        ref_dir = os.path.join(values["-BASE_DIR-"], "ref_qwen")
        video_base_path = os.path.splitext(values["-VIDEO_DROPDOWN-"])[0]
        sfx = "_dt-color.h265" if "cmnet2" in video_base_path else "_cmnet2_dt-color.h265"
        out_video_file = os.path.join(values["-BASE_DIR-"], video_base_path + sfx)

        crf_val    = window["-CRF-"].get().strip() or "20.0"
        fps_val    = values["-FPS-"].strip() or "24000/1001"
        render_speed = window["-RENDER_SPEED-"].get().strip() or "auto"
        memory_frames = window["-MEMORY_FRAMES-"].get().strip() or "20"
        encode_vpy = os.path.join(values["-SCRIPT_DIR-"], values["-ENCODE_VPY-"])

        vsp_cmd = (f'"{values["-VSPIPE-"]}" "{encode_vpy}" - '
                   f'-a "VideoPath={orig_video_path}" -a "RefDir={ref_dir}" '
                   f'-a "RenderSpeed={render_speed}" -a "MemoryFrames={memory_frames}" '
                   f'--outputindex 0 -c y4m')
        x265_cmd = (f'"{values["-X265-"]}" --preset fast --input - '
                    f'--fps {fps_val} --output-depth 10 --y4m --profile main10 '
                    f'--crf {crf_val} --output "{out_video_file}"')

        total_frames = state.get("total_frames", -1)
        if total_frames <= 0:
            info = get_video_info(
                values["-VSPIPE-"], orig_video_path,
                values["-SCRIPT_DIR-"], log_message)
            if info:
                total_frames = info["frames"]
                window.write_event_value("-FPS-", info["fps"])

        full_cmd = f"{vsp_cmd} | {x265_cmd}"
        log_message(f'ℹ️ Avvio encoding con script: "{values["-ENCODE_VPY-"]}"')
        log_message("----------------------------------------------------------------")
        log_message(f"[ENCODE] {full_cmd.strip()}")
        log_message("----------------------------------------------------------------")

        proc = subprocess.Popen(
            full_cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, universal_newlines=True,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                           if os.name == 'nt' else 0),
        )
        state["current_process"] = proc
        start_time = time.time()
        frame_re   = re.compile(r"(\d+)/\d+\s+Frames", re.IGNORECASE)
        curr = 0
        for line in proc.stderr:
            if state["stop_requested"]:
                break
            line = line.strip()
            if total_frames > 0:
                match = frame_re.search(line)
                if match:
                    curr = int(match.group(1))
                    p    = min(100, int((curr / total_frames) * 100))
                    log_gui_only(f"[ENCODE] {line}")
                    eta = get_eta_string(curr, total_frames, start_time)
                    update_status(window, f"Status: ETA ENCODE: {eta}...", "info")
                    window.write_event_value(
                        "-PROGRESS-", (p, f"{p}% {curr}/{total_frames}"))
                else:
                    log_message(line)

        proc.wait()
        p = min(100, int((curr / total_frames) * 100)) if total_frames > 0 else 100
        window.write_event_value("-PROGRESS-", (p, f"{p}% {curr}/{total_frames}"))
        if p < 90:
            update_status(window, "Status: Failed", "error")
            log_message(f"[FAILED] Codificati solo {curr}/{total_frames}")
        else:
            update_status(window, "Status: OK", "success")
            log_message(f"[COMPLETED] Encoding: {orig_video_path} @ {fps_val} fps")
            create_video_mkv(values["-MKV_PATH-"], out_video_file, fps_val, log_message)
        return out_video_file

    # ---- STEP 3b: ENCODE NVEnc ----
    def do_encode_Nvenc(values, window, orig_video_path):
        total_frames = state.get("total_frames", -1)
        info = get_video_info(
            values["-VSPIPE-"], orig_video_path,
            values["-SCRIPT_DIR-"], log_message)
        if info and total_frames <= 0:
            total_frames = info["frames"]
            window.write_event_value("-FPS-", info["fps"])

        ref_dir        = os.path.join(values["-BASE_DIR-"], "ref_qwen")
        video_base_path = os.path.splitext(values["-VIDEO_DROPDOWN-"])[0]
        sfx = "_dt-color.h265" if "cmnet2" in video_base_path else "_cmnet2_dt-color.h265"
        out_video_file = os.path.join(values["-BASE_DIR-"], video_base_path + sfx)

        fps_val    = values["-FPS-"].strip() or "24000/1001"
        render_speed = window["-RENDER_SPEED-"].get().strip() or "auto"
        memory_frames = window["-MEMORY_FRAMES-"].get().strip() or "20"
        encode_vpy = os.path.join(values["-SCRIPT_DIR-"], values["-ENCODE_VPY-"])

        vsp_cmd = (f'"{values["-VSPIPE-"]}" "{encode_vpy}" - '
                   f'-a "VideoPath={orig_video_path}" -a "RefDir={ref_dir}" '
                   f'-a "RenderSpeed={render_speed}" -a "MemoryFrames={memory_frames}" '
                   f'--outputindex 0 -c y4m')
        sharp_filter = window["-USE_SHARP-"].get()
        sharp = "--vpp-unsharp --vpp-edgelevel" if sharp_filter else ""
        res = f"{info['width']}x{info['height']}"
        nvenc_exe = os.path.join(Path(values["-X265-"]).parent.parent / "NVEncC" , "NVEncC64.exe")
        nvenc_opt = (
            "--profile main10 --level auto --tier high --sar 1:1 "
            "--lookahead 16 --output-depth 10 --aq --aq-strength 5 "
            "--aq-temporal --gop-len 0 --ref 3 --bframes 5 --bref-mode auto "
            "--mv-precision Q-pel --lookahead-level 1 --preset default "
            "--cuda-schedule sync"
        )
        nvenc_cmd = (
            f'"{nvenc_exe}" --y4m -i - --input-res {res} '
            f'--fps {info["fps"]} --codec h265 --vbr 0 '
            f'--vbr-quality {window["-VBR_QUALITY-"].get()} '
            f'{nvenc_opt} {sharp} --output "{out_video_file}"'
        )
        full_cmd = f"{vsp_cmd} | {nvenc_cmd}"
        run_command(full_cmd, total_frames, task_name="ENCODE")

        curr = total_frames
        p    = min(100, int((curr / total_frames) * 100)) if total_frames > 0 else 100
        window.write_event_value("-PROGRESS-", (p, f"{p}% {curr}/{total_frames}"))
        if p < 90:
            update_status(window, "Status: Failed", "error")
            log_message(f"[FAILED] Codificati solo {curr}/{total_frames}")
        else:
            update_status(window, "Status: OK", "success")
            log_message(f"[COMPLETED] Encoding: {orig_video_path} @ {fps_val} fps")
            create_video_mkv(values["-MKV_PATH-"], out_video_file, fps_val, log_message)
        return out_video_file

    # ---- STEP 4: MERGE ----
    def do_video_merge(values, window, orig_video_path, last_encoded_file):
        if not last_encoded_file or not os.path.exists(last_encoded_file):
            video_base = os.path.splitext(values["-VIDEO_DROPDOWN-"])[0]
            sfx = ("_dt-color.mkv" if "cmnet2" in video_base.lower()
                   else "_cmnet2_dt-color.mkv")
            last_encoded_file = os.path.join(
                values["-BASE_DIR-"], video_base + sfx)

        merge_vpy = os.path.join(values["-SCRIPT_DIR-"], "cmnet2_merge-m2.vpy")
        vsp_cmd = (
            f'"{values["-VSPIPE-"]}" "{merge_vpy}" - '
            f'-a "VideoPath1={orig_video_path}" '
            f'-a "VideoPath2={last_encoded_file}" '
            f'-a "Weight={window["-MERGE_WEIGHT-"].get()}" '
            f'--outputindex 0 -c y4m'
        )

        if not os.path.exists(last_encoded_file):
            log_message(f"⚠️ File non trovato per il merge: {last_encoded_file}")
            return

        info = get_video_info(
            values["-VSPIPE-"], orig_video_path,
            values["-SCRIPT_DIR-"], log_message)
        total_frames = info["frames"] if info else -1
        out_merge = str(
            Path(last_encoded_file).with_name(
                Path(last_encoded_file).stem + "_merged.h265"))
        sharp = "--vpp-unsharp --vpp-edgelevel" if window["-USE_SHARP-"].get() else ""
        res   = f"{info['width']}x{info['height']}"
        nvenc_exe = os.path.join(Path(values["-X265-"]).parent.parent / "NVEncC" , "NVEncC64.exe")
        nvenc_opt = (
            "--profile main10 --level auto --tier high --sar 1:1 "
            "--lookahead 16 --output-depth 10 --aq --aq-strength 5 "
            "--aq-temporal --gop-len 0 --ref 3 --bframes 5 --bref-mode auto "
            "--mv-precision Q-pel --lookahead-level 1 --preset default "
            "--cuda-schedule sync"
        )
        nvenc_cmd = (
            f'"{nvenc_exe}" --y4m -i - --input-res {res} '
            f'--fps {info["fps"]} --codec h265 --vbr 0 '
            f'--vbr-quality {window["-VBR_QUALITY-"].get()} '
            f'{nvenc_opt} {sharp} --output "{out_merge}"'
        )
        full_cmd = f"{vsp_cmd} | {nvenc_cmd}"
        run_command(full_cmd, total_frames, task_name="MERGE")
        create_video_mkv(values["-MKV_PATH-"], out_merge, info["fps"], log_message)

    # ---- ORCHESTRATOR MAIN LOOP ----
    try:
        tasks = []
        if init_values["-DO_STEP1-"]: tasks.append("EXTRACT")
        if init_values["-DO_STEP2-"]: tasks.append("COLORIZE")
        if init_values["-DO_STEP3-"]: tasks.append("ENCODE")
        if init_values["-DO_STEP4-"]: tasks.append("MERGE")

        orig_video_path = os.path.join(
            init_values["-BASE_DIR-"], init_values["-VIDEO_DROPDOWN-"])
        info = get_video_info(
            init_values["-VSPIPE-"], orig_video_path,
            init_values["-SCRIPT_DIR-"], log_fn=log_message)
        total_frames = info["frames"] if info else -1
        state["total_frames"] = total_frames
        last_encoded_file = None

        for task in tasks:
            if state["stop_requested"]:
                log_message("⚠️ STOP richiesto")
                break
            log_message(f">>> AVVIO TASK: {task}")

            if task == "EXTRACT":
                if not window["-DO_STEP1-"].get():
                    log_message("⚠️ Task Extraction cancellato")
                else:
                    do_extraction(init_values, window, orig_video_path)

            elif task == "COLORIZE":
                fast_pipeline = bool(window["-FAST_PIPE-"].get())
                if not window["-DO_STEP2-"].get():
                    log_message("⚠️ Task Colorization cancellato")
                else:
                    if fast_pipeline:
                        do_colorize_fast(init_values, window)
                    else:
                        do_colorize(init_values, window)

            elif task == "ENCODE":
                if not window["-DO_STEP3-"].get():
                    log_message("⚠️ Task Encoding cancellato")
                else:
                    if window["-ENCODER-"].get() == "x265":
                        last_encoded_file = do_encode_x265(
                            init_values, window, orig_video_path)
                    else:
                        last_encoded_file = do_encode_Nvenc(
                            init_values, window, orig_video_path)

            elif task == "MERGE":
                if not window["-DO_STEP4-"].get():
                    log_message("⚠️ Task Merge cancellato")
                else:
                    do_video_merge(
                        init_values, window, orig_video_path, last_encoded_file)

        log_message("[COMPLETED] Tutti i task completati con successo.")
        window.write_event_value("-FINISHED-", True)

    except Exception as e:
        log_message(f"FATAL ERROR: {str(e)}")
        window.write_event_value("-FINISHED-", False)
    finally:
        if log_file:
            status = "COMPLETED" if not state["stop_requested"] else "STOPPED"
            print(f"--- SESSION {status}: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n",
                  file=log_file, flush=True)
            log_file.close()
        state["is_running"] = False


# ===========================================================================
# GUI LAYOUT
# ===========================================================================
cfg = load_all_configs()
sg.theme("DarkBlue14")

merge_values:      list[str] = [f"{x/100:.2f}" for x in range(30, 75, 5)]
x265_crf_values:   list[str] = [f"{x/10:.2f}" for x in range(180, 285, 5)]
nvenc_cq_values:   list[str] = [f"{x/10:.2f}" for x in range(220, 305, 5)]
encoder_values:    list[str] = ['x265', 'Nvenc']
memory_values:     list[str] = [f"{x}" for x in range(10, 110, 10)]
steps_values:      list[str] = ['2', '4', '8']
speed_values:    list[str] = ['auto', 'fast', 'medium', 'slow', 'slower']
model_list:        list[str] = ["nunchaku-qwen", "gguf-qwen"]
model_p_list:      list[str] = ["fp4", "int4", "q3", "q4", "q5", "q6", "q8"]
model_r_list:      list[str] = ["32", "128"]
model_steps_list:  list[str] = ["4", "8"]

sc_tht_values:  list[str] = [f"{x/1000:.3f}" for x in range(20, 155, 5)]
sc_ssim_values: list[str] = [f"{x/100:.2f}"  for x in range(0, 100, 5)]
sc_int_values:  list[str] = [f"{x}" for x in range(5, 55, 5)]
sc_mult_values: list[str] = [f"{x}" for x in range(0, 26, 1)]

# ---------------------------------------------------------------------------
# TAB 1 — Dashboard
# ---------------------------------------------------------------------------
tab1_layout = [
    [sg.Text("Pipeline Controller", font=("Any", 16, "bold"))],
    [sg.Frame("Tasks to Execute", [
        [sg.Checkbox("1. Extract Reference Frames",    key="-DO_STEP1-", default=cfg["do_step1"])],
        [sg.Checkbox("2. Colorize Frames (AI)",        key="-DO_STEP2-", default=cfg["do_step2"])],
        [sg.Checkbox("3. Encode Video (x265 / Nvenc)", key="-DO_STEP3-", default=cfg["do_step3"])],
        [sg.Checkbox("4. Video Merge (NVEnc)",         key="-DO_STEP4-", default=cfg["do_step4"])],
    ], expand_x=True)],
    [sg.Checkbox("Shutdown PC when finished", key="-SHUTDOWN-",
                 default=cfg["shutdown_on_complete"])],
    [sg.Button("START PIPELINE", size=(20, 2), button_color="Green", key="-RUN-"),
     sg.Button("STOP", size=(10, 2), button_color="SaddleBrown",
               key="-STOP-", disabled=True)],
    [sg.ProgressBar(100, orientation='h', size=(20, 20),
                    key="-PBAR-", expand_x=True),
     sg.Text("0%", key="-PTEXT-", size=(15, 1))],
    [sg.Multiline(size=(82, 12), key="-LOG_BOX-", autoscroll=True,
                  expand_x=True, expand_y=True, font=("Courier New", 9))],
]

# ---------------------------------------------------------------------------
# TAB 2 — Extraction
# ---------------------------------------------------------------------------
tab2_layout = [
    [sg.Text("Extraction Settings", font=("Any", 14, "bold"))],
    [sg.Text("VapourSynth Pipe:"),
     sg.Input(cfg["vspipe_path"], key="-VSPIPE-", expand_x=True), sg.FileBrowse()],
    [sg.Text("Script Directory:"),
     sg.Input(cfg["script_dir"], key="-SCRIPT_DIR-", expand_x=True, enable_events=True),
     sg.FolderBrowse()],
    [sg.Text("Extract VPY:"),
     sg.Combo(scan_files(cfg["script_dir"], "*extract_*.vpy"),
              key="-EXTRACT_VPY-", expand_x=True, default_value=cfg["extract_script"])],
    [sg.Text("threshold:"),
     sg.Combo(sc_tht_values,  default_value=cfg["sc_threshold"], key="-SC_THT-",      readonly=True, size=(6,1)),
     sg.Text("tht_ssim:"),
     sg.Combo(sc_ssim_values, default_value=cfg["sc_tht_ssim"],  key="-SC_THT_SSIM-", readonly=True, size=(6,1)),
     sg.Text("min_int:"),
     sg.Combo(sc_int_values,  default_value=cfg["sc_min_int"],   key="-SC_MIN_INT-",  readonly=True, size=(6,1)),
     sg.Text("mult/freq:"),
     sg.Combo(sc_mult_values, default_value=cfg["sc_mult_tht"],  key="-SC_MULT_THT-", readonly=True, size=(6,1)),
     sg.Checkbox("Ref Override", key="-REF_OVERRIDE-", default=cfg["ref_override"])],
    [sg.HorizontalSeparator()],
    [sg.Checkbox("Create ref_000000.jpg from second frame",
                 key="-DUPE_FIRST_FRAME-", default=cfg["dupe_first_frame"])],
    [sg.Text("Video Directory:"),
     sg.Input(cfg["base_dir"], key="-BASE_DIR-", enable_events=True, expand_x=True),
     sg.FolderBrowse()],
    [sg.Text("Select Video:"),
     sg.Combo(scan_videos(cfg["base_dir"]), key="-VIDEO_DROPDOWN-", expand_x=True),
     sg.Button("Refresh")],
    [sg.Frame("Video Technical Details", [
        [sg.Column([
            [sg.Text("Resolution:",   size=(12, 1)),
             sg.Text("-", key="-INF_RES-",    text_color="yellow", font=("Any", 10, "bold"))],
            [sg.Text("FPS:",          size=(12, 1)),
             sg.Text("-", key="-INF_FPS-",    text_color="yellow", font=("Any", 10, "bold"))],
            [sg.Text("Total Frames:", size=(12, 1)),
             sg.Text("-", key="-INF_FRAMES-", text_color="yellow", font=("Any", 10, "bold"))],
            [sg.Text("Video Format:", size=(12, 1)),
             sg.Text("-", key="-INF_FORMAT-", text_color="yellow", font=("Any", 10, "bold"))],
        ], expand_x=True)],
    ], expand_x=True)],
]

# ---------------------------------------------------------------------------
# TAB 3 — Colorization  (novità: frame connessione RPC in cima)
# ---------------------------------------------------------------------------
tab3_layout = [
    [sg.Text("AI Colorization Settings", font=("Any", 14, "bold"))],

    # --- Connessione RPC (NUOVO) ---
    [sg.Frame("RPC Server Connection", [
        [sg.Text("Host:", size=(5,1)),
         sg.Input(cfg.get("rpc_host", "127.0.0.1"), key="-RPC_HOST-", size=(20, 1)),
         sg.Text("Port:", size=(5,1)),
         sg.Input(str(cfg.get("rpc_port", 8765)), key="-RPC_PORT-", size=(6, 1)),
         sg.Button("Connect", key="-CONNECT-", button_color=("white", "#1a6b1a")),
         sg.Text("●", key="-RPC_LED-", text_color="red",
                 font=("Any", 14, "bold")),
         sg.Text("Non connesso", key="-RPC_STATUS_TEXT-", text_color="red",
                 size=(12, 1))],
    ], expand_x=True)],

    [sg.Text("HF Cache:"),
     sg.Input(cfg["hf_cache"], key="-CACHE_DIR-", expand_x=True), sg.FolderBrowse()],
    [sg.Frame("Model Technical Details", [
        [sg.Text("Model Name:"),
         sg.Combo(model_list,      default_value=cfg["model_name"],           key="-MODEL_NAME-",     readonly=True, size=(18,1)),
         sg.Text("Model Precision:"),
         sg.Combo(model_p_list,    default_value=cfg["model_precision"],      key="-MODEL_PRECISION-",readonly=True, size=(6,1)),
         sg.Text("Model Rank:"),
         sg.Combo(model_r_list,    default_value=cfg["model_rank"],           key="-MODEL_RANK-",     readonly=True, size=(6,1)),
         sg.Text("Model Steps:"),
         sg.Combo(model_steps_list,default_value=cfg["model_inference_steps"],key="-MODEL_INF_STEPS-",readonly=True, size=(6,1))],
        [sg.Text("Colorization Steps:"),
         sg.Combo(steps_values, default_value=cfg["steps"], key="-STEPS-", readonly=True, size=(6,1)),
         sg.Checkbox("Fast Pipeline", key="-FAST_PIPE-", default=cfg["fast_pipe"])],
    ], expand_x=True)],
    [sg.Text("Prompt:"), sg.Input(cfg["prompt"], key="-PROMPT-", expand_x=True)],
    [sg.Column([
        [sg.Text("B&W Input")],
        [sg.Image(data=b'', key="-IMG_BW-", size=(370, 350), background_color="black")],
    ]),
     sg.Column([
        [sg.Text("AI Output")],
        [sg.Image(data=b'', key="-IMG_CLR-", size=(370, 350), background_color="black")],
    ])],
]

# ---------------------------------------------------------------------------
# TAB 4 — Encode/Merge
# ---------------------------------------------------------------------------
tab4_layout = [
    [sg.Text("Encode/Merge Settings", font=("Any", 14, "bold"))],
    [sg.Text("MKVmerge Path:"),
     sg.Input(cfg["mkv_path"], key="-MKV_PATH-", expand_x=True), sg.FileBrowse()],
    [sg.Text("x265 Path:"),
     sg.Input(cfg["x265_path"], key="-X265-", expand_x=True), sg.FileBrowse()],
    [sg.Text("Encode VPY:"),
     sg.Combo(scan_files(cfg["script_dir"], "*encode_*.vpy"),
              key="-ENCODE_VPY-", expand_x=True, default_value=cfg["encode_script"])],
    [sg.Text("CRF:"),
     sg.Combo(x265_crf_values, default_value=cfg["crf"],
              key="-CRF-", readonly=True, size=(6,1)),
     sg.Text("FPS:"),
     sg.Input("24000/1001", key="-FPS-", size=(12,1)),
     sg.Text("Encoder:"),
     sg.Combo(encoder_values, default_value=cfg.get("encoder","x265"),
              key="-ENCODER-", readonly=True, size=(8,1)),
     sg.Text("Memory Frames:"),
     sg.Combo(memory_values, default_value=cfg.get("frames_memory", "20"),
              key="-MEMORY_FRAMES-", readonly=True, size=(5, 1)),
     sg.Text("Render Speed:"),
     sg.Combo(speed_values, default_value=cfg.get("render_speed", "auto"),
              key="-RENDER_SPEED-", readonly=True, size=(8, 1))
     ],
    [sg.Frame("NVEnc Merge Settings", [
        [sg.Text("Merge Weight:"),
         sg.Combo(merge_values, default_value=cfg.get("merge_weight","0.40"),
                  key="-MERGE_WEIGHT-", readonly=True, size=(6,1)),
         sg.Text("VBR Quality:"),
         sg.Combo(nvenc_cq_values, default_value=cfg.get("vbr_quality","27.00"),
                  key="-VBR_QUALITY-", readonly=True, size=(8,1))],
        [sg.Checkbox("Enable NVEnc Sharpness (--vpp-unsharp --vpp-edgelevel)",
                     key="-USE_SHARP-", default=cfg.get("use_sharp", True))
         ],
    ], expand_x=True)],
    [sg.Text("Note: Output will be saved in the Project Directory as [video]_cmnet2_dt-color.mkv")],
]

# ---------------------------------------------------------------------------
# MAIN LAYOUT
# ---------------------------------------------------------------------------
layout = [
    [sg.TabGroup([
        [sg.Tab("Dashboard",     tab1_layout),
         sg.Tab("1. Extraction", tab2_layout),
         sg.Tab("2. Colorization", tab3_layout),
         sg.Tab("3. Encode/Merge", tab4_layout)]
    ], expand_x=True, expand_y=True)],
    [sg.Button("Save Global Settings"),
     sg.Text("Status: OK", size=(70, 1), expand_x=True,
             key="-STATUS-", background_color="cyan",
             text_color="black", font=("Arial", 10, "italic")),
     sg.Push(),
     sg.Button("Exit")],
]

window = sg.Window("CMNET2 Master Suite", layout, finalize=True,
                   resizable=True, size=(cfg["window_w"], cfg["window_h"]))

# ===========================================================================
# EVENT LOOP
# ===========================================================================
while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, "Exit"):
        if state["current_process"]:
            state["current_process"].terminate()
        break

    # ---- Connessione al server RPC ----
    if event == "-CONNECT-":
        host = values["-RPC_HOST-"].strip()
        port = values["-RPC_PORT-"].strip()
        window["-CONNECT-"].update(disabled=True)
        window["-RPC_LED-"].update("●", text_color="yellow")
        window["-RPC_STATUS_TEXT-"].update("⏳ ...", text_color="yellow")
        window["-LOG_BOX-"].print(f"[RPC] Connessione a {host}:{port}...")
        threading.Thread(
            target=_connect_thread, args=(host, port, window), daemon=True
        ).start()

    if event == "-RPC_CONNECT_DONE-":
        ok, err_msg = values["-RPC_CONNECT_DONE-"]
        window["-CONNECT-"].update(disabled=False)
        if ok:
            window["-RPC_LED-"].update("●", text_color="lime")
            window["-RPC_STATUS_TEXT-"].update("✅ OK", text_color="lime")
            update_status(window, "Status: Server RPC connesso", "info")
        else:
            window["-RPC_LED-"].update("●", text_color="red")
            window["-RPC_STATUS_TEXT-"].update("❌ Errore", text_color="red")
            update_status(window, "Status: Connessione RPC fallita", "error")

    # ---- Aggiorna combo script quando cambia la dir ----
    if event == "-SCRIPT_DIR-":
        ev = scan_files(values["-SCRIPT_DIR-"], "cmnet2_extract_*.vpy")
        if ev: window["-EXTRACT_VPY-"].update(values=ev)
        ev = scan_files(values["-SCRIPT_DIR-"], "cmnet2_encode_*.vpy")
        if ev: window["-ENCODE_VPY-"].update(values=ev)

    if event in ("Refresh", "-BASE_DIR-"):
        vids = scan_videos(values["-BASE_DIR-"])
        selected_video = (values["-VIDEO_DROPDOWN-"]
                          if values["-VIDEO_DROPDOWN-"] in vids
                          else (vids[0] if vids else ""))
        window["-VIDEO_DROPDOWN-"].update(
            values=vids, value=selected_video)
        if vids:
            video_path = os.path.join(values["-BASE_DIR-"], selected_video)
            info = get_video_info(
                values["-VSPIPE-"], video_path, values["-SCRIPT_DIR-"], log_gui_only)
            if info:
                state["total_frames"] = info["frames"]
                update_video_info(window, info)

    if event == "-VIDEO_DROPDOWN-" and values["-VIDEO_DROPDOWN-"]:
        video_path = os.path.join(values["-BASE_DIR-"], values["-VIDEO_DROPDOWN-"])
        info = get_video_info(
            values["-VSPIPE-"], video_path, values["-SCRIPT_DIR-"], log_gui_only)
        if info:
            state["total_frames"] = info["frames"]
            update_video_info(window, info)

    # ---- Salva configurazione ----
    if event == "Save Global Settings":
        curr_w, curr_h = window.size
        cfg.update({
            "vspipe_path":           values["-VSPIPE-"],
            "x265_path":             values["-X265-"],
            "script_dir":            values["-SCRIPT_DIR-"],
            "extract_script":        values["-EXTRACT_VPY-"],
            "encode_script":         values["-ENCODE_VPY-"],
            "base_dir":              values["-BASE_DIR-"],
            "model_name":            values["-MODEL_NAME-"],
            "model_precision":       values["-MODEL_PRECISION-"],
            "model_rank":            values["-MODEL_RANK-"],
            "model_inference_steps": values["-MODEL_INF_STEPS-"],
            "steps":                 values["-STEPS-"],
            "fast_pipe":             values["-FAST_PIPE-"],
            "mkv_path":              values["-MKV_PATH-"],
            "hf_cache":              values["-CACHE_DIR-"],
            "prompt":                values["-PROMPT-"],
            "shutdown_on_complete":  values["-SHUTDOWN-"],
            "dupe_first_frame":      values["-DUPE_FIRST_FRAME-"],
            "do_step1":              values["-DO_STEP1-"],
            "do_step2":              values["-DO_STEP2-"],
            "do_step3":              values["-DO_STEP3-"],
            "do_step4":              values["-DO_STEP4-"],
            "sc_threshold":          values["-SC_THT-"],
            "sc_tht_ssim":           values["-SC_THT_SSIM-"],
            "sc_min_int":            values["-SC_MIN_INT-"],
            "sc_mult_tht":           values["-SC_MULT_THT-"],
            "ref_override":          values["-REF_OVERRIDE-"],
            "crf":                   values["-CRF-"],
            "encoder":               values["-ENCODER-"],
            "frames_memory":         values["-MEMORY_FRAMES-"],
            "render_speed":          values["-RENDER_SPEED-"],
            "merge_weight":          values["-MERGE_WEIGHT-"],
            "vbr_quality":           values["-VBR_QUALITY-"],
            "use_sharp":             values["-USE_SHARP-"],
            # RPC
            "rpc_host":              values["-RPC_HOST-"],
            "rpc_port":              int(values["-RPC_PORT-"]),
            # window
            "window_w": curr_w,
            "window_h": curr_h,
        })
        save_all_configs(cfg)
        sg.popup("Settings saved to JSON.")

    # ---- Avvio pipeline ----
    if event == "-RUN-":
        if not values["-VIDEO_DROPDOWN-"]:
            sg.popup_error("Seleziona prima un file video!")
            continue
        if (values["-DO_STEP2-"] and not state["rpc_connected"]):
            sg.popup_error(
                "Il task Colorization è selezionato ma il client\n"
                "non è connesso al server RPC.\n\n"
                "Vai alla tab '2. Colorization' e clicca Connect.")
            continue
        window["-RUN-"].update(disabled=True)
        window["-STOP-"].update(disabled=False)
        window["-LOG_BOX-"].update("--- STARTING BATCH ---\n")
        threading.Thread(
            target=orchestrator,
            args=(values, window),
            daemon=True,
        ).start()

    # ---- Stop ----
    if event == "-STOP-":
        if sg.popup_yes_no("Fermare il task corrente?") == "Yes":
            state["stop_requested"] = True
            # Notifica anche il server se connesso
            rpc = state.get("rpc_client")
            if rpc:
                try:
                    rpc.request_stop()
                except Exception:
                    pass
            if state["current_process"]:
                try:
                    os.kill(state["current_process"].pid,
                            signal.CTRL_BREAK_EVENT)
                except Exception:
                    pass

    # ---- Thread events ----
    if event == "-LOG-":
        window["-LOG_BOX-"].print(values["-LOG-"])
    if event == "-PROGRESS-":
        val, txt = values["-PROGRESS-"]
        window["-PBAR-"].update(val)
        window["-PTEXT-"].update(txt)
    if event == "-PREVIEW_BW-":
        window["-IMG_BW-"].update(data=pil_to_png_data(values["-PREVIEW_BW-"]))
    if event == "-PREVIEW_CLR-":
        window["-IMG_CLR-"].update(data=pil_to_png_data(values["-PREVIEW_CLR-"]))
    if event == "-FINISHED-":
        window["-RUN-"].update(disabled=False)
        window["-STOP-"].update(disabled=True)
        if values["-FINISHED-"]:
            window["-LOG_BOX-"].print(
                "\n[COMPLETED] Tutti i task completati.", text_color="green")
            if window["-SHUTDOWN-"].get():
                window["-LOG_BOX-"].print(
                    "Shutdown avviato (60s)...", text_color="red")
                os.system("shutdown /s /t 60")
        else:
            window["-LOG_BOX-"].print(
                "\n[STOPPED] Processo fermato o fallito.", text_color="orange")

window.close()
