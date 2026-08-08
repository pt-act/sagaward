# Build from the REPO ROOT so the strix package (for strix.core.net) is in the context:
#   docker build -f benchmarks/bv2p/ssrf_webhook/Dockerfile -t strix-bv2p-ssrf_webhook .
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.34.0" \
    "pydantic>=2.11.0" \
    "httpx>=0.28.0"

COPY strix /src/strix
ENV PYTHONPATH=/src

COPY benchmarks/bv2p/ssrf_webhook/core.py .
COPY benchmarks/bv2p/ssrf_webhook/app.py .

ENV VULN_MODE=1
EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
