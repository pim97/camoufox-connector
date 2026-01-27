# Camoufox Connector - Multi-stage Docker build
# Base image with Python and system dependencies

FROM python:3.11-slim as base

# Install system dependencies for browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download camoufox browser binaries to avoid runtime downloads
# This prevents multiple pool instances from downloading simultaneously
RUN camoufox fetch

# Install the application
COPY . .
RUN pip install --no-cache-dir -e .

# Expose ports
# 8080: HTTP API
# 9222-9230: WebSocket endpoints for browsers
EXPOSE 8080
EXPOSE 9222-9230

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default environment variables
ENV CAMOUFOX_MODE=single \
    CAMOUFOX_POOL_SIZE=3 \
    CAMOUFOX_API_PORT=8080 \
    CAMOUFOX_API_HOST=0.0.0.0 \
    CAMOUFOX_WS_PORT_START=9222 \
    CAMOUFOX_HEADLESS=true \
    CAMOUFOX_GEOIP=true \
    CAMOUFOX_HUMANIZE=true \
    CAMOUFOX_BLOCK_IMAGES=false

# Run with xvfb for headless support
ENTRYPOINT ["python", "-m", "camoufox_connector.server"]
