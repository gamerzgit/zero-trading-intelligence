FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/execution/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/execution/ /app/
COPY contracts/ /app/contracts/

# Expose API port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

# Run service
CMD ["python", "main.py"]
