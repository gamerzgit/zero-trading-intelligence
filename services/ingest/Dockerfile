# ZERO Price Ingestion Service - Dockerfile (ARM64/Jetson compatible)
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/ingest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import redis.asyncio; print('✅ redis.asyncio import successful')" || \
    (echo "❌ redis.asyncio import failed" && pip list | grep redis && exit 1)

# Copy application code
COPY services/ingest/ /app/
COPY contracts/ /app/contracts/

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run service
CMD ["python", "main.py"]

