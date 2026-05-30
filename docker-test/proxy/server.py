"""
PMC Test Harness — Proxy Server
================================
Two containers, each with Claude Code + FastAPI codebase:

  Container A (pmc):  Claude Code → PMC proxy (compression) → DeepSeek
  Container B (raw):  Claude Code → Raw proxy (passthrough)  → DeepSeek

Each container has its OWN copy of the FastAPI codebase.
Claude Code runs inside the container, reads files, sends through proxy.
"""

import os, time, json, httpx, logging, subprocess, tempfile
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from stats import TokenBudgetTracker

PROXY_TYPE = os.environ.get("PROXY_TYPE", "raw")
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "https://api.deepseek.com/anthropic")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")
SOURCE_ROOT = os.environ.get("SOURCE_ROOT", "/app/codebase")

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
log = logging.getLogger(f"proxy-{PROXY_TYPE}")

# PMC Engine (only for pmc container)
pmc_engine = None
pmc_indexed = False
if PROXY_TYPE == "pmc":
    try:
        import sys; sys.path.insert(0, "/app")
        from pmc import PMCEngine, PMCConfig
        cfg = PMCConfig(); cfg.mode = "balanced"; cfg._apply_mode()
        pmc_engine = PMCEngine(config=cfg)
    except Exception as e:
        log.warning(f"PMC init: {e}")

app = FastAPI(title=f"PMC — {PROXY_TYPE.upper()}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
tracker = TokenBudgetTracker(budget=99999999, name=f"{PROXY_TYPE.upper()} Proxy")
client = httpx.AsyncClient(timeout=300.0)

def read_codebase(root: str) -> str:
    if not root or not os.path.isdir(root): return ""
    parts = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "__"))]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, root)
                try:
                    parts.append(f"# FILE: {rel}\n{open(fp, encoding='utf-8').read()}")
                except: pass
    return "\n\n".join(parts)


@app.post("/test")
async def run_test(request: Request):
    """
    Run a real Claude Code fix on the FastAPI codebase.

    1. Receives a query (e.g. "Fix the bug in login")
    2. Container A (PMC): reads codebase → PMC compresses → sends to DeepSeek
    3. Container B (RAW): reads codebase → sends ALL files to DeepSeek
    4. Gets actual AI fix back
    5. Returns fix + token counts
    """
    body = await request.json()
    api_key = body.get("api_key", os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))
    if not api_key:
        return JSONResponse(400, content={"error": "API key required"})

    query = body.get("query", "")
    difficulty = body.get("difficulty", "unknown")
    max_tokens = body.get("max_tokens", 4096)

    if not query:
        return JSONResponse(400, content={"error": "Query required"})

    # Read the codebase
    raw_files = read_codebase(SOURCE_ROOT)
    naive_estimate = max(1, len(raw_files) // 4)

    # ── Build context ──
    if PROXY_TYPE == "pmc" and pmc_engine and pmc_indexed:
        try:
            comp = pmc_engine.compress(query, source_root=SOURCE_ROOT)
            system_prompt = comp.context_string
            naive = comp.naive_token_count
            reduction = comp.reduction_pct
            log.info(f"PMC: {naive:,} → {comp.token_count:,} tokens ({reduction}% reduction)")
        except Exception as e:
            log.warning(f"PMC fallback: {e}")
            system_prompt = raw_files
            naive = naive_estimate
            reduction = 0.0
    else:
        system_prompt = raw_files
        naive = naive_estimate
        reduction = 0.0

    # ── Forward to DeepSeek ──
    api_body = {
        "model": "deepseek-v4-flash",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": query}],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    upstream_start = time.time()
    try:
        resp = await client.post(f"{UPSTREAM_URL}/v1/messages", json=api_body, headers=headers, timeout=300.0)
        elapsed = round(time.time() - upstream_start, 1)
    except Exception as e:
        return JSONResponse(502, content={"error": str(e), "type": PROXY_TYPE})

    try:
        resp_data = resp.json()
    except:
        return JSONResponse(502, content={"error": "Bad upstream response", "type": PROXY_TYPE})

    usage = resp_data.get("usage", {})
    upstream_input = usage.get("input_tokens", tracker.estimated_input_tokens(json.dumps(api_body)))
    upstream_output = usage.get("output_tokens", len(json.dumps(resp_data)) // 4)

    # Extract AI response text
    response_text = ""
    for block in resp_data.get("content", []):
        if block.get("type") == "text":
            response_text = block.get("text", "")
            break

    # Track
    total_tokens = upstream_input + upstream_output
    tracker.track_request(
        query=f"[{difficulty}] {query[:60]}",
        input_tokens=upstream_input,
        output_tokens=upstream_output,
        naive_tokens=naive,
        reduction_pct=reduction,
    )

    return {
        "status": "ok",
        "type": PROXY_TYPE,
        "difficulty": difficulty,
        "query": query[:120],
        "tokens_used": total_tokens,
        "tokens_input": upstream_input,
        "tokens_output": upstream_output,
        "naive_tokens": naive,
        "reduction_pct": round(reduction, 1),
        "elapsed_seconds": elapsed,
        "budget_remaining": 99999999,
        "response": response_text,
    }


@app.get("/health")
async def health():
    return {"status":"ok","type":PROXY_TYPE,"requests":tracker.request_count,"indexed":pmc_indexed}

@app.get("/stats")
async def stats(): return tracker.stats()

@app.post("/reset")
async def reset(): tracker.reset(); return {"status":"reset"}

@app.post("/index")
async def index():
    global pmc_indexed
    if not pmc_engine: return JSONResponse(400, content={"error":"PMC not available"})
    if not os.path.isdir(SOURCE_ROOT): return JSONResponse(400, content={"error":f"Not found: {SOURCE_ROOT}"})
    try:
        s = pmc_engine.index(SOURCE_ROOT); pmc_indexed = True
        return {"status":"indexed","stats":s}
    except Exception as e:
        return JSONResponse(500, content={"error":str(e)})

@app.on_event("shutdown")
async def shutdown(): await client.aclose()
