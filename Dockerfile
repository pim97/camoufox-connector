# Camoufox Connector - Multi-stage Docker build
# Apify + Python + Playwright + Camoufox base image
FROM apify/actor-python-playwright-camoufox:latest

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download camoufox browser binaries to avoid runtime downloads
# This prevents multiple pool instances from downloading simultaneously
# It is redundant but a nice fallback in case the base image is outdated
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

# Reset the path to entrypoint script in base image
ENTRYPOINT ["/usr/src/app/xvfb-entrypoint.sh"]

# Run with xvfb for headless support
CMD ["python", "-m", "camoufox_connector.server"]
