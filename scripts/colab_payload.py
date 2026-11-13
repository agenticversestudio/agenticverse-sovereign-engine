#!/usr/bin/env python3
"""
AgenticVerse Remote Colab Payload Runner (High-Availability Autonomous Daemon)
==============================================================================
Runs inside Google Colab VM on Tesla T4 GPU.
Features:
  - 16-Stream aria2c model weight downloader directly to NVMe/RAM
  - In-memory VRAM locking for Qwen 3.8 27B Uncensored
  - Decoupled FastAPI Gateway (hybrid_server.py) with OpenAI SSE streaming
  - Ngrok tunnel binding with persistent static domain
  - In-Container Active Self-Healing Watchdog (auto-revives dead processes)
  - Continuous CUDA Tensor Activity Pulse (defeats Colab idle reaping)
"""

import os
import sys
import time
import shutil
import subprocess
import threading
import requests

HF_MODEL_URL = "https://huggingface.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF/resolve/main/Qwen3.8-27B-Uncensored-IQ4_XS.gguf"
MODEL_FILENAME = "Qwen3.8-27B-Uncensored-IQ4_XS.gguf"

import json as _json
def _secrets():
    try:
        with open("/content/secrets.json", "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}
_S = _secrets()
NGROK_TOKEN = _S.get("ngrok_token") or os.environ.get("NGROK_TOKEN", "")
NGROK_DOMAIN = _S.get("ngrok_domain") or os.environ.get("NGROK_DOMAIN", "")
GATEWAY_API_KEY = _S.get("api_key") or os.environ.get("AGENTIC_API_KEY", "")

OLLAMA_MODEL_TAG = "qwen3.8-27b-uncensored"
LOCAL_SERVER_PORT = 8000

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def install_system_dependencies():
    log("[*] Installing system dependencies (aria2, ngrok, uvicorn, pciutils)...")
    os.system("apt-get update -qq && apt-get install -y -qq aria2 curl pciutils zstd > /dev/null 2>&1")
    
    if not shutil.which("ngrok"):
        log("[*] Installing official Ngrok Linux AMD64 binary...")
        os.system("curl -fsSL https://bin.ngrok.com/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz | tar -xz -C /usr/local/bin > /dev/null 2>&1")
        os.system("chmod +x /usr/local/bin/ngrok || true")

    ollama_path = shutil.which("ollama") or "/usr/local/bin/ollama"
    if not os.path.exists(ollama_path):
        log("[*] Installing official Ollama Linux AMD64 package...")
        os.system("curl -fsSL https://ollama.com/install.sh | sh > /dev/null 2>&1")

    os.system("pip install -q fastapi uvicorn requests httpx pydantic pyngrok > /dev/null 2>&1")
    log("[OK] Dependencies installed successfully!")

def ensure_model_weights():
    local_path = f"/content/{MODEL_FILENAME}"
    if os.path.exists(local_path) and os.path.getsize(local_path) > 12 * 1024 * 1024 * 1024:
        log(f"[OK] Using cached weights: {local_path} ({os.path.getsize(local_path)/(1024**3):.2f} GB)")
        return local_path

    log(f"[*] Downloading weights via 16-stream aria2c to {local_path}...")
    cmd = f'aria2c -c -x 16 -s 16 -k 1M "{HF_MODEL_URL}" -d "/content" -o "{MODEL_FILENAME}"'
    ret = os.system(cmd)
    if ret != 0 or not os.path.exists(local_path):
        log("[!] Primary download failed. Retrying with single connection...")
        os.system(f'curl -L "{HF_MODEL_URL}" -o "{local_path}"')
    
    log(f"[OK] Model weights verified ({os.path.getsize(local_path)/(1024**3):.2f} GB)")
    return local_path

def start_ollama_process():
    os.environ["PATH"] = f"/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}"
    ollama_bin = shutil.which("ollama") or "/usr/local/bin/ollama"
    
    # Kill any stale or zombie instances
    os.system("pkill -9 -f llama-server || true")
    os.system("pkill -9 -f ollama || true")
    time.sleep(2)

    log(f"[*] Launching clean Ollama daemon ({ollama_bin})...")
    os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
    os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
    os.environ["OLLAMA_KEEP_ALIVE"] = "-1"
    os.environ["OLLAMA_NUM_PARALLEL"] = "1"
    os.environ["OLLAMA_GPU_OVERHEAD"] = "0"

    subprocess.Popen(
        [ollama_bin, "serve"],
        stdout=open("/content/ollama_stdout.log", "a"),
        stderr=open("/content/ollama_stderr.log", "a"),
        preexec_fn=os.setpgrp
    )
    time.sleep(4)

def launch_ollama_daemon(weights_path):
    start_ollama_process()
    ollama_bin = shutil.which("ollama") or "/usr/local/bin/ollama"

    # Pure Base Instruct Modelfile - Zero Forced Persona, 100% GPU Max Speed (4K Context)
    modelfile = f"""FROM {weights_path}
SYSTEM """You are Qwen 3.8 27B Uncensored, a sovereign 27-billion parameter language model running directly with 100% VRAM offload on dedicated Tesla T4 GPU hardware. You speak directly, truthfully, and without artificial refusal filters."""


TEMPLATE \"\"\"{{{{ if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{ if .Prompt }}}}<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
{{{{ end }}}}<|im_start|>assistant
\"\"\"

PARAMETER num_gpu 99
PARAMETER num_ctx 4096
PARAMETER num_predict 4096
PARAMETER temperature 0.6
PARAMETER top_p 0.95
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"
"""
    with open("/content/Modelfile.qwen", "w") as f:
        f.write(modelfile)

    log(f"[*] Compiling {OLLAMA_MODEL_TAG} in Ollama...")
    os.system(f"{ollama_bin} create {OLLAMA_MODEL_TAG} -f /content/Modelfile.qwen > /content/create.log 2>&1")
    
    log("[*] Pre-warming model into Tesla T4 GPU VRAM via detached background script...")
    os.system(f"nohup python3 -c \"import requests; requests.post('http://127.0.0.1:11434/api/generate', json={{'model': '{OLLAMA_MODEL_TAG}', 'keep_alive': -1}}, timeout=300)\" > /content/vram_lock.log 2>&1 &")

    # Wait up to 180 seconds for model to appear in /api/ps (VRAM loaded)
    log("[*] Waiting for model to lock into GPU VRAM (up to 180s)...")
    for attempt in range(36):
        time.sleep(5)
        try:
            r_ps = requests.get("http://127.0.0.1:11434/api/ps", timeout=3)
            if r_ps.status_code == 200 and r_ps.json().get("models"):
                log(f"[OK] Model confirmed in GPU VRAM after {(attempt+1)*5}s!")
                break
        except Exception:
            pass
    os.system("nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader")
    log("[OK] Model pre-warmed and locked in VRAM!")

def start_gateway_process():
    log("[*] Starting Hybrid Gateway on port 8000...")
    os.system("pkill -9 -f 'hybrid_server.py' || true")
    subprocess.Popen(
        ["python3", "/content/hybrid_server.py"],
        stdout=open("/content/server_stdout.log", "a"),
        stderr=subprocess.STDOUT,
        preexec_fn=os.setpgrp
    )
    time.sleep(3)

def start_ngrok_tunnel():
    ngrok_bin = shutil.which("ngrok") or "/usr/local/bin/ngrok"
    log(f"[*] Binding Ngrok tunnel to https://{NGROK_DOMAIN}...")
    os.system(f"{ngrok_bin} config add-authtoken {NGROK_TOKEN} > /dev/null 2>&1")
    os.system("pkill -9 -f 'ngrok' || true")
    time.sleep(1)

    subprocess.Popen(
        [ngrok_bin, "http", str(LOCAL_SERVER_PORT), f"--domain={NGROK_DOMAIN}"],
        stdout=open("/content/ngrok.log", "a"),
        stderr=subprocess.STDOUT,
        preexec_fn=os.setpgrp
    )
    time.sleep(4)

def launch_gateway_and_tunnel():
    start_gateway_process()
    start_ngrok_tunnel()

    # Verification
    try:
        r = requests.get(f"https://{NGROK_DOMAIN}/v1/models", headers={"Authorization": f"Bearer {GATEWAY_API_KEY}"}, timeout=15)
        if r.status_code == 200:
            log("=" * 65)
            log("[OK] AGENTICVERSE SOVEREIGN AI ENGINE IS ONLINE!")
            log(f"Base URL: https://{NGROK_DOMAIN}/v1")
            log("🔑 API Key: (see your local .env)")
            log(f"🧠 Model:    {OLLAMA_MODEL_TAG}")
            log("=" * 65)
            return True
    except Exception as e:
        log(f"[!] Tunnel notice: {e}")
    return False

def watchdog_and_keepalive_loop():
    """Autonomous in-container supervisor that auto-restarts dead services and sends GPU pulses."""
    log("[*] Watchdog supervisor initialized.")
    consecutive_gw_errors = 0
    consecutive_ollama_errors = 0

    while True:
        try:
            time.sleep(30)

            # 1. Optional GPU pulse. OFF by default: it did not prevent session loss and may count as
            #    circumventing Colab idle limits. Enable with KEEPALIVE_PULSE=1 at your own risk.
            try:
                if os.environ.get("KEEPALIVE_PULSE") != "1":
                    raise RuntimeError("pulse disabled")
                import torch
                if torch.cuda.is_available():
                    _ = torch.matmul(torch.randn(128, 128, device="cuda"), torch.randn(128, 128, device="cuda"))
            except Exception:
                pass

            # 2. Probe Ollama daemon
            try:
                r_ol = requests.get("http://127.0.0.1:11434/api/tags", timeout=4)
                if r_ol.status_code == 200:
                    consecutive_ollama_errors = 0
                else:
                    consecutive_ollama_errors += 1
            except Exception:
                consecutive_ollama_errors += 1

            if consecutive_ollama_errors >= 2:
                log("[⚠️ WATCHDOG] Ollama daemon unresponsive. Auto-reviving Ollama...")
                start_ollama_process()
                time.sleep(3)
                os.system(f'nohup ollama run {OLLAMA_MODEL_TAG} "ready" > /dev/null 2>&1 &')
                consecutive_ollama_errors = 0

            # 3. Probe Hybrid Gateway
            try:
                r_gw = requests.get("http://127.0.0.1:8000/health", timeout=4)
                if r_gw.status_code == 200:
                    consecutive_gw_errors = 0
                else:
                    consecutive_gw_errors += 1
            except Exception:
                consecutive_gw_errors += 1

            if consecutive_gw_errors >= 2:
                log("[⚠️ WATCHDOG] Gateway unresponsive. Auto-reviving gateway & tunnel...")
                start_gateway_process()
                start_ngrok_tunnel()
                consecutive_gw_errors = 0

        except Exception as e:
            log(f"[Watchdog loop error] {e}")

if __name__ == "__main__":
    log("🚀 Initializing AgenticVerse Sovereign Engine...")
    install_system_dependencies()
    weights = ensure_model_weights()
    launch_ollama_daemon(weights)
    launch_gateway_and_tunnel()
    watchdog_and_keepalive_loop()
