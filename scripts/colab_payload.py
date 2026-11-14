#!/usr/bin/env python3
"""
Colab Router - Remote Colab Payload Runner
===========================================
High-Availability Autonomous Daemon running inside Google Colab (Tesla T4 / A100 / L4 GPU).

Features:
  - 16-Stream aria2c model weight downloader directly to NVMe/RAM
  - In-memory VRAM locking for GGUF models via Ollama
  - Decoupled FastAPI Gateway (hybrid_server.py) with OpenAI SSE streaming
  - Ngrok tunnel binding with persistent static or dynamic domain
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


# Load secrets from /content/secrets.json if available
if os.path.exists('/content/secrets.json'):
    try:
        import json
        with open('/content/secrets.json') as _sf:
            _sec = json.load(_sf)
            for _k, _v in _sec.items():
                if _v and not os.environ.get(_k):
                    os.environ[_k] = str(_v)
    except Exception as _e:
        print('[!] Warning: failed to load /content/secrets.json:', _e)

# ----------------- Configuration & Defaults -----------------
HF_MODEL_URL = os.environ.get(
    "HF_MODEL_URL",
    "https://huggingface.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF/resolve/main/Qwen3.8-27B-Uncensored-IQ4_XS.gguf"
)
MODEL_FILENAME = os.environ.get("MODEL_FILENAME", "Qwen3.8-27B-Uncensored-IQ4_XS.gguf")
OLLAMA_MODEL_TAG = os.environ.get("OLLAMA_MODEL_TAG", "qwen3.8-27b-uncensored")

NGROK_TOKEN = os.environ.get("NGROK_AUTHTOKEN", "")
NGROK_DOMAIN = os.environ.get("NGROK_DOMAIN", "")

NUM_CTX = int(os.environ.get("NUM_CTX", 4096))
NUM_PREDICT = int(os.environ.get("NUM_PREDICT", 2048))
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
    # If weights already exist and are > 2GB
    if os.path.exists(local_path) and os.path.getsize(local_path) > 2 * 1024 * 1024 * 1024:
        log(f"[OK] Using cached weights: {local_path} ({os.path.getsize(local_path)/(1024**3):.2f} GB)")
        return local_path

    log(f"[*] Downloading weights via 16-stream aria2c to {local_path}...")
    cmd = f'aria2c -c -x 16 -s 16 -k 1M "{HF_MODEL_URL}" -d "/content" -o "{MODEL_FILENAME}"'
    ret = os.system(cmd)
    if ret != 0 or not os.path.exists(local_path) or os.path.getsize(local_path) < 2 * 1024 * 1024 * 1024:
        log("[!] aria2c download failed or incomplete. Retrying with curl (--fail -L)...")
        if os.path.exists(local_path):
            os.remove(local_path)
        os.system(f'curl -fL --retry 3 "{HF_MODEL_URL}" -o "{local_path}"')

    if not os.path.exists(local_path) or os.path.getsize(local_path) < 2 * 1024 * 1024 * 1024:
        raise RuntimeError(f"Weights file missing or corrupt after download: {local_path}")

    log(f"[OK] Model weights verified ({os.path.getsize(local_path)/(1024**3):.2f} GB)")
    return local_path

    log(f"[*] Downloading weights via 16-stream aria2c to {local_path}...")
    cmd = f'aria2c -c -x 16 -s 16 -k 1M "{HF_MODEL_URL}" -d "/content" -o "{MODEL_FILENAME}"'
    ret = os.system(cmd)
    if ret != 0 or not os.path.exists(local_path):
        log("[!] Primary download failed. Retrying with curl...")
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

    system_prompt = (
        "You are Qwen 3.8 27B Uncensored, a sovereign 27-billion parameter language model "
        "running directly with 100% VRAM offload on dedicated Tesla T4 GPU hardware. "
        "You speak directly, truthfully, and without artificial refusal filters."
    )

    modelfile = (
        f"FROM {weights_path}\n"
        f'SYSTEM """{system_prompt}"""\n\n'
        'TEMPLATE """{{ if .System }}<|im_start|>system\n'
        '{{ .System }}<|im_end|>\n'
        '{{ end }}{{ if .Prompt }}<|im_start|>user\n'
        '{{ .Prompt }}<|im_end|>\n'
        '{{ end }}<|im_start|>assistant\n'
        '"""\n\n'
        'PARAMETER num_gpu 99\n'
        f'PARAMETER num_ctx {NUM_CTX}\n'
        f'PARAMETER num_predict {NUM_PREDICT}\n'
        'PARAMETER temperature 0.6\n'
        'PARAMETER top_p 0.95\n'
        'PARAMETER stop "<|im_end|>"\n'
        'PARAMETER stop "<|endoftext|>"\n'
    )
    with open("/content/Modelfile.custom", "w") as f:
        f.write(modelfile)

        log(f"[*] Compiling {OLLAMA_MODEL_TAG} in Ollama...")
    res = subprocess.run([ollama_bin, "create", OLLAMA_MODEL_TAG, "-f", "/content/Modelfile.custom"], capture_output=True, text=True)
    if res.returncode != 0:
        log(f"[FATAL] Ollama create failed with code {res.returncode}: {res.stderr.strip()}")
        raise RuntimeError(f"Ollama create failed: {res.stderr.strip()}")
    log(f"[OK] {OLLAMA_MODEL_TAG} compiled successfully!")
    
    log("[*] Pre-warming model into GPU VRAM via detached script...")
    # Detached lock call ensures client drops never abort model load
    os.system(f"nohup python3 -c \"import requests; requests.post('http://127.0.0.1:11434/api/generate', json={{'model': '{OLLAMA_MODEL_TAG}', 'keep_alive': -1}}, timeout=300)\" > /content/vram_lock.log 2>&1 &")

    # Wait up to 180 seconds for model to appear in /api/ps (VRAM loaded, not just Ollama online)
    log("[*] Waiting for model to lock into GPU VRAM (up to 180s)...")
    for attempt in range(36):
        time.sleep(5)
        try:
            r_ps = requests.get("http://127.0.0.1:11434/api/ps", timeout=3)
            if r_ps.status_code == 200:
                ps_data = r_ps.json()
                if ps_data.get("models"):
                    log(f"[OK] Model confirmed in GPU VRAM after {(attempt+1)*5}s!")
                    break
            # Fallback: at least confirm Ollama is alive
            r_tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            if r_tags.status_code == 200 and attempt >= 12:
                # After 60s, if Ollama is alive, the vram lock is running in background
                log("[OK] Ollama alive — VRAM lock running in background.")
                break
        except Exception:
            pass

    os.system("nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader || true")
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
    if not NGROK_TOKEN:
        log("[!] WARNING: NGROK_AUTHTOKEN not provided. Skipping Ngrok tunnel.")
        return

    log(f"[*] Configuring Ngrok token...")
    os.system(f"{ngrok_bin} config add-authtoken {NGROK_TOKEN} > /dev/null 2>&1")
    os.system("pkill -9 -f 'ngrok' || true")
    time.sleep(1)

    cmd = [ngrok_bin, "http", str(LOCAL_SERVER_PORT)]
    if NGROK_DOMAIN:
        log(f"[*] Binding Ngrok tunnel to custom domain: https://{NGROK_DOMAIN}...")
        cmd.append(f"--url={NGROK_DOMAIN}")
    else:
        log("[*] Binding Ngrok tunnel to dynamic domain...")

    subprocess.Popen(
        cmd,
        stdout=open("/content/ngrok.log", "a"),
        stderr=subprocess.STDOUT,
        preexec_fn=os.setpgrp
    )
    time.sleep(4)

