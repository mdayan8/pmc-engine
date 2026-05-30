#!/usr/bin/env python3
"""
PMC Test Harness — Run queries against both PMC and Raw proxies.

Usage:
    # Set your API key
    export ANTHROPIC_AUTH_TOKEN="your_deepseek_key_here"

    # Start the proxies first, then:
    python3 run_test.py

    # Or test specific queries:
    python3 run_test.py --pmc-url http://localhost:8080 --raw-url http://localhost:8081

What this does:
    1. Builds the PMC index (POST /index on PMC proxy)
    2. Runs 3 test queries through BOTH proxies
    3. Prints side-by-side comparison of token usage
    4. Shows how much budget each consumed
"""

import os
import sys
import json
import time
import httpx
import argparse


# Test queries (from real FastAPI issues)
TEST_QUERIES = [
    {
        "difficulty": "EASY",
        "query": "Add a None check for the func parameter in BackgroundTasks.add_task. If func is None, raise a ValueError with a clear error message.",
        "messages": [
            {"role": "user", "content": "Add a None check for the func parameter in BackgroundTasks.add_task. If func is None, raise a ValueError with a clear error message."}
        ],
        "model": "deepseek-v4-pro",
        "max_tokens": 1024,
    },
    {
        "difficulty": "MEDIUM",
        "query": "Fix the nested 'app' function name clash in request_response in routing.py. The inner 'async def app' shadows the outer 'async def app'. Rename the inner one to 'inner_app'.",
        "messages": [
            {"role": "user", "content": "Fix the nested 'app' function name clash in request_response in routing.py. The inner 'async def app' shadows the outer 'async def app'. Rename the inner one to 'inner_app'."}
        ],
        "model": "deepseek-v4-pro",
        "max_tokens": 1536,
    },
    {
        "difficulty": "HARD",
        "query": "Add middleware ordering validation to FastAPI.__init__ in applications.py. Create a method that checks if certain middleware like CORSMiddleware is placed before other middleware. If misordered, log a warning.",
        "messages": [
            {"role": "user", "content": "Add middleware ordering validation to FastAPI.__init__ in applications.py. Create a method that checks if certain middleware like CORSMiddleware is placed before other middleware. If misordered, log a warning."}
        ],
        "model": "deepseek-v4-pro",
        "max_tokens": 2048,
    },
]


def build_body(query_info: dict) -> dict:
    """Build the API request body from query info."""
    return {
        "model": query_info["model"],
        "max_tokens": query_info["max_tokens"],
        "messages": query_info["messages"],
    }


async def test_proxy(client: httpx.AsyncClient, url: str, api_key: str,
                     query_info: dict, label: str) -> dict:
    """Send a query to a proxy and return the result."""
    body = build_body(query_info)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    start = time.time()
    try:
        resp = await client.post(
            f"{url}/v1/messages",
            json=body,
            headers=headers,
            timeout=300.0,
        )
        elapsed = time.time() - start
        resp_data = resp.json()
    except httpx.TimeoutException:
        return {"label": label, "error": "TIMEOUT", "elapsed": time.time() - start}
    except Exception as e:
        return {"label": label, "error": str(e), "elapsed": time.time() - start}

    # Extract response
    resp_content = ""
    if "content" in resp_data:
        for block in resp_data.get("content", []):
            if block.get("type") == "text":
                resp_content += block.get("text", "")

    response_len = len(resp_content)

    # Extract headers
    h = resp.headers
    result = {
        "label": label,
        "status": resp.status_code,
        "elapsed": round(elapsed, 1),
        "response_len": response_len,
        "response_preview": resp_content[:200],
        "total_tokens": h.get("x-total-tokens", "N/A"),
        "budget_remaining": h.get("x-budget-remaining", "N/A"),
        "budget_exhausted": h.get("x-budget-exhausted", "false"),
        "request_count": h.get("x-request-count", "N/A"),
        "proxy_type": h.get("x-proxy-type", "N/A"),
    }

    if label.lower() == "pmc":
        result["naive_tokens"] = h.get("x-naive-tokens", "N/A")
        result["reduction_pct"] = h.get("x-reduction-pct", "N/A")

    # If budget exhausted, flag it
    if h.get("x-budget-exhausted") == "true":
        result["budget_exhausted"] = True

    return result


