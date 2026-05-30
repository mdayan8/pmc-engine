# PMC Engine — Architecture

## Overview

PMC (Predictive Minimal Context) is a 7-layer system that cuts AI coding token costs by 40-80% via AST-based surgical context compression.

## The 7 Layers

```
┌────────────────────────────────────────────────────┐
│                   USER QUERY                        │
│  "Fix race condition in the login function"         │
└────────────────────┬───────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────┐
│  L1: SYMBOL INDEX (indexer.py)                     │
│  AST parse + 6-source dependency graph             │
│  • Call graph (function calls)                     │
│  • Import graph (who imports what)                 │
│  • Config key tracking (JWT_SECRET refs)           │
│  • Type/model usage (User.jwt_token refs)          │
│  • Test mapping (test_auth → auth_service)         │
│  • Convention clustering (jwt_*.py)                │
├────────────────────────────────────────────────────┤
│  L2: HYBRID INTENT PARSER (intent.py)              │
│  • Fast path: regex rules (<1ms)                   │
│  • Slow path: MiniLM embeddings (~20ms, optional)  │
│  • Fallback: UNKNOWN → conservative mode           │
├────────────────────────────────────────────────────┤
│  L3: AUTO-CALIBRATING SCORER (context.py)          │
│  score = direct×3.0 + hop1×1.5 + hop2×0.6         │
│        + import×0.5 + config×1.0 + type×1.0       │
│        + semantic×0.4 − cache×0.9                  │
│  pmc calibrate tunes weights per codebase          │
├────────────────────────────────────────────────────┤
│  L4: TIERED CONTEXT BUILDER (context.py)           │
│  T1 (≥2.5): Full source code                      │
│  T2 (≥1.0): Signature + docstring                 │
│  T3 (≥0.3): Stub (name + file)                    │
│  T4 (<0.3): Omitted                               │
├────────────────────────────────────────────────────┤
│  L5: PASSIVE DEMAND EXPANSION (context.py)         │
│  • Scans AI response for stubbed symbols           │
│  • Auto-expands [EXPAND: X] or mentions           │
│  • Pre-expands 3+ mentions from same file          │
├────────────────────────────────────────────────────┤
│  L6: SESSION CACHE (cache.py)                      │
│  • Track sent symbols → diff-only on turn 2+      │
│  • TTL: T1=20, T2=10, T3=5 turns                 │
│  • Response compression with [REF: X] stubs        │
├────────────────────────────────────────────────────┤
│  L7: QUALITY VERIFICATION (verify.py)              │
│  pmc verify → 20 tasks, compare full vs PMC       │
│  Auto-tunes dep graph on misses                    │
│  Self-improving per codebase                       │
└────────────────────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────┐
│               COMPRESSED CONTEXT                    │
│  ~5,000 tokens vs ~45,000 naive                   │
│  40-80% reduction, 95%+ quality                    │
└────────────────────────────────────────────────────┘
```

## Integration Methods

### HTTP Proxy (most universal)
```
AI Tool → localhost:8080 → PMC Proxy → Anthropic/OpenAI API
```
Works with: Claude Code (ANTHROPIC_BASE_URL), Cline, Continue, Aider, OpenCode, Gemini CLI

### MCP Server (native tool access)
```
Claude Code ←→ PMC MCP Server (stdio)
  Tools: pmc_compress, pmc_index, pmc_expand, pmc_stats, pmc_search
```
Works with: Claude Code, Cursor, Windsurf, Cline, Zed

### Claude Code Hooks (deepest integration)
```
UserPromptSubmit → inject compressed context
PreToolUse → intercept Read calls, serve compressed files
```

### Python Library (direct API)
```python
from pmc import PMCEngine
engine = PMCEngine()
engine.index("./src")
result = engine.compress("Fix the race condition in login")
```

## Directory Structure

```
pmc/
├── __init__.py     # PMCEngine facade
├── indexer.py      # L1: Symbol index + 6-source dep graph
├── intent.py       # L2: Hybrid intent parser
├── context.py      # L3-5: Scorer + builder + passive expansion
├── cache.py        # L6: Session cache + response compression
├── verify.py       # L7: Quality verification loop
├── cli.py          # CLI entry point
├── config.py       # TOML config manager
├── grammars/
│   ├── python.py   # Python parser (stdlib ast + tree-sitter)
│   └── typescript.py  # TypeScript parser (tree-sitter + regex)
├── proxy/
│   ├── server.py   # FastAPI proxy (Anthropic + OpenAI)
│   └── compression.py  # Request compression middleware
└── mcp/
    └── server.py   # MCP stdio server
```

## Data Flow (Example)

1. **User**: "Fix race condition in login"
2. **Intent Parser**: {op: DEBUG, target: login, blast: MEDIUM}
3. **Symbol Index**: login() calls verify_password(), query(), log_failed_login(), rate_limiter()
4. **Scorer**: login=3.0(T1), verify_pw=1.5(T2), query=1.5(T2), log_fail=1.5(T2)
5. **Context Builder**: Tier 1 (login full), Tier 2 (4 sigs), Tier 3 (connect, close stubs)
6. **Session Cache**: Mark all sent, next turn send only new symbols
7. **Result**: 424 tokens vs 1,128 naive (62.4% reduction)

## Key Design Decisions

1. **HTTP proxy is primary** — covers 7+ tools with one codebase
2. **MCP server is supplementary** — provides tools AI can call
3. **tree-sitter optional** — stdlib ast fallback for zero-dependency core
4. **3 honesty modes** — conservative/balanced/aggressive, user chooses
5. **Self-improving** — verify loop auto-tunes weights per codebase
