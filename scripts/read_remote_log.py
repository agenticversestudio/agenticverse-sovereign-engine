import os

log_files = [
    ("/content/payload.log", "PAYLOAD PROGRESS"),
    ("/content/ngrok.log", "NGROK LOG"),
    ("/content/server_stdout.log", "HYBRID SERVER LOG"),
    ("/content/ollama_stderr.log", "OLLAMA LOG")
]

for path, title in log_files:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                last_lines = "".join(lines[-8:]).strip()
                print(f"--- {title} ---")
                print(last_lines)
        except Exception:
            pass
