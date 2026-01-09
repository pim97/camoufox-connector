#!/bin/bash
# Camoufox Connector - cURL/Shell Examples
#
# This script demonstrates how to interact with the Camoufox Connector API
# using cURL. Useful for testing and simple integrations.
#
# Start the connector server first:
#   camoufox-connector --mode pool --pool-size 3

API_URL="${CAMOUFOX_API:-http://localhost:8080}"

echo "=== Camoufox Connector API Examples ==="
echo "API URL: $API_URL"
echo

# Check health
echo "=== Health Check ==="
curl -s "$API_URL/health" | jq .
echo

# Get server info
echo "=== Server Info ==="
curl -s "$API_URL/" | jq .
echo

# Get next endpoint (round-robin)
echo "=== Get Next Endpoint ==="
ENDPOINT=$(curl -s "$API_URL/next" | jq -r '.endpoint')
echo "Endpoint: $ENDPOINT"
echo

# Get all endpoints
echo "=== All Endpoints ==="
curl -s "$API_URL/endpoints" | jq .
echo

# Get statistics
echo "=== Pool Statistics ==="
curl -s "$API_URL/stats" | jq .
echo

# Demonstrate round-robin by getting multiple endpoints
echo "=== Round-Robin Demo (5 requests) ==="
for i in {1..5}; do
    ENDPOINT=$(curl -s "$API_URL/next" | jq -r '.endpoint')
    echo "Request $i: $ENDPOINT"
done
echo

echo "=== Examples Complete ==="
echo
echo "To connect to a browser, use the WebSocket endpoint with Playwright:"
echo "  playwright.firefox.connect('$ENDPOINT')"
