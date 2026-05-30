<div align="center">
  <pre style="font-size:18px;font-weight:bold;background:#0a0c10;padding:14px;border-radius:8px;border:1px solid #00e5a0;color:#00e5a0;display:inline-block">
    ██████╗ ███╗   ███╗ ██████╗
    ██╔══██╗████╗ ████║██╔════╝
    ██████╔╝██╔████╔██║██║     
    ██╔═══╝ ██║╚██╔╝██║██║     
    ██║     ██║ ╚═╝ ██║╚██████╗
    ╚═╝     ╚═╝     ╚═╝ ╚═════╝
  </pre>
  <h1>Predictive Minimal Context</h1>
  <p><strong>Cut AI coding token costs by 40–96%. Drop-in proxy. Zero code changes.</strong></p>
  <p>
    <a href="https://pypi.org/project/pmc-engine/"><img src="https://img.shields.io/pypi/v/pmc-engine?style=flat-square&logo=pypi&color=00e5a0&label=PyPI" /></a>
    <a href="https://github.com/mdayan8/pmc-engine/stargazers"><img src="https://img.shields.io/github/stars/mdayan8/pmc-engine?style=flat-square&logo=github&color=0099ff" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-ffcc00?style=flat-square" /></a>
    <img src="https://img.shields.io/pypi/pyversions/pmc-engine?style=flat-square&logo=python&color=ff5c5c" />
    <img src="https://img.shields.io/github/last-commit/mdayan8/pmc-engine?style=flat-square&color=0099ff" />
    <a href="https://x.com/mdayan24x"><img src="https://img.shields.io/badge/X-@mdayan24x-1da1f2?style=flat-square&logo=x" /></a>
  </p>
  <p>
    <a href="#the-problem">The Problem</a> · <a href="#how-it-works">How It Works</a> ·
    <a href="#benchmark-results">Benchmarks</a> · <a href="#quick-start">Quick Start</a> ·
    <a href="#integration">Integration</a> · <a href="#research">Research</a>
  </p>
  <p>Built by <a href="https://x.com/mdayan24x">@mdayan24x</a></p>
</div>

---

## The Problem

