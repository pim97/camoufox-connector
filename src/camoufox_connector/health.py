"""
HTTP Health Check API for Camoufox Connector.

Provides endpoints for health monitoring and browser pool management.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

if TYPE_CHECKING:
    from .pool import BrowserPool

logger = logging.getLogger(__name__)


def create_health_app(pool: BrowserPool) -> Starlette:
    """
    Create a Starlette application for health checks and management.

    Args:
        pool: Browser pool instance to monitor

    Returns:
        Starlette application instance
    """

    async def health(request: Request) -> Response:
        """
        Health check endpoint.

        Returns 200 if at least one browser is healthy, 503 otherwise.
        """
        health_status = await pool.health_check()

        status_code = 200 if health_status["healthy"] else 503

        return JSONResponse(
            {
                "status": "healthy" if health_status["healthy"] else "unhealthy",
                "mode": pool.settings.mode.value,
                "instances": health_status["instances"],
            },
            status_code=status_code,
        )

    async def endpoints(request: Request) -> Response:
        """
        Get available WebSocket endpoints.

        Returns a list of all healthy browser endpoints.
        """
        all_endpoints = pool.get_all_endpoints()

        return JSONResponse({
            "endpoints": all_endpoints,
            "count": len(all_endpoints),
        })

    async def next_endpoint(request: Request) -> Response:
        """
        Get the next available endpoint using round-robin.

        This is the primary endpoint for clients to get a browser.
        """
        endpoint = await pool.get_next_endpoint()

        if endpoint is None:
            return JSONResponse(
                {"error": "No healthy browser instances available"},
                status_code=503,
            )

        return JSONResponse({
            "endpoint": endpoint,
        })

    async def stats(request: Request) -> Response:
        """
        Get detailed pool statistics.

        Returns connection counts, uptime, and instance details.
        """
        return JSONResponse(pool.get_stats())

    async def restart_instance(request: Request) -> Response:
        """
        Restart a specific browser instance.

        POST /restart/{index}
        """
        try:
            index = int(request.path_params["index"])
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": "Invalid instance index"},
                status_code=400,
            )

        success = await pool.restart_instance(index)

        if success:
            return JSONResponse({
                "status": "restarted",
                "index": index,
            })
        else:
            return JSONResponse(
                {"error": f"Failed to restart instance {index}"},
                status_code=500,
            )

    async def info(request: Request) -> Response:
        """
        Get server information and configuration.
        """
        from . import __version__

        return JSONResponse({
            "name": "camoufox-connector",
            "version": __version__,
            "mode": pool.settings.mode.value,
            "pool_size": len(pool.instances),
            "config": {
                "headless": pool.settings.headless,
                "geoip": pool.settings.geoip,
                "humanize": pool.settings.humanize,
                "block_images": pool.settings.block_images,
                "proxy": "configured" if pool.settings.proxy else None,
            },
        })

    routes = [
        Route("/", info, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/endpoints", endpoints, methods=["GET"]),
        Route("/next", next_endpoint, methods=["GET"]),
        Route("/stats", stats, methods=["GET"]),
        Route("/restart/{index:int}", restart_instance, methods=["POST"]),
    ]

    app = Starlette(
        debug=pool.settings.debug,
        routes=routes,
    )

    return app


async def run_health_server(pool: BrowserPool) -> None:
    """
    Run the health check HTTP server.

    Args:
        pool: Browser pool instance to monitor
    """
    import uvicorn

    app = create_health_app(pool)

    config = uvicorn.Config(
        app,
        host=pool.settings.api_host,
        port=pool.settings.api_port,
        log_level="info" if pool.settings.debug else "warning",
        access_log=pool.settings.debug,
    )

    server = uvicorn.Server(config)
    await server.serve()
