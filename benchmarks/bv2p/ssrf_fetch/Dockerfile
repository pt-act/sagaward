# Build from the REPO ROOT so the oriontrix package (for oriontrix.core.net) is in the context:
#   docker build -f benchmarks/bv2p/ssrf_fetch/Dockerfile -t oriontrix-bv2p-ssrf .
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.34.0" \
    "pydantic>=2.11.0" \
    "httpx>=0.27.0"

# Make the oriontrix package importable (the patched SSRF guard reuses oriontrix.core.net) without
# pulling oriontrix's full dependency set — oriontrix.core.net is pure-stdlib at import time.
COPY oriontrix /src/oriontrix
ENV PYTHONPATH=/src

COPY benchmarks/bv2p/ssrf_fetch/core.py .
COPY benchmarks/bv2p/ssrf_fetch/app.py .

ENV VULN_MODE=1
EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
