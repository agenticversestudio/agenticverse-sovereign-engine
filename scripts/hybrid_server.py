import os, sys, time, json, re, asyncio, httpx
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="AgenticVerse Sovereign Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

LOGIN_PASSKEY = "gqd@534$$"
API_PREFIX = "sk-jaggu"

MODELS_LIST = [
    {"id": "qwen3.8-27b-uncensored", "name": "Qwen 3.8 27B Uncensored (Flagship Engine)"},
    {"id": "deepseek-v4.1", "name": "DeepSeek V4.1 (Deep Reasoning Engine)"},
    {"id": "glm-5.3", "name": "GLM 5.3 (Complex Logic Engine)"}
]

def check_authorized(req: Request) -> bool:
    auth = req.headers.get("authorization", "")
    passkey_hdr = req.headers.get("x-passkey", "")

    if passkey_hdr == LOGIN_PASSKEY:
        return True
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token.startswith(API_PREFIX) or token == LOGIN_PASSKEY:
            return True
    return False

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AgenticVerse | Sovereign AI Studio</title>
  <style>
    :root {
      --bg: #090d16;
      --card: #111827;
      --border: #1f2937;
      --accent: #3b82f6;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --green: #10b981;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

    /* Login Lock Screen */
    #lock-modal {
      position: fixed; inset: 0; background: rgba(9, 13, 22, 0.94);
      backdrop-filter: blur(16px); display: flex; align-items: center; justify-content: center; z-index: 100;
    }
    .lock-card {
      background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 32px;
      max-width: 420px; width: 90%; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.6);
    }
    .lock-icon { font-size: 2.5rem; margin-bottom: 12px; }
    .lock-title { font-size: 1.3rem; font-weight: 700; color: #fff; margin-bottom: 6px; }
    .lock-sub { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 24px; line-height: 1.4; }
    .lock-input {
      width: 100%; padding: 12px 16px; border-radius: 12px; background: #1a2234; border: 1px solid var(--border);
      color: #fff; font-size: 1rem; margin-bottom: 16px; outline: none; transition: border-color 0.2s;
    }
    .lock-input:focus { border-color: var(--accent); }
    .lock-btn {
      width: 100%; padding: 12px; border-radius: 12px; background: var(--accent); color: #fff;
      font-size: 1rem; font-weight: 600; border: none; cursor: pointer; transition: 0.2s;
    }
    .lock-btn:hover { background: #2563eb; }
    .lock-err { color: var(--danger); font-size: 0.8rem; margin-top: 10px; display: none; }

    /* App Header */
    header {
      background: rgba(17, 24, 39, 0.85); backdrop-filter: blur(12px); border-bottom: 1px solid var(--border);
      padding: 12px 24px; display: flex; justify-content: space-between; align-items: center;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 10px var(--green); }
    .brand h1 { font-size: 1.15rem; font-weight: 700; background: linear-gradient(135deg, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .controls { display: flex; align-items: center; gap: 12px; }
    select#model-select {
      background: #1a2234; border: 1px solid var(--border); color: #fff; padding: 6px 12px;
      border-radius: 8px; font-size: 0.82rem; outline: none; cursor: pointer;
    }
    .vram-pill { font-size: 0.75rem; color: var(--text-muted); background: rgba(31, 41, 55, 0.6); padding: 4px 10px; border-radius: 9999px; border: 1px solid var(--border); }
    .vram-pill strong { color: var(--green); }

    /* Main Chat */
    main { flex: 1; max-width: 900px; width: 100%; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; height: calc(100vh - 65px); }
    #chat-box { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding: 10px 0; }
    .msg { display: flex; flex-direction: column; max-width: 85%; animation: fadeIn 0.2s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
    .msg.user { align-self: flex-end; }
    .msg.assistant { align-self: flex-start; }
    .bubble { padding: 12px 18px; border-radius: 16px; font-size: 0.95rem; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
    .msg.user .bubble { background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; border-bottom-right-radius: 4px; }
    .msg.assistant .bubble { background: var(--card); border: 1px solid var(--border); color: var(--text); border-bottom-left-radius: 4px; }
    .think-block {
      background: rgba(31, 41, 55, 0.4); border-left: 3px solid #6366f1; padding: 8px 12px;
      border-radius: 4px; font-size: 0.85rem; color: #a5b4fc; margin-bottom: 8px; font-style: italic;
    }

    /* Input Bar */
    .input-bar { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 8px 12px; display: flex; align-items: center; gap: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
    textarea { flex: 1; background: transparent; border: none; color: var(--text); font-size: 0.95rem; resize: none; outline: none; height: 42px; line-height: 1.4; padding: 10px 4px; }
    button#send-btn { background: var(--accent); color: white; border: none; width: 42px; height: 42px; border-radius: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; }
    button#send-btn:hover { background: #2563eb; }
    button#send-btn:disabled { opacity: 0.3; cursor: not-allowed; }
    .footer-note { font-size: 0.72rem; text-align: center; color: var(--text-muted); margin-top: 8px; }
  </style>
</head>
<body>

  <!-- Passkey Lock Barrier -->
  <div id="lock-modal">
    <div class="lock-card">
      <div class="lock-icon">🔒</div>
      <div class="lock-title">AgenticVerse Sovereign Gate</div>
      <div class="lock-sub">Enter Passkey to authenticate Flagship Neural Compute session.</div>
      <input type="password" id="passkey-input" class="lock-input" placeholder="Passkey" autocomplete="off" />
      <button class="lock-btn" onclick="unlockGateway()">Unlock Console</button>
      <div id="lock-err" class="lock-err">Access Denied: Invalid Passkey</div>
    </div>
  </div>

  <header>
    <div class="brand">
      <div class="pulse"></div>
      <h1>AgenticVerse Studio</h1>
    </div>
    <div class="controls">
      <select id="model-select">
        <option value="qwen3.8-27b-uncensored">Qwen 3.8 27B Uncensored (Active)</option>
        <option value="deepseek-v4.1">DeepSeek V4.1</option>
        <option value="glm-5.3">GLM 5.3</option>
      </select>
      <div class="vram-pill" id="vram-stat">VRAM: <strong>Checking...</strong></div>
      <button onclick="logout()" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:0.8rem;">🔒 Lock</button>
    </div>
  </header>

  <main>
    <div id="chat-box">
      <div class="msg assistant">
        <div class="bubble">AgenticVerse Sovereign Engine online. Raw unconstrained compute ready. Send prompt below.</div>
      </div>
    </div>

    <div class="input-bar">
      <textarea id="prompt-input" placeholder="Enter message... (Enter to send, Shift+Enter for newline)" rows="1"></textarea>
      <button id="send-btn" onclick="sendMessage()">➔</button>
    </div>
    <div class="footer-note">Authenticated Neural Session • Direct Stream</div>
  </main>

  <script>
    const lockModal = document.getElementById('lock-modal');
    const passkeyInput = document.getElementById('passkey-input');
    const lockErr = document.getElementById('lock-err');
    const chatBox = document.getElementById('chat-box');
    const promptInput = document.getElementById('prompt-input');
    const sendBtn = document.getElementById('send-btn');
    const modelSelect = document.getElementById('model-select');
    let history = [];

    // Check saved session
    const savedKey = sessionStorage.getItem('agv_auth');
    if (savedKey === 'gqd@534$$') {
      lockModal.style.display = 'none';
      initTelemetry();
    }

    passkeyInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') unlockGateway();
    });

    promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    function unlockGateway() {
      const val = passkeyInput.value.trim();
      if (val === 'gqd@534$$') {
        sessionStorage.setItem('agv_auth', val);
        lockModal.style.display = 'none';
        initTelemetry();
      } else {
        lockErr.style.display = 'block';
      }
    }

    function logout() {
      sessionStorage.removeItem('agv_auth');
      location.reload();
    }

    async function initTelemetry() {
      try {
        const res = await fetch('/ps', { headers: { 'x-passkey': sessionStorage.getItem('agv_auth') || '' } });
        if (res.ok) {
          const d = await res.json();
          if (d.gpu_telemetry) {
            document.getElementById('vram-stat').innerHTML = 'VRAM: <strong>' + d.gpu_telemetry.split(',')[1].trim() + '</strong>';
          }
        }
      } catch(e) {}
    }
    setInterval(initTelemetry, 15000);

    async function sendMessage() {
      const text = promptInput.value.trim();
      if (!text) return;

      const auth = sessionStorage.getItem('agv_auth');
      if (!auth) {
        lockModal.style.display = 'flex';
        return;
      }

      promptInput.value = '';
      sendBtn.disabled = true;

      appendMsg('user', text);
      history.push({ role: 'user', content: text });

      const assistantBubble = appendMsg('assistant', '');
      let fullReply = '';

      try {
        const response = await fetch('/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + auth
          },
          body: JSON.stringify({
            model: modelSelect.value,
            messages: history,
            stream: true
          })
        });

        if (response.status === 401) {
          assistantBubble.innerText = '[401 Unauthorized: Invalid Passkey]';
          logout();
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\\n');

          for (const line of lines) {
            if (line.startsWith('data: ') && line !== 'data: [DONE]') {
              try {
                const data = JSON.parse(line.substring(6));
                const delta = data.choices[0]?.delta?.content || '';
                fullReply += delta;
                assistantBubble.innerText = fullReply;
                chatBox.scrollTop = chatBox.scrollHeight;
              } catch(e) {}
            }
          }
        }
        history.push({ role: 'assistant', content: fullReply });
      } catch(err) {
        assistantBubble.innerText = '[Stream error: ' + err.message + ']';
      } finally {
        sendBtn.disabled = false;
        promptInput.focus();
      }
    }

    function appendMsg(role, text) {
      const msgDiv = document.createElement('div');
      msgDiv.className = 'msg ' + role;
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.innerText = text;
      msgDiv.appendChild(bubble);
      chatBox.appendChild(msgDiv);
      chatBox.scrollTop = chatBox.scrollHeight;
      return bubble;
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index_ui():
    return HTML_UI

@app.get("/health")
def health():
    return {"status": "healthy", "service": "AgenticVerse Sovereign Gateway"}

@app.get("/ps")
def process_status(req: Request):
    if not check_authorized(req):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    import subprocess
    res_ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
    res_gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.free,utilization.gpu", "--format=csv,noheader"], capture_output=True, text=True)
    return {
        "status": "online",
        "gpu_telemetry": res_gpu.stdout.strip(),
        "ollama_ps": res_ps.stdout.strip()
    }

@app.get("/v1/models")
@app.get("/models")
def list_models(req: Request):
    now = int(time.time())
    return {
        "object": "list",
        "data": [{
            "id": m["id"], "object": "model", "created": now, "owned_by": "agenticverse",
            "root": m["id"], "parent": None,
            "permission": [{
                "id": f"modelperm-{m['id']}", "object": "model_permission", "created": now,
                "allow_create_engine": False, "allow_sampling": True, "allow_logprobs": True,
                "allow_search_indices": False, "allow_view": True, "allow_fine_tuning": False,
                "organization": "*", "group": None, "is_blocking": False
            }]
        } for m in MODELS_LIST]
    }

async def stream_ollama(model: str, messages: list, temperature: float = 0.6, max_tokens: int = None):
    url = "http://127.0.0.1:11434/v1/chat/completions"
    payload = {"model": model, "messages": messages, "stream": True, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                async for chunk in response.aiter_lines():
                    if chunk:
                        yield f"{chunk}\n\n"
    except Exception as e:
        err = {"error": {"message": str(e), "type": "gateway_error"}}
        yield f"data: {json.dumps(err)}\n\n"
        yield "data: [DONE]\n\n"

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def completions(req: Request):
    if not check_authorized(req):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized: Access Key Required")

    try:
        body = await req.json()
    except Exception:
        body = {}

    model = body.get("model", "qwen3.8-27b-uncensored")
    messages = body.get("messages", [])
    stream = body.get("stream", True)
    temp = float(body.get("temperature", 0.6))
    max_tok = body.get("max_tokens")

    if stream:
        return StreamingResponse(
            stream_ollama(model=model, messages=messages, temperature=temp, max_tokens=max_tok),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        url = "http://127.0.0.1:11434/v1/chat/completions"
        payload = {"model": model, "messages": messages, "stream": False, "temperature": temp}
        if max_tok:
            payload["max_tokens"] = max_tok
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(url, json=payload)
            return JSONResponse(r.json())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
