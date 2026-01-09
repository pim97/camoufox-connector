# Camoufox Connector

**WebSocket bridge for multi-language Playwright access to Camoufox anti-detect browser**

Connect to [Camoufox](https://github.com/daijro/camoufox) from **any programming language** that has Playwright bindings - Node.js, Go, Java, .NET, Python, and more.

---

## Sponsored by Scrappey

[![Scrappey - Web Scraping API](https://scrappey.com/scrape.png)](https://scrappey.com/)

**Tired of getting blocked while scraping the web?**

Rotating proxies, Anti-Bot technology and headless browsers to CAPTCHAs. It's never been this easy using our simple-to-use API.

👉 **[Try Scrappey for free](https://scrappey.com/)**

---

## Why Camoufox Connector?

Camoufox is a powerful anti-detect browser based on Firefox, but its Python-only interface limits accessibility. Camoufox Connector solves this by:

- **Exposing WebSocket endpoints** that any Playwright client can connect to
- **Managing browser pools** for high-volume scraping with fingerprint rotation
- **Providing health monitoring** via HTTP API
- **Simplifying deployment** with Docker support

## Features

- **Multi-language support** - Connect from Node.js, Go, Python, Java, .NET, or any Playwright-compatible language
- **Single & Pool modes** - One persistent browser or multiple rotating browsers
- **Round-robin load balancing** - Distribute connections across browser instances
- **Fingerprint rotation** - Each browser instance has a unique fingerprint
- **Health check API** - Monitor browser health and statistics
- **Docker ready** - Production-ready containerization
- **High performance** - Async architecture optimized for concurrent connections

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/pim97/camoufox-connector.git
cd camoufox-connector

# Install with pip
pip install -e .

# Or install from PyPI (when published)
pip install camoufox-connector
```

### Start the Server

```bash
# Single browser mode (default)
camoufox-connector

# Pool mode with 5 browsers
camoufox-connector --mode pool --pool-size 5

# With proxy
camoufox-connector --proxy http://user:pass@host:port
```

### Connect from Node.js

```javascript
import { firefox } from 'playwright';

// Get endpoint from the connector API
const response = await fetch('http://localhost:8080/next');
const { endpoint } = await response.json();

// Connect to Camoufox
const browser = await firefox.connect(endpoint);
const page = await browser.newPage();

await page.goto('https://example.com');
console.log(await page.title());

await browser.close();
```

### Connect from Go

```go
package main

import (
    "github.com/playwright-community/playwright-go"
)

func main() {
    pw, _ := playwright.Run()
    defer pw.Stop()
    
    // Get endpoint from connector API
    // endpoint := getEndpointFromAPI()
    endpoint := "ws://localhost:9222/abc123"
    
    browser, _ := pw.Firefox.Connect(endpoint)
    page, _ := browser.NewPage()
    
    page.Goto("https://example.com")
    title, _ := page.Title()
    println(title)
    
    browser.Close()
}
```

### Connect from Python

```python
import httpx
from playwright.async_api import async_playwright

async def main():
    # Get endpoint from connector API
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8080/next")
        endpoint = response.json()["endpoint"]
    
    async with async_playwright() as p:
        browser = await p.firefox.connect(endpoint)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        print(await page.title())
        
        await browser.close()
```

## Operating Modes

### Single Mode (Default)

One browser instance with a consistent fingerprint. Ideal for:
- Maintaining logged-in sessions
- Sequential scraping tasks
- Development and testing

```bash
camoufox-connector --mode single
```

### Pool Mode

Multiple browser instances with different fingerprints, distributed via round-robin. Ideal for:
- High-volume scraping
- Avoiding detection through fingerprint rotation
- Parallel processing

```bash
camoufox-connector --mode pool --pool-size 5
```

> **Note:** Since each browser instance maintains its own fingerprint, use pool mode when you need fingerprint rotation between requests. Use single mode when you need session persistence.

## HTTP API

The connector exposes an HTTP API for health monitoring and browser management.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Server info and version |
| `/health` | GET | Health check (returns 200/503) |
| `/next` | GET | Get next browser endpoint (round-robin) |
| `/endpoints` | GET | List all available endpoints |
| `/stats` | GET | Pool statistics and connection counts |
| `/restart/{n}` | POST | Restart browser instance N |

### Example API Responses

**GET /next**
```json
{
  "endpoint": "ws://localhost:9222/abc123def456"
}
```

**GET /health**
```json
{
  "status": "healthy",
  "mode": "pool",
  "instances": [
    {"index": 0, "healthy": true, "endpoint": "ws://..."},
    {"index": 1, "healthy": true, "endpoint": "ws://..."},
    {"index": 2, "healthy": true, "endpoint": "ws://..."}
  ]
}
```

**GET /stats**
```json
{
  "mode": "pool",
  "total_instances": 3,
  "healthy_instances": 3,
  "active_connections": 5,
  "total_connections": 142,
  "instances": [
    {"index": 0, "uptime": 3600.5, "connections": 2, "total_connections": 48},
    {"index": 1, "uptime": 3600.3, "connections": 2, "total_connections": 47},
    {"index": 2, "uptime": 3600.1, "connections": 1, "total_connections": 47}
  ]
}
```

## Configuration

### Command Line Options

```
Usage: camoufox-connector [OPTIONS]

Options:
  --mode {single,pool}   Operating mode (default: single)
  --pool-size N          Number of browser instances in pool mode (default: 3)
  --api-port PORT        HTTP API port (default: 8080)
  --api-host HOST        HTTP API host (default: 0.0.0.0)
  --ws-port-start PORT   Starting port for WebSocket endpoints (default: 9222)
  --headless             Run browsers in headless mode (default)
  --no-headless          Run browsers in headed mode
  --geoip                Enable GeoIP spoofing (default)
  --no-geoip             Disable GeoIP spoofing
  --humanize             Enable humanization (default)
  --no-humanize          Disable humanization
  --block-images         Block image loading
  --proxy URL            Proxy URL (http://user:pass@host:port)
  --config FILE          Load configuration from JSON file
  --debug                Enable debug logging
```

### Environment Variables

All options can be set via `CAMOUFOX_` prefixed environment variables:

```bash
export CAMOUFOX_MODE=pool
export CAMOUFOX_POOL_SIZE=5
export CAMOUFOX_HEADLESS=true
export CAMOUFOX_PROXY=http://user:pass@host:port

camoufox-connector
```

### JSON Configuration

```json
{
  "mode": "pool",
  "pool_size": 5,
  "headless": true,
  "geoip": true,
  "humanize": true,
  "proxy": "http://user:pass@host:port"
}
```

```bash
camoufox-connector --config config.json
```

## Docker

### Quick Start with Docker

```bash
# Build the image
docker build -t camoufox-connector .

# Run in single mode
docker run -p 8080:8080 -p 9222:9222 camoufox-connector

# Run in pool mode
docker run -p 8080:8080 -p 9222-9230:9222-9230 \
  -e CAMOUFOX_MODE=pool \
  -e CAMOUFOX_POOL_SIZE=5 \
  --shm-size=4gb \
  camoufox-connector
```

### Docker Compose

```bash
# Single mode
docker compose up

# Pool mode
docker compose --profile pool up
```

### Custom docker-compose.yml

```yaml
services:
  camoufox:
    build: .
    ports:
      - "8080:8080"
      - "9222-9230:9222-9230"
    environment:
      - CAMOUFOX_MODE=pool
      - CAMOUFOX_POOL_SIZE=5
      - CAMOUFOX_HEADLESS=true
    shm_size: 4gb
    restart: unless-stopped
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Client Applications                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────────┐ │
│  │ Node.js │  │   Go    │  │  Java   │  │  Other Playwright   │ │
│  │Playwright│  │Playwright│  │Playwright│  │     Clients        │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └──────────┬──────────┘ │
└───────┼────────────┼────────────┼───────────────────┼───────────┘
        │            │            │                   │
        └────────────┴────────────┴───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   HTTP API :8080   │
                    │  GET /next (RR)    │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Camoufox 1   │   │  Camoufox 2   │   │  Camoufox N   │
│  WS :9222     │   │  WS :9223     │   │  WS :922X     │
│  Fingerprint A│   │  Fingerprint B│   │  Fingerprint N│
└───────────────┘   └───────────────┘   └───────────────┘
```

## Use Cases

### High-Volume Web Scraping

```javascript
// Distribute scraping across multiple fingerprints
async function scrapeUrls(urls) {
  const results = await Promise.all(urls.map(async (url) => {
    // Each request gets a different browser/fingerprint
    const { endpoint } = await fetch('http://localhost:8080/next').then(r => r.json());
    const browser = await firefox.connect(endpoint);
    
    try {
      const page = await browser.newPage();
      await page.goto(url);
      return await page.content();
    } finally {
      await browser.close();
    }
  }));
  
  return results;
}
```

### Session Persistence

```javascript
// Use a specific endpoint for session persistence
const { endpoints } = await fetch('http://localhost:8080/endpoints').then(r => r.json());
const sessionEndpoint = endpoints[0];  // Always use the same browser

// Login once
let browser = await firefox.connect(sessionEndpoint);
let page = await browser.newPage();
await page.goto('https://example.com/login');
// ... perform login
await browser.close();

// Subsequent requests use the same session
browser = await firefox.connect(sessionEndpoint);
page = await browser.newPage();
await page.goto('https://example.com/dashboard');  // Already logged in
```

### Load Balancing with Health Checks

```javascript
async function getHealthyEndpoint() {
  const health = await fetch('http://localhost:8080/health').then(r => r.json());
  
  if (health.status !== 'healthy') {
    throw new Error('No healthy browsers available');
  }
  
  const { endpoint } = await fetch('http://localhost:8080/next').then(r => r.json());
  return endpoint;
}
```

## Performance Tips

1. **Use pool mode for parallel tasks** - Each browser instance can handle multiple pages concurrently
2. **Set appropriate pool size** - Rule of thumb: 1-2 browsers per CPU core
3. **Enable `--block-images`** - Significantly speeds up page loads for text-based scraping
4. **Use `--headless`** - Reduces memory and CPU usage
5. **Monitor with `/stats`** - Watch connection distribution and adjust pool size accordingly

## Troubleshooting

### Browser fails to start

```bash
# Check if Camoufox is installed
python -c "from camoufox.sync_api import Camoufox; print('OK')"

# Install if missing
pip install camoufox
python -m playwright install firefox
```

### Connection refused

```bash
# Check if server is running
curl http://localhost:8080/health

# Check if browser WebSocket is accessible
curl -I ws://localhost:9222
```

### Out of memory in Docker

```bash
# Increase shared memory (required for browsers)
docker run --shm-size=2gb camoufox-connector
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

- [Camoufox](https://github.com/daijro/camoufox) - The anti-detect browser this project wraps
- [Playwright](https://playwright.dev/) - Browser automation framework
- [node-camoufox](https://github.com/DemonMartin/node-camoufox) - Inspiration for this project

## Links

- [Camoufox Documentation](https://camoufox.com/)
- [Playwright Documentation](https://playwright.dev/docs/intro)
- [GitHub Repository](https://github.com/pim97/camoufox-connector)
