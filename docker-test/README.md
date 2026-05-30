# PMC Engine — Docker Test Harness

Two proxy containers + live dashboard. Test PMC compression side-by-side with a raw proxy.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Docker Compose                                           │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  PMC Proxy   │  │  Raw Proxy   │  │  Dashboard   │   │
│  │  port 8080   │  │  port 8081   │  │  port 8082   │   │
│  │  PMC: ON     │  │  PMC: OFF    │  │  Comparison  │   │
│  │  60K budget  │  │  60K budget  │  │  Live charts │   │
│  │  DeepSeek▲   │  │  DeepSeek▲   │  └──────┬───────┘   │
│  └──────┬───────┘  └──────┬───────┘         │           │
│         │                 │                 │           │
│         └─────────────────┴─────────────────┘           │
│                           │                             │
│                  DeepSeek API (upstream)                 │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Set your DeepSeek API key
export ANTHROPIC_AUTH_TOKEN="your_deepseek_key_here"

# 2. Build & start
cd docker-test
docker compose up --build -d

# 3. Open dashboard
open http://localhost:8082

# 4. Run test queries
python3 run_test.py
```

## Using with Claude Code

```bash
# Terminal 1: Test with PMC
export ANTHROPIC_BASE_URL="http://localhost:8080"
export ANTHROPIC_AUTH_TOKEN="your_key"
export ANTHROPIC_MODEL="deepseek-v4-pro"
claude "Fix the bug in login"

# Terminal 2: Test without PMC
export ANTHROPIC_BASE_URL="http://localhost:8081"
export ANTHROPIC_AUTH_TOKEN="your_key"
export ANTHROPIC_MODEL="deepseek-v4-pro"
claude "Fix the bug in login"
```

## Monitoring

Open `http://localhost:8082` in your browser.

The dashboard shows:
- ✅ PMC container: token usage, request count, budget remaining
- ❌ Raw container: same metrics
- 📊 Comparison summary: efficiency ratio, queries done
- Budget exhaustion warning when either hits 60K

## Resetting

```bash
# Reset both trackers from dashboard
Click "Reset Both Trackers" button

# Or from CLI
curl -X POST http://localhost:8080/reset
curl -X POST http://localhost:8081/reset
```

## Test Harness

Run `python3 run_test.py` for automated comparison:

```
  ════════════════════════════════════════════════════════
  PMC ENGINE — TEST HARNESS
  ════════════════════════════════════════════════════════
  PMC proxy: http://localhost:8080
  Raw proxy: http://localhost:8081

  [EASY] Add None check in BackgroundTasks.add_task...
    ├─ PMC:  6,300 tokens in 12.5s
    └─ RAW:  45,000 tokens in 14.2s

  [HARD] Middleware ordering validation...
    ├─ PMC:  3,248 tokens in 18.1s
    └─ RAW:  45,000 tokens in 20.3s
```

## Budget

Both containers have a hard 60K token limit. When exhausted:
- New requests return HTTP 429
- Dashboard shows "BUDGET EXHAUSTED" in red
- Reset with `POST /reset` or dashboard button
