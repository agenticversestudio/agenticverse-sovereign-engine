"""
AgenticVerse Sovereign Cloud Orchestrator Daemon
================================================
Production-Grade Automated 24/7 Sovereign AI Engine for Render / Koyeb / Docker.
Features:
  - Built-in HTTP Health Server (Listens on os.environ.get('PORT', 8080)) for Koyeb/Render/UptimeRobot
  - Zero-Inactivity Keep-Alive: Continuous Web Endpoint prevents Cloud Service Sleep
  - Multi-Account Token Vault Ingestion via Environment Variables or Mounted Vault
  - Headless Colab VM Provisioning via `google-colab-cli`
  - 11.5-Hour Preemptive Shift Handover (Zero GPU Exhaustion)
  - 60-Second Ingress Probing & Self-Healing Auto-Failover
"""

import os
import sys
import time
import json
import shutil
import logging
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import requests

# UTF-8 Encoding Guard
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
VAULT_DIR = os.environ.get("VAULT_DIR", r"D:\Projects\Google\colab_vault")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
COLAB_CONFIG_DIR = os.path.expanduser("~/.config/colab-cli")

def _load_dotenv(path):
    """Tiny .env loader (no dependency). Real environment variables win."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)
os.makedirs(COLAB_CONFIG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "orchestrator.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AgenticVerseCloud")

# Ingress & Engine Settings
NGROK_DOMAIN = os.environ.get("NGROK_DOMAIN", "")
HEALTH_URL = os.environ.get("INGRESS_HEALTH_URL", f"https://{NGROK_DOMAIN}/v1/models")
API_KEY = os.environ.get("AGENTIC_API_KEY", "")
PASSKEY = os.environ.get("AGENTIC_PASSKEY", "")
if not API_KEY or not NGROK_DOMAIN:
    sys.exit("[FATAL] Missing AGENTIC_API_KEY / NGROK_DOMAIN. Copy .env.example to .env and fill it in (see RESTART_GUIDE.md).")
SHIFT_MAX_HOURS = float(os.environ.get("SHIFT_MAX_HOURS", 3.5))
HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", 30))
CONSECUTIVE_FAILURES_LIMIT = 5
# --- Safe defaults (see RESTART_GUIDE.md) ---------------------------------
# ACCOUNT_COUNT=1 -> only the first account is used (no rotation).
# Colab's FAQ disallows "using multiple accounts to work around access or
# resource usage restrictions". Set ACCOUNT_COUNT=2/3 only if you accept that risk.
ACCOUNT_COUNT = max(1, int(os.environ.get("ACCOUNT_COUNT", 1)))
# When Google says "Service Unavailable" (no T4 free), wait with exponential backoff
# instead of hammering: 5 min, 10, 20, 40 ... capped at 60 min.
BACKOFF_BASE_SECONDS = int(os.environ.get("BACKOFF_BASE_SECONDS", 300))
BACKOFF_MAX_SECONDS = int(os.environ.get("BACKOFF_MAX_SECONDS", 3600))
# Heartbeat did not prevent ~2h session loss in the logs; off by default.
KEEPALIVE = os.environ.get("KEEPALIVE", "0") == "1"
PORT = int(os.environ.get("PORT", 8080))

# Accounts Setup
ACCOUNTS = [
    {"id": "primary", "name": "Shift 1 - Primary Account", "vault_token": os.path.join(VAULT_DIR, "primary", "token.json"), "env_var": "TOKEN_PRIMARY_B64"},
    {"id": "iconjagat", "name": "Shift 2 - iconjagat@gmail.com", "vault_token": os.path.join(VAULT_DIR, "iconjagat", "token.json"), "env_var": "TOKEN_ICONJAGAT_B64"},
    {"id": "ecogainnexus", "name": "Shift 3 - ecogainnexus@gmail.com", "vault_token": os.path.join(VAULT_DIR, "ecogainnexus", "token.json"), "env_var": "TOKEN_ECOGAIN_B64"}
]
ACTIVE_ACCOUNTS = ACCOUNTS[:ACCOUNT_COUNT]

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "current_account_index": 0,
        "shift_started_at": 0,
        "consecutive_failures": 0,
        "total_rotations": 0,
        "status": "idle"
    }

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving state: {e}")

# ----------------- Koyeb / Render Health HTTP Server -----------------
class CloudHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        state = load_state()
        curr_idx = state.get("current_account_index", 0)
        account_name = ACCOUNTS[curr_idx]["name"] if curr_idx < len(ACCOUNTS) else "Unknown"
        started = state.get("shift_started_at", 0)
        elapsed_hrs = (time.time() - started) / 3600.0 if started > 0 else 0.0

        resp_data = {
            "status": "online",
            "service": "AgenticVerse Sovereign Cloud Orchestrator",
            "engine": state.get("status", "running"),
            "uptime_hours": round(elapsed_hrs, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp_data, indent=2).encode("utf-8"))

    def log_message(self, format, *args):
        # Silence default HTTP server access logs to keep terminal clean
        return

def start_cloud_http_server():
    server = HTTPServer(("0.0.0.0", PORT), CloudHealthHandler)
    logger.info(f"⚡ Cloud Health & Keep-Alive HTTP Server listening on port {PORT}")
    server.serve_forever()

# ----------------- Cloud Orchestrator Core -----------------
class AgenticVerseOrchestrator:
    def __init__(self):
        self.state = load_state()

    def bootstrap_env_tokens(self):
        """Unpacks environment variables into vault if running on headless cloud."""
        import base64
        for acc in ACCOUNTS:
            env_val = os.environ.get(acc["env_var"])
            if env_val:
                os.makedirs(os.path.dirname(acc["vault_token"]), exist_ok=True)
                try:
                    decoded = base64.b64decode(env_val).decode("utf-8")
                    with open(acc["vault_token"], "w", encoding="utf-8") as f:
                        f.write(decoded)
                    logger.info(f"[✓] Ingested token from {acc['env_var']} for {acc['name']}")
                except Exception as e:
                    logger.warning(f"Error decoding {acc['env_var']}: {e}")

    def probe_health(self) -> bool:
        """Healthy ONLY if the gateway answers AND the Qwen model is really loaded on the GPU."""
        try:
            hdr = {"Authorization": f"Bearer {API_KEY}", "ngrok-skip-browser-warning": "true"}
            r = requests.get(HEALTH_URL, headers=hdr, timeout=8)
            if r.status_code != 200:
                return False
            models = [m.get("id") for m in r.json().get("data", [])]
            if "qwen3.8-27b-uncensored" not in models:
                return False
            ps_url = HEALTH_URL.replace("/v1/models", "/ps").replace("/models", "/ps")
            r_ps = requests.get(ps_url, headers={**hdr, "x-passkey": PASSKEY}, timeout=8)
            if r_ps.status_code != 200:
                return False
            j = r_ps.json()
            return j.get("status") == "online" and j.get("engine") == "ollama"
        except Exception as e:
            logger.debug(f"Health probe exception: {e}")
            return False

    def fast_in_container_heal(self) -> tuple[bool, bool]:
        """Attempts a clean restart of both Ollama and llama-server inside the existing Colab VM.
        Returns: (healed: bool, session_lost: bool)
        """
        logger.info("[⚡] Attempting fast in-container service revival...")
        try:
            heal_script = os.path.join(SCRIPTS_DIR, "fast_heal.py")
            with open(heal_script, "w", encoding="utf-8") as f:
                f.write("""import os, time
