# InsightPM backend container.
# Single-stage build: install deps, copy code, run uvicorn.
# Frontend is built and served separately (see frontend/Dockerfile).

FROM python:3.12-slim

WORKDIR /app

# Install system deps that some Python wheels need (cryptography for google-auth, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first so Docker can cache the pip layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

# Create data dir for SQLite + logs (mounted as volume in compose)
RUN mkdir -p /data && chmod 755 /data

# The app expects ~/.insightpm/* -- redirect HOME to the volume path
ENV HOME=/data

EXPOSE 8000

# Healthcheck endpoint defined in app/main.py
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
