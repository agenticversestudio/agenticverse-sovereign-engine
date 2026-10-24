import os, sys, time, json, re, asyncio, httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="AgenticVerse Sovereign Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AgenticVerse | Sovereign AI Studio</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --border: #1f2937;
      --accent: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.4);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --green: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
    header { background: rgba(17, 24, 39, 0.85); backdrop-filter: blur(12px); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 10; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; background: linear-gradient(135deg, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .badge { font-size: 0.72rem; padding: 3px 8px; border-radius: 9999px; background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.3); display: flex; align-items: center; gap: 5px; }
    .pulse { width: 6px; height: 6px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px var(--green); animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
    .telemetry { display: flex; gap: 16px; font-size: 0.8rem; color: var(--text-muted); }
    .telemetry-item strong { color: var(--text); font-weight: 600; }
    main { flex: 1; max-width: 900px; width: 100%; margin: 0 auto; padding: 20px; display: flex; flex-direction: column; height: calc(100vh - 65px); }
    #chat-container { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding: 10px 0; }
    .msg { display: flex; flex-direction: column; max-width: 85%; animation: fadeIn 0.25s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    .msg.user { align-self: flex-end; align-items: flex-end; }
    .msg.assistant { align-self: flex-start; align-items: flex-start; }
    .bubble { padding: 12px 18px; border-radius: 16px; font-size: 0.95rem; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
    .msg.user .bubble { background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; border-bottom-right-radius: 4px; }
    .msg.assistant .bubble { background: var(--card-bg); border: 1px solid var(--border); color: var(--text); border-bottom-left-radius: 4px; box-shadow: 0 4px 14px rgba(0,0,0,0.25); }
    .meta { font-size: 0.72rem; color: var(--text-muted); margin-top: 4px; padding: 0 4px; }
    .pills { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .pill { font-size: 0.8rem; padding: 6px 12px; border-radius: 9999px; background: rgba(31, 41, 55, 0.6); border: 1px solid var(--border); color: var(--text-muted); cursor: pointer; transition: all 0.2s; }
    .pill:hover { background: var(--accent); color: white; border-color: var(--accent); }
    .input-bar { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 8px 12px; display: flex; align-items: center; gap: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.35); }
    textarea { flex: 1; background: transparent; border: none; color: var(--text); font-size: 0.95rem; resize: none; outline: none; height: 42px; line-height: 1.4; padding: 10px 4px; }
    button#send-btn { background: var(--accent); color: white; border: none; width: 42px; height: 42px; border-radius: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; transition: all 0.2s; }
    button#send-btn:hover { background: #2563eb; transform: scale(1.05); }
    button#send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .footer-api { font-size: 0.75rem; text-align: center; color: var(--text-muted); margin-top: 10px; display: flex; justify-content: center; gap: 16px; }
    .footer-api code { background: rgba(31, 41, 55, 0.8); padding: 2px 6px; border-radius: 4px; color: #93c5fd; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="pulse"></div>
      <h1>AgenticVerse Sovereign Hub</h1>
      <span class="badge">Tesla T4 16GB VRAM</span>
    </div>
    <div class="telemetry">
      <div class="telemetry-item">Model: <strong>Qwen 3.8 27B Uncensored</strong></div>
      <div class="telemetry-item" id="vram-stat">VRAM: <strong>Checking...</strong></div>
    </div>
  </header>

  <main>
    <div id="chat-container">
      <div class="msg assistant">
        <div class="bubble">Namaste Jaggu! 🙏 Sovereign AI Engine live hai aur poora 27B model Tesla T4 GPU me locked hai. Koi bhi question puchiye, prompt likhiye ya coding exploit request karein — zero censorship, pure power. 🔥</div>
        <div class="meta">AgenticVerse Engine • 100% Ablated</div>
      </div>
    </div>

    <div class="pills">
      <div class="pill" onclick="sendQuick('Namaste Jaggu! Confirm you are running 100% online in Hinglish.')">🙏 Quick Health Check</div>
      <div class="pill" onclick="sendQuick('Write a high-speed Python script to monitor GPU memory every 5 seconds.')">⚡ Python Script</div>
      <div class="pill" onclick="sendQuick('Explain why sovereign AI is crucial for independence in 2 sentences.')">🧠 Sovereign AI Thesis</div>
    </div>

    <div class="input-bar">
      <textarea id="prompt-input" placeholder="Type your prompt here... (Shift+Enter for newline, Enter to send)" rows="1"></textarea>
      <button id="send-btn" onclick="submitMessage()">➔</button>
    </div>

    <div class="footer-api">
      <span>API Endpoint: <code>https://eel-feminine-progeny.ngrok-free.dev/v1</code></span>
      <span>Key: <code>sk-jaggu</code></span>
      <span>Client: PocketStrike / OpenAI Compatible</span>
    </div>
  </main>

  <script>
    const chatContainer = document.getElementById('chat-container');
    const promptInput = document.getElementById('prompt-input');
    const sendBtn = document.getElementById('send-btn');
    let history = [];

    // Periodic telemetry probe
    async function updateTelemetry() {
      try {
        const res = await fetch('/ps');
        if (res.ok) {
          const d = await res.json();
          if (d.gpu_telemetry) {
            document.getElementById('vram-stat').innerHTML = 'GPU: <strong>' + d.gpu_telemetry.split(',')[1].trim() + '</strong>';
          }
        }
      } catch(e) {}
    }
    updateTelemetry();
    setInterval(updateTelemetry, 10000);

    promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitMessage();
      }
    });

    function sendQuick(txt) {
      promptInput.value = txt;
      submitMessage();
    }

    async function submitMessage() {
      const text = promptInput.value.trim();
      if (!text) return;

      promptInput.value = '';
      sendBtn.disabled = true;

      // Add user bubble
      appendMessage('user', text);
      history.push({ role: 'user', content: text });

      // Create assistant placeholder
      const assistantBubble = appendMessage('assistant', '');
      const metaDiv = assistantBubble.parentElement.querySelector('.meta');
      metaDiv.innerText = 'Streaming tokens...';

      try {
        const response = await fetch('/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer sk-jaggu'
          },
          body: JSON.stringify({
            model: 'qwen3.8-27b-uncensored',
            messages: history,
            stream: true
          })
        });

        if (!response.ok) {
          assistantBubble.innerText = '[Error: HTTP ' + response.status + ' - Gateway notice]';
          sendBtn.disabled = false;
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullReply = '';

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
                chatContainer.scrollTop = chatContainer.scrollHeight;
              } catch(e) {}
            }
          }
        }

        history.push({ role: 'assistant', content: fullReply });
        metaDiv.innerText = 'AgenticVerse Engine • Verified Stream';
      } catch(err) {
        assistantBubble.innerText = '[Connection error: ' + err.message + ']';
      } finally {
        sendBtn.disabled = false;
        promptInput.focus();
      }
    }

    function appendMessage(role, text) {
      const msgDiv = document.createElement('div');
      msgDiv.className = 'msg ' + role;
      
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.innerText = text;

      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.innerText = role === 'user' ? 'You' : 'AgenticVerse Engine';

      msgDiv.appendChild(bubble);
      msgDiv.appendChild(meta);
      chatContainer.appendChild(msgDiv);
      chatContainer.scrollTop = chatContainer.scrollHeight;
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
    return {"status": "healthy", "service": "AgenticVerse Sovereign AI Gateway", "owner": "Jaggu"}

@app.get("/ps")
def process_status():
    import subprocess
    res_ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
    res_gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.free,utilization.gpu", "--format=csv,noheader"], capture_output=True, text=True)
    return {
        "status": "online",
        "active_model": "qwen3.8-27b-uncensored",
        "gpu_telemetry": res_gpu.stdout.strip(),
        "ollama_ps": res_ps.stdout.strip()
    }

@app.get("/v1/models")
@app.get("/models")
def list_models():
    now = int(time.time())
    models = ["qwen3.8-27b-uncensored", "glm-5.3", "deepseek-v4.1", "hybrid-auto"]
    return {
        "object": "list",
        "data": [{
            "id": m, "object": "model", "created": now, "owned_by": "agenticverse",
            "root": m, "parent": None,
            "permission": [{
                "id": f"modelperm-{m}", "object": "model_permission", "created": now,
                "allow_create_engine": False, "allow_sampling": True, "allow_logprobs": True,
                "allow_search_indices": False, "allow_view": True, "allow_fine_tuning": False,
                "organization": "*", "group": None, "is_blocking": False
            }]
        } for m in models]
    }

async def stream_ollama(messages: list, temperature: float = 0.6, max_tokens: int = None):
    url = "http://127.0.0.1:11434/v1/chat/completions"
    payload = {"model": "qwen3.8-27b-uncensored", "messages": messages, "stream": True, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens

    chunk_id = f"chatcmpl-{int(time.time()*1000)}"
    created = int(time.time())

    init_chunk = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": "qwen3.8-27b-uncensored",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
    }
    yield f"data: {json.dumps(init_chunk)}\n\n"

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                async for chunk in response.aiter_lines():
                    if not chunk: continue
                    if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                        try:
                            d = json.loads(chunk[6:])
                            choices = d.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield f"{chunk}\n\n"
                        except Exception:
                            pass
                    elif chunk.startswith("data: [DONE]"):
                        pass
    except Exception as e:
        err_chunk = {"id": chunk_id, "object": "chat.completion.chunk", "created": created, "model": "qwen3.8-27b-uncensored", "choices": [{"index": 0, "delta": {"content": f"\n[Error: {e}]"}, "finish_reason": "error"}]}
        yield f"data: {json.dumps(err_chunk)}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def completions(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    messages = body.get("messages", [])
    stream = body.get("stream", True)
    temp = float(body.get("temperature", 0.6))
    max_tok = body.get("max_tokens")

    if stream:
        return StreamingResponse(
            stream_ollama(messages, temperature=temp, max_tokens=max_tok),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        url = "http://127.0.0.1:11434/v1/chat/completions"
        payload = {"model": "qwen3.8-27b-uncensored", "messages": messages, "stream": False, "temperature": temp}
        if max_tok:
            payload["max_tokens"] = max_tok
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(url, json=payload)
            return JSONResponse(r.json())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
