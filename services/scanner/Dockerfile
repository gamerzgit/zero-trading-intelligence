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

# Copy service code
COPY services/scanner/ ./services/scanner/
COPY contracts/ ./contracts/

# Set working directory to service
WORKDIR /app/services/scanner

# Run service
CMD ["python", "main.py"]

