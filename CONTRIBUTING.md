# Contributing to PMC Engine

## Quick Start

```bash
git clone https://github.com/pmc-engine/pmc
cd pmc-engine
pip install -e ".[dev]"
pytest tests/
```

## Development

### Run Tests
```bash
pytest tests/ -v
pytest tests/ --cov=pmc --cov-report=term-missing
```

### Run Benchmarks
```bash
pmc bench ./path/to/codebase
```

### Run Verification
```bash
pmc verify ./path/to/codebase
```

### Run Calibration
```bash
pmc calibrate ./path/to/codebase
```

### Start Proxy
```bash
pmc serve --port 8080
```

### Start MCP Server
```bash
pmc mcp
```

## Code Style

- Python 3.11+ type annotations
- f-strings over .format() or %
- Dataclasses over manual __init__
- Docstrings for all public APIs

## Architecture

See [docs/architecture.md](docs/architecture.md) for the 7-layer design.

## License

MIT
