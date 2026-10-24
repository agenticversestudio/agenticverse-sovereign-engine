FROM python:3.11-slim

# Install system utilities and Colab CLI dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements and official Colab CLI
RUN pip install --no-cache-dir requests google-colab-cli

# Copy Orchestrator codebase
COPY agenticverse_cloud_orchestrator.py /app/
COPY scripts/ /app/scripts/

# Health check probe against local HTTP keep-alive server
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os, requests; port = os.environ.get('PORT', '8080'); r = requests.get(f'http://127.0.0.1:{port}/'); exit(0 if r.status_code == 200 else 1)"

CMD ["python", "agenticverse_cloud_orchestrator.py"]