async def get_stats(client: httpx.AsyncClient, url: str) -> dict:
    """Get stats from a proxy."""
    try:
        resp = await client.get(f"{url}/stats", timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def print_report(results: list[dict], pmc_stats: dict, raw_stats: dict):
    """Print a beautiful comparison report."""
    print()
    print("╔" + "═" * 76 + "╗")
    print("║" + "  PMC ENGINE — SIDE-BY-SIDE TEST RESULTS".center(74) + "║")
    print("╚" + "═" * 76 + "╝")
    print()

    # Separate PMC and Raw results
    pmc_results = [r for r in results if r.get("proxy_type") == "pmc"]
    raw_results = [r for r in results if r.get("proxy_type") == "raw"]

    for i in range(max(len(pmc_results), len(raw_results))):
        pmc_r = pmc_results[i] if i < len(pmc_results) else None
        raw_r = raw_results[i] if i < len(raw_results) else None
        query_info = TEST_QUERIES[i] if i < len(TEST_QUERIES) else None

        if query_info:
            diff = query_info["difficulty"]
            query_short = query_info["query"][:60]
            print(f"  ┌{'─' * 76}┐")
            print(f"  │  [{diff}] {query_short:<66}│")
            print(f"  ├{'─' * 36}┬{'─' * 39}┤")
            print(f"  │ {'WITH PMC':<33} │ {'WITHOUT PMC':<36} │")
            print(f"  ├{'─' * 36}┼{'─' * 39}┤")

            # Token comparison
            pmc_tokens = pmc_r.get("total_tokens", "ERR") if pmc_r else "N/A"
            raw_tokens = raw_r.get("total_tokens", "ERR") if raw_r else "N/A"
            print(f"  │ {'Tokens:':<17} {str(pmc_tokens):<15} │ {'Tokens:':<17} {str(raw_tokens):<15} │")

            # Time
            pmc_time = f"{pmc_r.get('elapsed', 0)}s" if pmc_r else "N/A"
            raw_time = f"{raw_r.get('elapsed', 0)}s" if raw_r else "N/A"
            print(f"  │ {'Time:':<17} {pmc_time:<15} │ {'Time:':<17} {raw_time:<15} │")

            # Reduction (PMC only)
            if pmc_r and "reduction_pct" in pmc_r:
                red = pmc_r.get("reduction_pct", "N/A")
                print(f"  │ {'Reduction:':<17} {str(red)+'%':<15} │ {'Reduction:':<17} {'N/A':<15} │")

            # Budget remaining
            pmc_budget = pmc_r.get("budget_remaining", "N/A") if pmc_r else "N/A"
            raw_budget = raw_r.get("budget_remaining", "N/A") if raw_r else "N/A"
            print(f"  │ {'Budget Left:':<17} {str(pmc_budget):<15} │ {'Budget Left:':<17} {str(raw_budget):<15} │")

            # Status
            pmc_status = pmc_r.get("status", "N/A") if pmc_r else "N/A"
            raw_status = raw_r.get("status", "N/A") if raw_r else "N/A"
            if pmc_r and pmc_r.get("budget_exhausted"):
                pmc_status = "BUDGET EXHAUSTED"
            if raw_r and raw_r.get("budget_exhausted"):
                raw_status = "BUDGET EXHAUSTED"
            print(f"  │ {'Status:':<17} {str(pmc_status):<15} │ {'Status:':<17} {str(raw_status):<15} │")

            # Error
            pmc_err = pmc_r.get("error", "") if pmc_r else ""
            raw_err = raw_r.get("error", "") if raw_r else ""
            if pmc_err:
                print(f"  │ {'ERROR:':<17} {pmc_err:<15} │ {'':<38} │")
            if raw_err:
                print(f"  │ {'':<34} │ {'ERROR:':<17} {raw_err:<15} │")

            print(f"  └{'─' * 36}┴{'─' * 39}┘")
            print()

    # Overall budget summary
    print()
    print("  ╔" + "═" * 76 + "╗")
    print("  ║" + "  BUDGET SUMMARY".center(74) + "║")
    print("  ╚" + "═" * 76 + "╝")
    print()

    pmc_total = pmc_stats.get("total_tokens", 0) if pmc_stats else 0
    raw_total = raw_stats.get("total_tokens", 0) if raw_stats else 0
    pmc_reqs = pmc_stats.get("request_count", 0) if pmc_stats else 0
    raw_reqs = raw_stats.get("request_count", 0) if raw_stats else 0
    pmc_rem = pmc_stats.get("budget_remaining", 0) if pmc_stats else 0
    raw_rem = raw_stats.get("budget_remaining", 0) if raw_stats else 0

    print(f"  {'':<4} {'METRIC':<30} {'PMC':<20} {'RAW':<20}")
    print(f"  {'':<4} {'─' * 30} {'─' * 20} {'─' * 20}")
    print(f"  {'':<4} {'Total Tokens Used':<30} {pmc_total:<20,} {raw_total:<20,}")
    print(f"  {'':<4} {'Requests Completed':<30} {pmc_reqs:<20} {raw_reqs:<20}")
    print(f"  {'':<4} {'Budget Remaining':<30} {pmc_rem:<20,} {raw_rem:<20,}")
    print(f"  {'':<4} {'Budget Used %':<30} {pmc_stats.get('budget_used_pct', 0):<19}% {raw_stats.get('budget_used_pct', 0):<19}%")

    if pmc_reqs > 0 and raw_reqs > 0:
        avg_pmc = pmc_total / pmc_reqs
        avg_raw = raw_total / raw_reqs
        ratio = avg_raw / max(avg_pmc, 1)
        print(f"  {'':<4} {'Avg Tokens/Request':<30} {avg_pmc:<20,.0f} {avg_raw:<20,.0f}")
        print(f"  {'':<4} {'Efficiency Ratio':<30} {'':<20} {ratio:<20.1f}x")
        print(f"  {'':<4} {'':<30} {'PMC does':<20} {ratio:.1f}x more/req")

    print()
    print(f"  💡 With PMC, {pmc_reqs} queries used {pmc_total:,} tokens.")
    print(f"  💡 Without PMC, {raw_reqs} queries used {raw_total:,} tokens.")
    if pmc_reqs > 0 and raw_reqs > 0:
        print(f"  💡 PMC is {ratio:.1f}x more token-efficient per request.")
    print()
    print(f"  ═" + "═" * 76)
    print()


async def main():
    parser = argparse.ArgumentParser(description="PMC Test Harness")
    parser.add_argument("--pmc-url", default="http://localhost:8080")
    parser.add_argument("--raw-url", default="http://localhost:8081")
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("❌ Set ANTHROPIC_AUTH_TOKEN environment variable or pass --api-key")
        sys.exit(1)

    api_key = args.api_key
    pmc_url = args.pmc_url
    raw_url = args.raw_url

    print()
    print("  ═" + "═" * 72)
    print("  PMC ENGINE — TEST HARNESS")
    print("  ═" + "═" * 72)
    print(f"  PMC proxy: {pmc_url}")
    print(f"  Raw proxy: {raw_url}")
    print(f"  API key:   {api_key[:8]}...{api_key[-4:]}")
    print()

    async with httpx.AsyncClient(timeout=300.0) as client:
        # 1. Build PMC index
        print("  📦 Building PMC symbol index...")
        try:
            resp = await client.post(f"{pmc_url}/index", timeout=60)
            if resp.status_code == 200:
                idx = resp.json()
                s = idx.get("stats", {})
                print(f"     Indexed {s.get('symbols', 0)} symbols in {s.get('files', 0)} files")
            else:
                print(f"     ⚠ Index response: {resp.status_code}")
        except Exception as e:
            print(f"     ⚠ Index failed: {e}")
        print()

        # 2. Run test queries through both proxies
        all_results = []
        for i, query_info in enumerate(TEST_QUERIES):
            diff = query_info["difficulty"]
            print(f"  [{diff}] Sending: {query_info['query'][:70]}...")

            # PMC
            pmc_r = await test_proxy(client, pmc_url, api_key, query_info, "PMC")
            all_results.append(pmc_r)
            pmc_tok = pmc_r.get("total_tokens", "?")
            pmc_time = pmc_r.get("elapsed", 0)
            pmc_stat = pmc_r.get("status", "ERR")
            print(f"    ├─ PMC:  {pmc_tok} tokens in {pmc_time}s (status: {pmc_stat})")

            # Raw
            raw_r = await test_proxy(client, raw_url, api_key, query_info, "RAW")
            all_results.append(raw_r)
            raw_tok = raw_r.get("total_tokens", "?")
            raw_time = raw_r.get("elapsed", 0)
            raw_stat = raw_r.get("status", "ERR")
            print(f"    └─ RAW:  {raw_tok} tokens in {raw_time}s (status: {raw_stat})")

            # Check for exhaustion
            for r in [pmc_r, raw_r]:
                if r.get("budget_exhausted") == "true":
                    print(f"    ⚠ BUDGET EXHAUSTED on {r.get('proxy_type', 'unknown')} proxy")
            print()

        # 3. Get final stats
        pmc_stats = await get_stats(client, pmc_url)
        raw_stats = await get_stats(client, raw_url)

        # 4. Print report
        print_report(all_results, pmc_stats, raw_stats)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
