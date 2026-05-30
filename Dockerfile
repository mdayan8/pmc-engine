# PMC Engine — Proxy Server Docker Image
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir "pmc-engine[proxy]" \
    && pip install --no-cache-dir "git+https://github.com/pmc-engine/pmc.git" \
    || true

# Install from local build as fallback
COPY . .
RUN pip install -e ".[proxy]" || pip install -e .

# Default: run the proxy server
EXPOSE 8080
ENV PMC_MODE=balanced
ENV PMC_PORT=8080
ENV PMC_HOST=0.0.0.0

CMD pmc serve --port $PMC_PORT --host $PMC_HOST --mode $PMC_MODE

# Alternative: run MCP server
# CMD ["pmc", "mcp"]
