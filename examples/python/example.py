"""
Camoufox Connector - Python Example

This example demonstrates how to connect to Camoufox from Python
using Playwright's remote connection feature.

Prerequisites:
    pip install playwright httpx

Start the connector server first:
    camoufox-connector --mode pool --pool-size 3
"""

import asyncio
import os
from typing import Optional

import httpx
from playwright.async_api import async_playwright

API_URL = os.getenv("CAMOUFOX_API", "http://localhost:8080")


async def get_next_endpoint() -> str:
    """Get the next available browser endpoint using round-robin."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/next")
        response.raise_for_status()
        return response.json()["endpoint"]


async def get_all_endpoints() -> list[str]:
    """Get all available browser endpoints."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/endpoints")
        response.raise_for_status()
        return response.json()["endpoints"]


async def check_health() -> bool:
    """Check if the server is healthy."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/health")
            data = response.json()
            print(f"Server health: {data}")
            return data["status"] == "healthy"
        except Exception as e:
            print(f"Health check failed: {e}")
            return False


async def basic_example():
    """Basic example: Connect and navigate to a page."""
    print("\n=== Basic Example ===\n")

    # Get a browser endpoint using round-robin
    endpoint = await get_next_endpoint()
    print(f"Connecting to: {endpoint}")

    async with async_playwright() as p:
        # Connect to Camoufox via WebSocket
        browser = await p.firefox.connect(endpoint)

        try:
            # Create a new page
            page = await browser.new_page()

            # Navigate to a test page
            await page.goto("https://httpbin.org/headers")

            # Get page content
            content = await page.text_content("body")
            print(f"Response: {content}")

            # Take a screenshot
            await page.screenshot(path="screenshot.png")
            print("Screenshot saved to screenshot.png")

        finally:
            # Close the connection (not the browser, it stays running)
            await browser.close()


async def pool_example():
    """Pool example: Distribute work across multiple browsers."""
    print("\n=== Pool Example ===\n")

    urls = [
        "https://httpbin.org/ip",
        "https://httpbin.org/user-agent",
        "https://httpbin.org/headers",
        "https://httpbin.org/get",
        "https://httpbin.org/cookies",
    ]

    async def process_url(url: str) -> dict:
        """Process a single URL using a browser from the pool."""
        # Each call to /next gets the next browser in rotation
        endpoint = await get_next_endpoint()
        print(f"Processing {url} via {endpoint}")

        async with async_playwright() as p:
            browser = await p.firefox.connect(endpoint)

            try:
                page = await browser.new_page()
                await page.goto(url)

                content = await page.text_content("body")
                return {"url": url, "content": content[:100] + "..."}

            finally:
                await browser.close()

    # Process URLs in parallel
    results = await asyncio.gather(*[process_url(url) for url in urls])

    print("\nResults:")
    for result in results:
        print(f"  {result['url']}: {result['content']}")


async def session_example():
    """Session persistence example."""
    print("\n=== Session Example ===\n")

    # Get all endpoints and pick one for persistent session
    endpoints = await get_all_endpoints()
    endpoint = endpoints[0]

    print(f"Using fixed endpoint for session: {endpoint}")

    async with async_playwright() as p:
        # First connection: set a cookie
        browser = await p.firefox.connect(endpoint)
        page = await browser.new_page()

        await page.goto("https://httpbin.org/cookies/set/session/abc123")
        print("Session cookie set")

        await browser.close()

        # Second connection: verify cookie persists
        browser = await p.firefox.connect(endpoint)
        page = await browser.new_page()

        await page.goto("https://httpbin.org/cookies")
        cookies = await page.text_content("body")
        print(f"Cookies in second connection: {cookies}")

        await browser.close()


async def main():
    """Main execution."""
    try:
        # Check if server is healthy
        healthy = await check_health()

        if not healthy:
            print("Server is not healthy. Please start the connector first.")
            return

        # Run examples
        await basic_example()
        await pool_example()
        await session_example()

        print("\n✓ All examples completed successfully!\n")

    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
