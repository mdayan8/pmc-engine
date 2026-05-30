FROM python:3.13-slim

WORKDIR /app

# Install deps
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi uvicorn httpx pyyaml 2>&1 | tail -2

# Copy PMC engine source
COPY pmc/ /app/pmc/
COPY pyproject.toml setup.py /app/

# Install PMC
RUN pip install -e /app 2>&1 | tail -2 || echo "PMC install skipped"

# Copy proxy server
COPY docker-test/proxy/server.py /app/server.py
COPY docker-test/proxy/stats.py /app/stats.py

ENV SOURCE_ROOT=/app/codebase
EXPOSE 80

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "80", "--log-level", "info"]
