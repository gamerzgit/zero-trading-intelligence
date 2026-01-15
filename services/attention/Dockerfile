FROM python:3.10-slim-bullseye

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/attention/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/attention/ /app/

# Copy contracts for schema access
COPY contracts/ /app/contracts/

# Expose health port
EXPOSE 8005

# Run the service
CMD ["python", "main.py"]