print("[*] Killing ALL stale ollama and llama-server processes...")
os.system("pkill -9 -f llama-server; pkill -9 -f ollama || true")
time.sleep(2)
print("[*] Restarting clean Ollama daemon...")
os.system("nohup /usr/local/bin/ollama serve > /content/ollama_stdout.log 2>&1 &")
time.sleep(4)
print("[*] Triggering model lock into GPU VRAM...")
os.system("nohup ollama run qwen3.8-27b-uncensored 'hi' > /dev/null 2>&1 &")
time.sleep(3)
print("[✓] Fast heal finished.")
""")
            res = subprocess.run(
                ["colab", "exec", "-s", "agenticverse_engine", "-f", heal_script],
                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120
            )
            out = f"{res.stdout.strip()} {res.stderr.strip()}".strip()
            logger.info(f"Fast heal execution: {out}")
            if "not found" in out.lower() or "lost" in out.lower() or "cleaning up" in out.lower() or res.returncode != 0:
                logger.warning("[!] Colab session lost. Rotating shift immediately.")
                return False, True
            time.sleep(10)
            return self.probe_health(), False
        except Exception as e:
            logger.warning(f"Fast heal failed: {e}")
            return False, False

    def deploy_token(self, account_index: int):
        account = ACCOUNTS[account_index]
        src_token = account["vault_token"]
        dest_token = os.path.join(COLAB_CONFIG_DIR, "token.json")

        if not os.path.exists(src_token):
            raise FileNotFoundError(f"Vault token missing for {account['name']} at {src_token}")

        shutil.copyfile(src_token, dest_token)
        logger.info(f"[✓] Active Colab CLI token deployed for: {account['name']}")

    def terminate_current_session(self):
        logger.info("[*] Releasing active Colab cloud sessions on server...")
        try:
            subprocess.run(["colab", "stop", "-s", "agenticverse_engine"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15)
        except Exception:
            pass

    def launch_shift(self, account_index: int):
        account = ACCOUNTS[account_index]

        logger.info("=" * 65)
        logger.info(f"🚀 PROVISIONING SHIFT: {account['name']}")
        logger.info("=" * 65)

        # 1. Deploy token for target account
        self.deploy_token(account_index)

        # 2. Release any previous session on this account
        self.terminate_current_session()

        # 3. Provision Headless T4 GPU VM
        logger.info("[*] Instantiating Tesla T4 GPU VM on Colab...")
        try:
            res = subprocess.run(["colab", "new", "-s", "agenticverse_engine", "--gpu", "T4"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ 'colab new' timed out after 120s (Google did not assign a GPU).")
            return "provision_failed"
        combined_output = f"{res.stdout.strip()} {res.stderr.strip()}".strip()
        # keep logs readable: only the last line of a traceback
        logger.info(f"Colab Provision Status: {combined_output[-300:]}")

        if res.returncode != 0 or "refused" in combined_output.lower() or "limit" in combined_output.lower() or "service unavailable" in combined_output.lower():
            logger.warning(f"⚠️ GPU VM provision failed for {account['name']} (Google had no free T4 or refused). Caller will back off.")
            return "provision_failed"

        # Open session in browser to prevent Colab idle reaping
        subprocess.run(["colab", "url", "-s", "agenticverse_engine", "--open"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15)

        # 4. Upload decoupled server files directly to Colab container
        server_local = os.path.join(SCRIPTS_DIR, "hybrid_server.py")
        payload_local = os.path.join(SCRIPTS_DIR, "colab_payload.py")

        # Secrets are sent to the VM as a file; they are never stored in the code.
        secrets_local = os.path.join(SCRIPTS_DIR, "_secrets.json")
        try:
            with open(secrets_local, "w", encoding="utf-8") as f:
                json.dump({"api_key": API_KEY, "passkey": PASSKEY,
                           "login_user": os.environ.get("AGENTIC_LOGIN_USER", ""),
                           "extra_api_keys": os.environ.get("EXTRA_API_KEYS", ""),
                           "ngrok_token": os.environ.get("NGROK_TOKEN", ""),
                           "ngrok_domain": NGROK_DOMAIN,
                           "groq_api_key": os.environ.get("GROQ_API_KEY", "")}, f)
            subprocess.run(["colab", "upload", "-s", "agenticverse_engine", secrets_local, "/content/secrets.json"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        finally:
            try:
                os.remove(secrets_local)
            except OSError:
                pass

        logger.info("[*] Uploading decoupled server files directly to Colab container...")
        subprocess.run(["colab", "upload", "-s", "agenticverse_engine", server_local, "/content/hybrid_server.py"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        subprocess.run(["colab", "upload", "-s", "agenticverse_engine", payload_local, "/content/colab_payload.py"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)

        # 5. Trigger remote execution via detached launcher script
        launcher_file = os.path.join(BASE_DIR, "launch_payload.py")
        with open(launcher_file, "w", encoding="utf-8") as f:
            f.write("import os\nos.system('nohup python3 /content/colab_payload.py > /content/payload.log 2>&1 &')\n")

        logger.info("[*] Triggering detached setup payload on remote GPU...")
        res_exec = subprocess.run(
            ["colab", "exec", "-s", "agenticverse_engine", "-f", launcher_file],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120
        )
        logger.info(f"Colab Exec Launcher Result: stdout='{res_exec.stdout.strip()}' stderr='{res_exec.stderr.strip()}'")

        self.state["current_account_index"] = account_index
        self.state["shift_started_at"] = time.time()
        self.state["consecutive_failures"] = 0
        self.state["provision_failures"] = 0
        self.state["status"] = "booting"
        save_state(self.state)

        # 4. Wait for warmup
        logger.info("[*] Awaiting model lock into VRAM & Ngrok tunnel activation...")
        warmup_start = time.time()
        poll_step = 0
        while time.time() - warmup_start < 720:
            time.sleep(15)
            poll_step += 1
            if self.probe_health():
                logger.info("=" * 65)
                logger.info(f"🚀 [✓] SHIFT IS ONLINE & RESPONDING TO POCKETSTRIKE!")
                logger.info(f"🌐 Base URL: {HEALTH_URL.replace('/models', '')}")
                logger.info("🔑 API Key: (see your local .env)")
                logger.info("🧠 Model:    qwen3.8-27b-uncensored")
                logger.info("=" * 65)
                self.state["status"] = "running"
                save_state(self.state)
                return "online"

            if poll_step % 2 == 0:
                try:
                    read_script = os.path.join(SCRIPTS_DIR, "read_remote_log.py")
                    p_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                    p_res = subprocess.run(
                        ["colab", "exec", "-s", "agenticverse_engine", "-f", read_script],
                        capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=30, env=p_env
                    )
                    out = p_res.stdout.strip()
                    if out and out != "0":
                        clean_out = out.encode("ascii", "ignore").decode("ascii")
                        logger.info(f"[Remote GPU Progress]\n{clean_out}")
                except Exception:
                    pass

        logger.warning("[!] Warmup period elapsed; Continuing health supervision.")
        return "warmup_timeout"

    def backoff_seconds(self) -> int:
        n = self.state.get("provision_failures", 0)
        return min(BACKOFF_BASE_SECONDS * (2 ** max(0, n - 1)), BACKOFF_MAX_SECONDS)

    def rotate_shift(self, reason: str):
        """Start a fresh shift. Iterative (no recursion). With ACCOUNT_COUNT=1 this
        simply retries the same account after an exponential backoff."""
        cur = self.state.get("current_account_index", 0)
        while True:
            next_index = (cur + 1) % len(ACTIVE_ACCOUNTS)
            logger.info("=" * 65)
            logger.info(f"🔄 SHIFT RESTART: {reason} | slot {cur} ➔ {next_index} (accounts in use: {len(ACTIVE_ACCOUNTS)})")
            logger.info("=" * 65)
            self.state["current_account_index"] = next_index
            self.state["total_rotations"] = self.state.get("total_rotations", 0) + 1
            save_state(self.state)
            result = self.launch_shift(next_index)
            if result != "provision_failed":
                return result
            self.state["provision_failures"] = self.state.get("provision_failures", 0) + 1
            self.state["status"] = "waiting_for_gpu"
            save_state(self.state)
            wait = self.backoff_seconds()
            logger.warning(f"⏳ No GPU yet (failure #{self.state['provision_failures']}). Waiting {wait // 60} min before retrying...")
            time.sleep(wait)
            cur = next_index

    def run(self):
        self.bootstrap_env_tokens()
        logger.info("🌌 AgenticVerse Cloud Orchestrator Started")

        if self.probe_health():
            logger.info("[✓] Gateway is already active and healthy!")
            if self.state["shift_started_at"] == 0:
                self.state["shift_started_at"] = time.time()
            self.state["status"] = "running"
            save_state(self.state)
        else:
            logger.info("[!] Gateway offline. Starting initial boot sequence...")
            if self.launch_shift(self.state.get("current_account_index", 0) % len(ACTIVE_ACCOUNTS)) == "provision_failed":
                self.state["provision_failures"] = self.state.get("provision_failures", 0) + 1
                save_state(self.state)
                self.rotate_shift("Initial boot: no GPU assigned")

        while True:
            try:
                time.sleep(HEALTH_CHECK_INTERVAL)
                now = time.time()

                # Preemptive Shift Handover
                elapsed_hrs = (now - self.state.get("shift_started_at", now)) / 3600.0
                if len(ACTIVE_ACCOUNTS) > 1 and elapsed_hrs >= SHIFT_MAX_HOURS:
                    logger.info(f"⏰ Shift limit reached ({elapsed_hrs:.2f} hrs). Initiating scheduled rotation.")
                    self.rotate_shift(f"Scheduled {SHIFT_MAX_HOURS:g}-hour handover")
                    continue

                # Health Probing
                if self.probe_health():
                    if self.state["consecutive_failures"] > 0:
                        logger.info("[✓] Gateway health restored!")
                    self.state["consecutive_failures"] = 0
                    self.state["status"] = "running"

                    # Colab Kernel Active Heartbeat (Prevents Google idle reaping)
                    try:
                        if not KEEPALIVE:
                            raise RuntimeError("keepalive disabled")
                        hb_script = os.path.join(SCRIPTS_DIR, "kernel_heartbeat.py")
                        subprocess.run(["colab", "exec", "-s", "agenticverse_engine", "-f", hb_script], capture_output=True, timeout=10)
                    except Exception:
                        pass
                else:
                    self.state["consecutive_failures"] += 1
                    failures = self.state["consecutive_failures"]
                    logger.warning(f"⚠️ Health failure {failures}/{CONSECUTIVE_FAILURES_LIMIT}")

                    # Step 1: Fast in-container recovery attempt before heavy VM recreation
                    logger.info("[*] Trying immediate in-container heal...")
                    healed, session_lost = self.fast_in_container_heal()
                    if healed:
                        logger.info("[✓] In-container fast heal succeeded! Engine back online.")
                        self.state["consecutive_failures"] = 0
                        self.state["status"] = "running"
                        save_state(self.state)
                        continue

                    # Step 2: If session is lost or consecutive failures hit limit, rotate immediately
                    if session_lost or failures >= CONSECUTIVE_FAILURES_LIMIT:
                        logger.error("❌ Session lost or gateway unresponsive. Initiating full failover rotation!")
                        self.rotate_shift("Crash Recovery Failover")
                        continue

                save_state(self.state)

            except KeyboardInterrupt:
                logger.info("Stopping Orchestrator on user command...")
                self.terminate_current_session()
                break
            except Exception as e:
                logger.error(f"Orchestrator loop exception: {e}")
                time.sleep(10)

if __name__ == "__main__":
    # Start Cloud HTTP Keep-Alive Server in background thread
    http_thread = threading.Thread(target=start_cloud_http_server, daemon=True)
    http_thread.start()

    orchestrator = AgenticVerseOrchestrator()
    orchestrator.run()
