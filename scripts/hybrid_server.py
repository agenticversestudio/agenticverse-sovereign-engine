import os, sys, time, json, re, asyncio, httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="AgenticVerse Sovereign Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
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
    body = await req.json()
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
