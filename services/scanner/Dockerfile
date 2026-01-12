FROM python:3.10-slim-bullseye

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/scanner/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code (same structure as ingest/regime)
COPY services/scanner/ /app/
COPY contracts/ /app/contracts/

# Set Python path
ENV PYTHONPATH=/app

# Run service
CMD ["python", "main.py"]

