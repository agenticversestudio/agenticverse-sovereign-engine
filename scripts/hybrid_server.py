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

async def stream_ollama(messages: list):
    url = "http://127.0.0.1:11434/v1/chat/completions"
    payload = {"model": "qwen3.8-27b-uncensored", "messages": messages, "stream": True}
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
                        yield f"{chunk}\n\n"
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

    if stream:
        return StreamingResponse(stream_ollama(messages), media_type="text/event-stream")
    else:
        url = "http://127.0.0.1:11434/v1/chat/completions"
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(url, json={"model": "qwen3.8-27b-uncensored", "messages": messages, "stream": False})
            return JSONResponse(r.json())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
