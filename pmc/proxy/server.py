"""
PMC Engine — HTTP Proxy Server
================================
FastAPI-based proxy that intercepts AI API requests and compresses code context.

Endpoints:
  - POST /v1/messages          — Anthropic Messages API proxy
  - POST /v1/chat/completions  — OpenAI Chat Completions proxy
  - GET  /health               — Health check
  - GET  /stats                — Compression statistics
"""

import os
import json
import time
import httpx
from typing import Optional

from pmc.proxy.compression import PMCProxyCompressor


def start_proxy(host: str = "0.0.0.0", port: int = 8080, mode: str = "balanced", source_root: str = "."):
    """Start the PMC HTTP proxy server using FastAPI + uvicorn."""
    try:
        import uvicorn
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, StreamingResponse
    except ImportError:
        print("  ⚠ fastapi and uvicorn required for proxy mode.")
        print("  Install: pip install 'pmc-engine[proxy]'")
        return

    app = FastAPI(
        title="PMC Engine Proxy",
        description="Predictive Minimal Context — HTTP proxy for AI API requests",
        version="0.1.0",
    )

    compressor = PMCProxyCompressor(source_root=source_root, mode=mode)

    # Anthropic API endpoints
    ANTHROPIC_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

    # OpenAI API endpoints
    OPENAI_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

    client = httpx.AsyncClient(timeout=120.0)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        response.headers["X-PMC-Processing-Time-ms"] = str(round(duration * 1000, 1))
        return response

    @app.post("/v1/messages")
    async def proxy_anthropic(request: Request):
        """Proxy for Anthropic Messages API."""
        body = await request.json()

        # Compress request body
        compressed = compressor.compress_request(body)

        # Get API key from request header or env
        api_key = request.headers.get("x-api-key", ANTHROPIC_KEY)
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "API key required. Set ANTHROPIC_API_KEY env var or pass x-api-key header."}
            )

        # Forward to Anthropic API
        upstream_url = f"{ANTHROPIC_BASE}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
            "content-type": "application/json",
        }

        try:
            response = await client.post(
                upstream_url,
                json=compressed,
                headers=headers,
            )
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
                headers={"X-PMC-Token-Savings": str(compressor.stats["total_savings"])},
            )
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": f"Upstream request failed: {str(e)}"}
            )

    @app.post("/v1/chat/completions")
    async def proxy_openai(request: Request):
        """Proxy for OpenAI Chat Completions API."""
        body = await request.json()

        # Compress request body
        compressed = compressor.compress_request(body)

        # Get API key
        api_key = request.headers.get("authorization", "").replace("Bearer ", "") or OPENAI_KEY
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "API key required. Set OPENAI_API_KEY env var or pass Authorization header."}
            )

        # Forward to OpenAI API
        upstream_url = f"{OPENAI_BASE}/v1/chat/completions"
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }

        try:
            response = await client.post(
                upstream_url,
                json=compressed,
                headers=headers,
            )
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
                headers={"X-PMC-Token-Savings": str(compressor.stats["total_savings"])},
            )
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": f"Upstream request failed: {str(e)}"}
            )

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {
            "status": "ok",
            "service": "pmc-engine-proxy",
            "version": "0.1.0",
            "uptime_seconds": int(time.time() - start_time),
            "indexed": compressor._indexed,
        }

    @app.get("/stats")
    async def stats():
        """Compression statistics."""
        return compressor.get_stats()

    @app.on_event("startup")
    async def startup():
        nonlocal start_time
        start_time = time.time()
        # Start building index in background
        try:
            compressor.ensure_indexed()
            stats = compressor.engine.stats()
            print(f"  ✅ Indexed {stats['index']['total_symbols']} symbols across {stats['index']['total_files']} files")
        except Exception as e:
            print(f"  ⚠ Index build: {e}")

    start_time = time.time()

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        import asyncio
        asyncio.run(client.aclose())