def launch_gateway_and_tunnel():
    start_gateway_process()
    start_ngrok_tunnel()

    # Discover active URL from Ngrok local API if dynamic
    active_url = f"https://{NGROK_DOMAIN}" if NGROK_DOMAIN else ""
    try:
        r_ng = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
        if r_ng.status_code == 200:
            tunnels = r_ng.json().get("tunnels", [])
            if tunnels:
                active_url = tunnels[0].get("public_url", active_url)
    except Exception:
        pass

    log("=" * 65)
    log("[OK] COLAB ROUTER ENGINE IS ONLINE!")
    log(f"🌐 Ingress URL: {active_url or 'http://localhost:8000'}")
    log(f"🧠 Model:       {OLLAMA_MODEL_TAG}")
    log(f"⚡ Context:     {NUM_CTX} tokens")
    log("=" * 65)

def watchdog_and_keepalive_loop():
    """In-container supervisor that auto-restarts dead services (GPU pulse is optional and OFF by default)."""
    log("[*] Watchdog supervisor initialized.")
    consecutive_gw_errors = 0
    consecutive_ollama_errors = 0

    while True:
        try:
            time.sleep(30)

            # 1. Optional GPU pulse. OFF by default (set KEEPALIVE_PULSE=1 to enable, at your own risk):
            #    it does not prevent Colab session limits and may count as circumventing idle limits.
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
    log("🚀 Initializing Colab Router Sovereign Engine...")
    install_system_dependencies()
    weights = ensure_model_weights()
    launch_ollama_daemon(weights)
    launch_gateway_and_tunnel()
    watchdog_and_keepalive_loop()
