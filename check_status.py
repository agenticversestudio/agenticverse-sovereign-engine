import os
import sys
import json
import time
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
HEALTH_URL = "https://eel-feminine-progeny.ngrok-free.dev/v1/models"
API_KEY = "sk-jaggu"

def print_status():
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    accounts = [
        "Shift 1 - Primary Account",
        "Shift 2 - iconjagat@gmail.com",
        "Shift 3 - ecogainnexus@gmail.com"
    ]

    curr_idx = state.get("current_account_index", 0)
    active_account = accounts[curr_idx] if curr_idx < len(accounts) else "Unknown"

    started = state.get("shift_started_at", 0)
    elapsed_hrs = (time.time() - started) / 3600.0 if started > 0 else 0.0

    print("=" * 65)
    print("🌌  AGENTICVERSE 24/7 SOVEREIGN ENGINE - LIVE HUD")
    print("=" * 65)
    print(f"📌 Active Slot:           {active_account}")
    print(f"⏱️  Shift Running Time:    {elapsed_hrs:.2f} hours (Max: 11.50 hrs)")
    print(f"🔄 Total Rotations Done:  {state.get('total_rotations', 0)}")
    print(f"⚠️  Consecutive Failures: {state.get('consecutive_failures', 0)}")
    print(f"🌐 Ingress Gateway:       {HEALTH_URL}")

    # Live check
    try:
        t0 = time.time()
        r = requests.get(HEALTH_URL, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=8)
        lat = (time.time() - t0) * 1000
        if r.status_code == 200:
            print(f"⚡ Engine Health:         ONLINE (HTTP 200, Latency: {lat:.0f}ms)")
            models = [m.get("id") for m in r.json().get("data", [])]
            print(f"🧠 Active Muscle:         {', '.join(models)}")
        else:
            print(f"⚡ Engine Health:         STANDBY (HTTP {r.status_code})")
    except Exception as e:
        print(f"⚡ Engine Health:         DISCONNECTED ({e})")
    print("=" * 65)

if __name__ == "__main__":
    print_status()
