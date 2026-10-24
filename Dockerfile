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

# Health check probe
HEALTHCHECK --interval=60s --timeout=15s --start-period=60s --retries=3 \
    CMD python -c "import requests; r = requests.get('https://eel-feminine-progeny.ngrok-free.dev/v1/models', headers={'Authorization': 'Bearer sk-jaggu'}); exit(0 if r.status_code == 200 else 1)"

CMD ["python", "agenticverse_cloud_orchestrator.py"]
