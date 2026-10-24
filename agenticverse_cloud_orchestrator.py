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
VAULT_DIR = os.environ.get("VAULT_DIR", os.path.join(BASE_DIR, "vault"))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
COLAB_CONFIG_DIR = os.path.expanduser("~/.config/colab-cli")

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
HEALTH_URL = os.environ.get("INGRESS_HEALTH_URL", "https://eel-feminine-progeny.ngrok-free.dev/v1/models")
API_KEY = os.environ.get("AGENTIC_API_KEY", "sk-jaggu")
SHIFT_MAX_HOURS = float(os.environ.get("SHIFT_MAX_HOURS", 11.5))
HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", 60))
CONSECUTIVE_FAILURES_LIMIT = 3
PORT = int(os.environ.get("PORT", 8080))

# Accounts Setup
ACCOUNTS = [
    {"id": "primary", "name": "Shift 1 - Primary Account", "vault_token": os.path.join(VAULT_DIR, "primary", "token.json"), "env_var": "TOKEN_PRIMARY_B64"},
    {"id": "iconjagat", "name": "Shift 2 - iconjagat@gmail.com", "vault_token": os.path.join(VAULT_DIR, "iconjagat", "token.json"), "env_var": "TOKEN_ICONJAGAT_B64"},
    {"id": "ecogainnexus", "name": "Shift 3 - ecogainnexus@gmail.com", "vault_token": os.path.join(VAULT_DIR, "ecogainnexus", "token.json"), "env_var": "TOKEN_ECOGAIN_B64"}
]

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
            "service": "AgenticVerse 24/7 Sovereign Cloud Orchestrator",
            "owner": "Jaggu (AgenticVerse)",
            "status": state.get("status", "running"),
            "active_shift": account_name,
            "running_hours": round(elapsed_hrs, 2),
            "total_rotations": state.get("total_rotations", 0),
            "target_ingress": HEALTH_URL,
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
        try:
            r = requests.get(HEALTH_URL, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=8)
            if r.status_code == 200:
                data = r.json().get("data", [])
                models = [m.get("id") for m in data]
                if "qwen3.8-27b-uncensored" in models or "hybrid-auto" in models:
                    return True
        except Exception:
            pass
        return False

    def deploy_token(self, account_index: int):
        account = ACCOUNTS[account_index]
        src_token = account["vault_token"]
        dest_token = os.path.join(COLAB_CONFIG_DIR, "token.json")

        if not os.path.exists(src_token):
            raise FileNotFoundError(f"Vault token missing for {account['name']} at {src_token}")

        shutil.copyfile(src_token, dest_token)
        logger.info(f"[✓] Active Colab CLI token deployed for: {account['name']}")

    def terminate_current_session(self):
        logger.info("[*] Releasing active Colab cloud sessions...")
        try:
            subprocess.run(["colab", "stop"], capture_output=True, text=True, timeout=30)
        except Exception as e:
            logger.warning(f"Notice stopping session: {e}")

    def launch_shift(self, account_index: int):
        account = ACCOUNTS[account_index]

        logger.info("=" * 65)
        logger.info(f"🚀 PROVISIONING SHIFT: {account['name']}")
        logger.info("=" * 65)

        # 1. Deploy token for target account
        self.deploy_token(account_index)

        # 2. Clean up any existing session on this account
        try:
            subprocess.run(["colab", "stop", "-s", "agenticverse_engine"], capture_output=True, text=True, timeout=20)
        except Exception:
            pass

        # 3. Provision Headless T4 GPU VM
        logger.info("[*] Instantiating Tesla T4 GPU VM on Colab...")
        res = subprocess.run(["colab", "new", "-s", "agenticverse_engine", "--gpu", "T4"], capture_output=True, text=True)
        combined_output = f"{res.stdout.strip()} {res.stderr.strip()}".strip()
        logger.info(f"Colab Provision Status: {combined_output}")

        if res.returncode != 0 or "refused" in combined_output.lower() or "limit" in combined_output.lower():
            logger.warning(f"⚠️ GPU VM provision failed for {account['name']}. Rotating to backup account...")
            time.sleep(5)
            self.rotate_shift(f"GPU Quota/Precondition on {account['name']}")
            return False

        # 4. Upload decoupled server files directly to Colab container
        server_local = os.path.join(SCRIPTS_DIR, "hybrid_server.py")
        payload_local = os.path.join(SCRIPTS_DIR, "colab_payload.py")

        logger.info("[*] Uploading decoupled server files directly to Colab container...")
        subprocess.run(["colab", "upload", "-s", "agenticverse_engine", server_local, "/content/hybrid_server.py"], capture_output=True, text=True)
        subprocess.run(["colab", "upload", "-s", "agenticverse_engine", payload_local, "/content/colab_payload.py"], capture_output=True, text=True)

        # 5. Trigger remote execution via detached launcher script
        launcher_file = os.path.join(BASE_DIR, "launch_payload.py")
        with open(launcher_file, "w", encoding="utf-8") as f:
            f.write("import os\nos.system('nohup python3 /content/colab_payload.py > /content/payload.log 2>&1 &')\n")

        logger.info("[*] Triggering detached setup payload on remote GPU...")
        res_exec = subprocess.run(
            ["colab", "exec", "-s", "agenticverse_engine", "-f", launcher_file],
            capture_output=True, text=True, timeout=60
        )
        logger.info(f"Colab Exec Launcher Result: stdout='{res_exec.stdout.strip()}' stderr='{res_exec.stderr.strip()}'")

        self.state["current_account_index"] = account_index
        self.state["shift_started_at"] = time.time()
        self.state["consecutive_failures"] = 0
        self.state["status"] = "booting"
        save_state(self.state)

        # 4. Wait for warmup
        logger.info("[*] Awaiting model lock into VRAM & Ngrok tunnel activation...")
        warmup_start = time.time()
        poll_step = 0
        while time.time() - warmup_start < 480:
            time.sleep(15)
            poll_step += 1
            if self.probe_health():
                logger.info("=" * 65)
                logger.info(f"🚀 [✓] SHIFT IS ONLINE & RESPONDING TO POCKETSTRIKE!")
                logger.info(f"🌐 Base URL: {HEALTH_URL.replace('/models', '')}")
                logger.info("🔑 API Key:  sk-jaggu")
                logger.info("🧠 Model:    qwen3.8-27b-uncensored")
                logger.info("=" * 65)
                self.state["status"] = "running"
                save_state(self.state)
                return True

            if poll_step % 2 == 0:
                try:
                    read_script = os.path.join(SCRIPTS_DIR, "read_remote_log.py")
                    p_res = subprocess.run(
                        ["colab", "exec", "-s", "agenticverse_engine", "-f", read_script],
                        capture_output=True, text=True, timeout=15
                    )
                    out = p_res.stdout.strip()
                    if out and out != "0":
                        logger.info(f"[Remote GPU Progress]\n{out}")
                except Exception:
                    pass

        logger.warning("[!] Warmup period elapsed; Continuing health supervision.")
        return False

    def rotate_shift(self, reason: str):
        next_index = (self.state["current_account_index"] + 1) % len(ACCOUNTS)
        logger.info("=" * 65)
        logger.info(f"🔄 ROTATION TRIGGERED: {reason}")
        logger.info(f"Current Slot: {self.state['current_account_index']} ➔ Next Slot: {next_index}")
        logger.info("=" * 65)

        self.state["total_rotations"] += 1
        self.launch_shift(next_index)

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
            self.launch_shift(self.state.get("current_account_index", 0))

        while True:
            try:
                time.sleep(HEALTH_CHECK_INTERVAL)
                now = time.time()

                # Preemptive Shift Handover
                elapsed_hrs = (now - self.state.get("shift_started_at", now)) / 3600.0
                if elapsed_hrs >= SHIFT_MAX_HOURS:
                    logger.info(f"⏰ Shift limit reached ({elapsed_hrs:.2f} hrs). Initiating scheduled rotation.")
                    self.rotate_shift("Scheduled 11.5-Hour Handover")
                    continue

                # Health Probing
                if self.probe_health():
                    if self.state["consecutive_failures"] > 0:
                        logger.info("[✓] Gateway health restored!")
                    self.state["consecutive_failures"] = 0
                    self.state["status"] = "running"
                else:
                    self.state["consecutive_failures"] += 1
                    failures = self.state["consecutive_failures"]
                    logger.warning(f"⚠️ Health failure {failures}/{CONSECUTIVE_FAILURES_LIMIT}")

                    if failures >= CONSECUTIVE_FAILURES_LIMIT:
                        logger.error("❌ Health checks failed. Initiating crash recovery failover!")
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