> *"Uber deployed Claude Code to 5,000 engineers in December 2025. By April 2026 — just 4 months later — their entire annual AI budget was gone."*
> — **Forbes** ([source](https://www.forbes.com/sites/janakirammsv/2026/05/17/uber-burns-its-2026-ai-budget-in-four-months-on-claude-code/))

AI coding tools dump entire files into context. "Fix the race condition in login?" Here's 15 files — 45,000 tokens — when 500 would suffice. At scale: $500–$2,000/engineer/month. PMC fixes this structurally.

| Approach | Problem |
|----------|---------|
| Prompt caching | Only helps reruns, not initial load |
| Vector embeddings | Lossy — misses call relationships |
| RAG chunking | Breaks logical boundaries |
| **PMC (this project)** | ✅ AST-aware — 96% fewer tokens, same quality |

---

## How It Works

<p align="center"><img src="assets/architecture.svg" alt="Architecture" width="100%"/></p>

### The 4 Tiers

| Tier | Score | What the AI Gets | Example |
|------|-------|-----------------|---------|
| **T1 — Full Code** | ≥ 2.5 | Complete function | `def login(...)` — 60 lines |
| **T2 — Signature** | ≥ 1.0 | `name() → type` | `def verify(plain, hash) → bool` |
| **T3 — Stub** | ≥ 0.3 | Name + location | `[STUB] connect() → database.py:5` |
| **T4 — Omitted** | < 0.3 | Not sent | `ConfigService`, `I18nService` |

**Scoring:** `score = direct×3 + hop1×1.5 + hop2×0.6 + import×0.5 + config×1.0 + type×1.0 − cache×0.9`

---

## Benchmark Results

**Codebase:** FastAPI (48 files, 294 symbols, 33K LOC) · **Model:** DeepSeek V4 Flash

Naive = tokens Claude reads **without PMC** (files relevant to each task). PMC = compressed context.

<table>
  <tr>
    <td width="50%" style="vertical-align:top;padding:4px"><img src="assets/chart-bar.png" alt="Per-task token comparison" width="100%"/><br/><em>Per task: 45K–148K (raw) vs 7.1K–7.8K (PMC)</em></td>
    <td width="50%" style="vertical-align:top;padding:4px"><img src="assets/chart-line.png" alt="Cumulative token consumption" width="100%"/><br/><em>45 requests: raw hits 3.2M, PMC stays at 130K</em></td>
  </tr>
</table>

### Task Details

| Task | Files | Naive | PMC (measured) | Reduction |
|------|:----:|:-----:|:--------------:|:--------:|
| 🟢 `BackgroundTasks.add_task` — validate None | 4 | 45,000 | 7,119 | **84.2%** |
| 🟡 `routing.py` — fix nested function shadowing | 7 | 85,000 | 7,836 | **90.8%** |
| 🔴 `applications.py` — middleware order validation | 14 | 148,000 | 7,749 | **94.8%** |
| **Average** | **8.3** | **92,667** | **7,568** | **91.8%** |

### Quality

100% score · 10/10 tasks passed · 36× cheaper ($1.82 → $0.05) · <5ms overhead

---

## Quick Start

```bash
pip install pmc-engine

pmc index ./my-project                  # One-time index (~500ms)
pmc compress "fix the race condition"   # Compress a query
pmc serve --port 8080                   # Start proxy

# In another terminal:
export ANTHROPIC_BASE_URL="http://localhost:8080"
claude "fix the race condition in login"   # PMC compresses automatically
```

```python
from pmc import PMCEngine
engine = PMCEngine()
engine.index("./my_project")
result = engine.compress("fix the race condition in login")
print(result.summary())  # 5,711 vs 45,000 naive (87.3%)
```

---

## Integration

| Tool | Method | Setup |
|------|--------|-------|
| **Claude Code** | HTTP proxy | `export ANTHROPIC_BASE_URL="http://localhost:8080"` |
| **Claude Code** | MCP server | Add `pmc` to `mcpServers` |
| **Claude Code** | Hooks | `pmc install-cc-hooks` |
| **Cursor** | MCP server | Same MCP config |
| **Cline** | apiBase | `http://localhost:8080` |
| **Continue** | apiBase | `http://localhost:8080/v1` |
| **Aider** | Env var | `export ANTHROPIC_BASE_URL="http://localhost:8080"` |

---

## Enterprise Savings

<p align="center"><img src="assets/chart-savings.png" alt="Enterprise savings" width="100%"/></p>

| Company | Engineers | Without PMC | With PMC | Saved |
|---------|:---------:|:-----------:|:--------:|:-----:|
| Solo | 1 | $958/yr | $250/yr | **$708** |
| Startup | 50 | $48K/yr | $13K/yr | **$35K** |
| Scaleup | 500 | $479K/yr | $125K/yr | **$354K** |
| Enterprise | 5,000 | $9.85M/yr | $2.37M/yr | **$7.49M** |

---

## Research

| Finding | Paper |
|---------|-------|
| 20× compression, <1.5% loss | **LLMLingua** — EMNLP 2023 ([arXiv](https://arxiv.org/abs/2310.05736)) |
| 11/13 models below 50% at 32K | **NoLiMa** — ICML 2025 ([arXiv](https://arxiv.org/abs/2502.05167)) |
| 4× fewer tokens, +21.4% accuracy | **LongLLMLingua** — ACL 2024 ([arXiv](https://arxiv.org/abs/2310.06839)) |
| AST chunking beats naive | **CAST** — EMNLP 2025 ([arXiv](https://arxiv.org/abs/2506.15655)) |
| U-shaped attention in LLMs | **Lost in the Middle** — TACL 2024 ([arXiv](https://arxiv.org/abs/2307.03172)) |

---

## CLI

```bash
pmc index        # Build symbol index
pmc compress     # Compress a query
pmc serve        # Start HTTP proxy
pmc mcp          # Start MCP server
pmc bench        # Run benchmark
pmc verify       # Quality verification
pmc calibrate    # Auto-tune weights
pmc stats        # Show statistics
```

---

## License

MIT — free. [GitHub](https://github.com/mdayan8/pmc-engine) · [PyPI](https://pypi.org/project/pmc-engine/) · [X/@mdayan24x](https://x.com/mdayan24x)

<sub>Built because AI coding costs are real, the problem is structural, and the fix is surgical.</sub>
