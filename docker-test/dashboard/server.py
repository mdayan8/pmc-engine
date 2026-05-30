"""
PMC Dashboard — Backend
========================
Routes test requests to both proxy containers.
"""

import os, asyncio, httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

PMC_PROXY_URL = os.environ.get("PMC_PROXY_URL", "http://pmc-proxy:80")
RAW_PROXY_URL = os.environ.get("RAW_PROXY_URL", "http://raw-proxy:80")

app = FastAPI(title="PMC Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
client = httpx.AsyncClient(timeout=600.0)

@app.post("/api/run-test")
async def run_test(request: Request):
    """Run a single query on BOTH proxies. Returns PMC and RAW results."""
    body = await request.json()
    api_key = body.get("api_key", "")
    query = body.get("query", "")
    difficulty = body.get("difficulty", "unknown")
    max_tokens = body.get("max_tokens", 2048)

    results = {"pmc": [], "raw": [], "errors": []}

    # PMC
    try:
        pmc_resp = await client.post(
            f"{PMC_PROXY_URL}/test",
            json={"api_key": api_key, "query": query, "difficulty": difficulty, "max_tokens": max_tokens},
            timeout=300.0,
        )
        results["pmc"].append(pmc_resp.json() if pmc_resp.status_code == 200 else {"status":"error","error":f"HTTP {pmc_resp.status_code}"})
    except Exception as e:
        results["pmc"].append({"status":"error","error":str(e)})

    # RAW
    try:
        raw_resp = await client.post(
            f"{RAW_PROXY_URL}/test",
            json={"api_key": api_key, "query": query, "difficulty": difficulty, "max_tokens": max_tokens},
            timeout=300.0,
        )
        results["raw"].append(raw_resp.json() if raw_resp.status_code == 200 else {"status":"error","error":f"HTTP {raw_resp.status_code}"})
    except Exception as e:
        results["raw"].append({"status":"error","error":str(e)})

    return results

@app.get("/api/compare")
async def compare():
    """Fetch stats from both proxies."""
    results = {}
    for name, url in [("pmc", PMC_PROXY_URL), ("raw", RAW_PROXY_URL)]:
        try:
            resp = await client.get(f"{url}/stats", timeout=5)
            results[name] = resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results

@app.post("/api/reset")
async def reset_all():
    """Reset both proxy trackers."""
    for url in [PMC_PROXY_URL, RAW_PROXY_URL]:
        try: await client.post(f"{url}/reset", timeout=5)
        except: pass
    return {"status":"reset"}

@app.get("/api/queries")
async def get_queries():
    return [
        {"id":"easy","difficulty":"easy","query":"Add a None check for the func parameter in BackgroundTasks.add_task. If func is None, raise a ValueError with a clear error message.","max_tokens":1024},
        {"id":"medium","difficulty":"medium","query":"Fix the nested 'app' function name clash in request_response in routing.py. The inner 'async def app' shadows the outer 'async def app' at line 110. Rename the inner one to 'inner_app'.","max_tokens":1536},
        {"id":"hard","difficulty":"hard","query":"Add middleware ordering validation to FastAPI.__init__ in applications.py. Create _validate_middleware_order that checks if CORSMiddleware is placed before other middleware and warns if misordered.","max_tokens":2560},
    ]

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path) as f: return f.read()

@app.on_event("shutdown")
async def shutdown(): await client.aclose()
