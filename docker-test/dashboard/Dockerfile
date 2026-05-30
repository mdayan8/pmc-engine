FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn httpx 2>&1 | tail -2
COPY server.py /app/server.py
COPY static /app/static
EXPOSE 80
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "80", "--log-level", "info"]
