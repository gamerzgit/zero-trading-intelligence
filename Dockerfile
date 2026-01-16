# ============================================
# BEAST ENGINE - Dockerfile for Jetson Orin AGX
# ============================================
# THE ULTIMATE 0DTE TRADING INTELLIGENCE
# ============================================

# Use NVIDIA's L4T base for Jetson (JetPack compatible)
# For Jetson Orin AGX with JetPack 5.x/6.x
FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip3 install --upgrade pip setuptools wheel

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Install additional Jetson-optimized packages
# TensorRT is pre-installed in the base image
RUN pip3 install --no-cache-dir \
    onnx \
    onnxruntime

# Copy application code
COPY beast_engine.py .
COPY config.yaml .
COPY models/ ./models/

# Create logs directory
RUN mkdir -p logs

# Expose port for future HTTP API
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import beast_engine; print('OK')" || exit 1

# Default command - run the beast engine
CMD ["python3", "beast_engine.py"]

# Alternative commands:
# Single scan: CMD ["python3", "beast_engine.py", "scan"]
# Query: CMD ["python3", "beast_engine.py", "query", "SPY"]
# Morning brief: CMD ["python3", "beast_engine.py", "brief"]
