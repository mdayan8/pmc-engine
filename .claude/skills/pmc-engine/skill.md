---
name: pmc-engine
description: PMC Engine — Predictive Minimal Context. Cuts AI coding token costs by 90%+ by compressing codebase context before sending to the AI model.
---

# PMC Engine — Agent Skill

## What It Does

PMC sits between you (the AI agent) and the codebase. Instead of dumping entire files into context, it:

1. **Indexes** the codebase once (AST parse → symbol database with call graph)
2. **Parses** the user's query → extracts intent + target symbols
3. **Scores** every symbol → direct hits (T1), dependencies (T2), stubs (T3), omit (T4)
4. **Assembles** tiered context → full code / signatures / stubs
5. **Sends** only what you actually need

## How to Use It

```python
from pmc import PMCEngine

engine = PMCEngine()
engine.index("./my_project")

# Instead of loading all files, compress:
result = engine.compress("Fix the race condition in the login function")
# Returns ~5K tokens instead of ~45K tokens

# result.context_string — send this to the AI
# result.summary() — "Tokens: 424 vs naive 1,128 (62.4% reduction)"
```

## Architecture (5 Layers)

| Layer | File | What |
|-------|------|------|
| L1 | indexer.py | AST parse → symbols + 6-source dep graph |
| L2 | intent.py | Classify op type (MODIFY/CREATE/READ/DEBUG/REFACTOR/TEST) |
| L3 | context.py | Score: `direct×3 + hop1×1.5 + hop2×0.6 + import×0.5 + config×1.0 + type×1.0 − cache×0.9` |
| L4 | context.py | Tiers: Full code (≥2.5) / Signatures (≥1.0) / Stubs (≥0.3) / Omit |
| L5 | cache.py | Session cache → diff-only on turn 2+ |

## Modes

| Mode | Reduction | Quality | Use |
|------|-----------|---------|-----|
| conservative | 40-50% | 98%+ | Refactors, production |
| balanced | 50-65% | 95%+ | Daily dev (default) |
| aggressive | 65-80% | 90%+ | Quick questions |

## Integration

```bash
# HTTP proxy (works with any AI tool)
pmc serve --port 8080
export ANTHROPIC_BASE_URL=http://localhost:8080

# MCP server
pmc mcp

# Python library
from pmc import PMCEngine
```

## The Core Insight

LLMs degrade in long context ("lost in the middle" problem — proven by NoLiMa benchmark, ICML 2025). Sending 45K tokens of irrelevant code pushes the relevant 500 tokens into the middle where attention is weakest. PMC keeps context tight — better output quality AND lower cost.
