# ZERO Regime Engine Service (ARM64 compatible)
FROM python:3.10-slim-bullseye

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/regime/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/regime/ /app/
COPY contracts/ /app/contracts/

# Set Python path
ENV PYTHONPATH=/app

# Expose health endpoint
EXPOSE 8000

# Run service
CMD ["python", "main.py"]

