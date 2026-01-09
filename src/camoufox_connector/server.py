"""
Main server entry point for Camoufox Connector.

Provides CLI interface and orchestrates the browser pool and health API.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Optional

from .config import ServerMode, Settings
from .health import run_health_server
from .pool import BrowserPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("camoufox-connector")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="camoufox-connector",
        description="WebSocket bridge for multi-language Playwright access to Camoufox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start in single mode (default)
  camoufox-connector

  # Start with 5 browser instances
  camoufox-connector --mode pool --pool-size 5

  # Start with proxy
  camoufox-connector --proxy http://user:pass@host:port

  # Start with custom ports
  camoufox-connector --api-port 3000 --ws-port-start 9000

Environment variables:
  All options can also be set via CAMOUFOX_ prefixed environment variables.
  Example: CAMOUFOX_MODE=pool CAMOUFOX_POOL_SIZE=5
        """,
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["single", "pool"],
        default=None,
        help="Operating mode: 'single' for one browser, 'pool' for multiple (default: single)",
    )

    # Pool configuration
    parser.add_argument(
        "--pool-size",
        type=int,
        default=None,
        metavar="N",
        help="Number of browser instances in pool mode (default: 3)",
    )

    # Network configuration
    parser.add_argument(
        "--api-port",
        type=int,
        default=None,
        metavar="PORT",
        help="HTTP API port for health checks (default: 8080)",
    )

    parser.add_argument(
        "--api-host",
        type=str,
        default=None,
        metavar="HOST",
        help="Host to bind the HTTP API to (default: 0.0.0.0)",
    )

    parser.add_argument(
        "--ws-port-start",
        type=int,
        default=None,
        metavar="PORT",
        help="Starting port for browser WebSocket endpoints (default: 9222)",
    )

    # Browser configuration
    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run browsers in headless mode (default: true)",
    )

    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run browsers in headed mode",
    )

    parser.add_argument(
        "--geoip",
        action="store_true",
        default=None,
        help="Enable GeoIP-based locale/timezone spoofing (default: true)",
    )

    parser.add_argument(
        "--no-geoip",
        dest="geoip",
        action="store_false",
        help="Disable GeoIP spoofing",
    )

    parser.add_argument(
        "--humanize",
        action="store_true",
        default=None,
        help="Enable humanization features (default: true)",
    )

    parser.add_argument(
        "--no-humanize",
        dest="humanize",
        action="store_false",
        help="Disable humanization",
    )

    parser.add_argument(
        "--block-images",
        action="store_true",
        default=None,
        help="Block image loading for faster page loads",
    )

    # Proxy configuration
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        metavar="URL",
        help="Proxy URL (http://user:pass@host:port)",
    )

    # Configuration file
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="FILE",
        help="Load configuration from JSON file",
    )

    # Debug
    parser.add_argument(
        "--debug",
        action="store_true",
        default=None,
        help="Enable debug logging",
    )

    return parser.parse_args()


class Server:
    """Main server class that orchestrates browser pool and health API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: Optional[BrowserPool] = None
        self._shutdown_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start the server."""
        self._shutdown_event = asyncio.Event()

        # Create browser pool
        self.pool = BrowserPool(settings=self.settings)

        # Start browser pool
        await self.pool.start()

        # Print startup info
        self._print_startup_info()

        # Run health server (blocks until shutdown)
        try:
            await run_health_server(self.pool)
        except asyncio.CancelledError:
            logger.info("Server shutdown requested")

    def _print_startup_info(self) -> None:
        """Print server startup information."""
        if self.pool is None:
            return

        endpoints = self.pool.get_all_endpoints()

        print()
        print("=" * 60)
        print("  Camoufox Connector - Ready")
        print("=" * 60)
        print()
        print(f"  Mode:           {self.settings.mode.value}")
        print(f"  Instances:      {len(self.pool.instances)}")
        print(f"  API endpoint:   http://{self.settings.api_host}:{self.settings.api_port}")
        print()
        print("  Browser endpoints:")
        for endpoint in endpoints:
            print(f"    - {endpoint}")
        print()
        print("  API Routes:")
        print(f"    GET  /         - Server info")
        print(f"    GET  /health   - Health check")
        print(f"    GET  /next     - Get next browser (round-robin)")
        print(f"    GET  /endpoints - List all endpoints")
        print(f"    GET  /stats    - Pool statistics")
        print(f"    POST /restart/{{n}} - Restart instance N")
        print()
        print("=" * 60)
        print()

    async def stop(self) -> None:
        """Stop the server gracefully."""
        logger.info("Shutting down server...")

        if self.pool:
            await self.pool.stop()

        if self._shutdown_event:
            self._shutdown_event.set()

        logger.info("Server shutdown complete")


async def async_main(settings: Settings) -> None:
    """Async main entry point."""
    server = Server(settings)

    # Setup signal handlers
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(server.stop())

    # Register signal handlers
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    else:
        # Windows doesn't support add_signal_handler
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await server.stop()


def main() -> None:
    """Main entry point."""
    # Parse CLI arguments
    args = parse_args()

    # Build settings from CLI args and environment
    try:
        # Convert mode string to enum if provided
        if args.mode:
            args.mode = ServerMode(args.mode)

        settings = Settings.from_cli_args(args)
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Configure debug logging
    if settings.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    logger.info("Starting Camoufox Connector...")
    logger.info(f"Mode: {settings.mode.value}")

    if settings.mode == ServerMode.POOL:
        logger.info(f"Pool size: {settings.pool_size}")

    # Run the async main
    try:
        asyncio.run(async_main(settings))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
