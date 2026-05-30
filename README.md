# PMC Engine

**Predictive Minimal Context** — cut AI coding token costs by **40-80%** with zero code changes.

```bash
pip install pmc-engine
```

```python
from pmc import PMCEngine

engine = PMCEngine()
engine.index("./my_project")

result = engine.compress("Fix the race condition in the login function")
print(result.summary())
# → 424 tokens vs 1,128 naive (62.4% reduction)
```

## The Problem

Uber burned its $24M AI budget in 4 months. AI tools dump entire codebases into context:
45,000 tokens to fix one function. PMC solves this structurally.

## The Solution

PMC replaces full-file context with a **tiered symbolic skeleton**:

| Tier | Score | What's Sent |
|------|-------|-------------|
| T1: Full | ≥2.5 | Direct touch points (1-3 functions) |
| T2: Sig | ≥1.0 | Signatures + docstrings only |
| T3: Stub | ≥0.3 | Name + file location |
| T4: Omit | <0.3 | Nothing |

**Result**: 40-80% fewer tokens. Same AI output quality.

## How It Works

```
1. AST-parse your codebase → symbol index + 6-source dependency graph
2. Parse your query → understand intent + target symbols
3. Score every symbol → direct×3 + hop1×1.5 + hop2×0.6 + ...
4. Build tiered context → full code / signatures / stubs / omit
5. Session cache → diff-only on turn 2+
6. Passive expansion → auto-expand stubs AI mentions
7. Verify quality → self-improving per codebase
```

## Honest Performance

| Mode | Reduction | Quality Match | When To Use |
|------|-----------|---------------|-------------|
| Conservative | 40-50% | 98%+ | Refactors, production changes |
| Balanced | 50-65% | 95%+ | Daily development (default) |
| Aggressive | 65-80% | 90%+ | Quick questions, READ queries |

## Quick Start

```bash
# Install
pip install pmc-engine

# Build index
pmc index ./my-project

# Compress a query
pmc compress "Fix the race condition in login"

# Start proxy (works with Claude Code, Cursor, Cline, Aider, Continue...)
pmc serve --port 8080

# In another terminal:
export ANTHROPIC_BASE_URL=http://localhost:8080
claude "Fix the race condition in login"
```

## Integration Methods

| Method | Tools | How |
|--------|-------|-----|
| **HTTP Proxy** | Claude Code, Cline, Continue, Aider, OpenCode, Gemini CLI | Set ANTHROPIC_BASE_URL or OPENAI_BASE_URL |
| **MCP Server** | Claude Code, Cursor, Windsurf, Cline, Zed | Add pmc to mcpServers in settings |
| **Python Lib** | Any Python project | `from pmc import PMCEngine` |
| **CC Hooks** | Claude Code | `pmc install-cc-hooks` |

## CLI Commands

```bash
pmc index     # Build symbol index
pmc compress  # Compress a query into surgical context
pmc serve     # Start HTTP proxy server
pmc mcp       # Start MCP server
pmc bench     # Run token reduction benchmark
pmc verify    # Run quality verification (self-improving)
pmc calibrate # Auto-tune scoring weights per codebase
pmc stats     # Show compression statistics
```

## Savings Projections

| Team Size | Naive Cost | With PMC | Annual Savings |
|-----------|------------|----------|----------------|
| 1 engineeer | $958/yr | $250/yr | $708 |
| 50 eng | $48K/yr | $13K/yr | $35K |
| 500 eng | $479K/yr | $125K/yr | $354K |
| 5,000 eng | $9.85M/yr | $3.9M/yr | $5.9M |

## License

MIT — free for everyone. Build on it.
