"""
Browser pool management for Camoufox Connector.

Manages multiple Camoufox browser instances with round-robin load balancing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass
class BrowserInstance:
    """Represents a single Camoufox browser instance."""

    index: int
    port: int
    ws_endpoint: Optional[str] = None
    process: Optional[asyncio.subprocess.Process] = None
    started_at: Optional[float] = None
    connections: int = 0
    total_connections: int = 0
    is_healthy: bool = False
    last_health_check: Optional[float] = None

    @property
    def uptime(self) -> float:
        """Get uptime in seconds."""
        if self.started_at is None:
            return 0.0
        return time.time() - self.started_at

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
            "port": self.port,
            "ws_endpoint": self.ws_endpoint,
            "uptime": round(self.uptime, 2),
            "connections": self.connections,
            "total_connections": self.total_connections,
            "is_healthy": self.is_healthy,
        }


@dataclass
class BrowserPool:
    """
    Manages a pool of Camoufox browser instances.

    Provides round-robin load balancing across browser instances,
    each with its own unique fingerprint.
    """

    settings: Settings
    instances: list[BrowserInstance] = field(default_factory=list)
    _current_index: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _running: bool = False

    async def start(self) -> None:
        """Start all browser instances in the pool."""
        if self._running:
            logger.warning("Pool is already running")
            return

        self._running = True
        pool_size = 1 if self.settings.mode.value == "single" else self.settings.pool_size

        logger.info(f"Starting browser pool with {pool_size} instance(s)")

        # Create and start instances concurrently
        tasks = []
        for i in range(pool_size):
            instance = BrowserInstance(
                index=i,
                port=self.settings.get_ws_port(i),
            )
            self.instances.append(instance)
            tasks.append(self._start_instance(instance))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        failed = sum(1 for r in results if isinstance(r, Exception))
        if failed > 0:
            logger.error(f"{failed}/{pool_size} browser instances failed to start")

        healthy = sum(1 for inst in self.instances if inst.is_healthy)
        logger.info(f"Browser pool started: {healthy}/{pool_size} healthy instances")

    async def _start_instance(self, instance: BrowserInstance) -> None:
        """Start a single browser instance."""
        try:
            logger.info(f"Starting browser instance {instance.index} on port {instance.port}")

            # Create the launcher script content
            launcher_code = self._generate_launcher_script(instance.port)

            # Start the process
            if sys.platform == "win32":
                instance.process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    launcher_code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW on Windows
                )
            else:
                instance.process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    launcher_code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            instance.started_at = time.time()

            # Wait for the WebSocket endpoint to be printed
            ws_endpoint = await self._wait_for_endpoint(instance)

            if ws_endpoint:
                instance.ws_endpoint = ws_endpoint
                instance.is_healthy = True
                logger.info(
                    f"Browser instance {instance.index} ready at {ws_endpoint}"
                )
            else:
                raise RuntimeError("Failed to get WebSocket endpoint")

        except Exception as e:
            logger.error(f"Failed to start browser instance {instance.index}: {e}")
            instance.is_healthy = False
            raise

    def _generate_launcher_script(self, port: int) -> str:
        """Generate Python script to launch Camoufox server."""
        kwargs = self.settings.to_camoufox_kwargs()

        # Build the script - note: launch_server doesn't accept port parameter
        # The port is managed by Camoufox automatically
        proxy_line = f"proxy='{kwargs['proxy']}'," if kwargs.get('proxy') else ""
        
        script = f"""
import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

from camoufox.server import launch_server

launch_server(
    headless={kwargs.get('headless', True)},
    geoip={kwargs.get('geoip', True)},
    humanize={kwargs.get('humanize', True)},
    block_images={kwargs.get('block_images', False)},
    {proxy_line}
)
"""
        return script.strip()

    async def _wait_for_endpoint(
        self,
        instance: BrowserInstance,
        timeout: float = 120.0,  # Increased timeout for first startup
    ) -> Optional[str]:
        """Wait for the browser to print its WebSocket endpoint."""
        if instance.process is None:
            return None

        # Pattern to match WebSocket endpoints
        # Matches various formats:
        # - ws://127.0.0.1:9222/abc123
        # - ws://localhost:9222/abc123
        # - ws://0.0.0.0:9222/abc123
        # - ws://[::1]:9222/abc123
        ws_pattern = re.compile(r"ws://[^\s\)\"']+")

        start_time = time.time()

        # Read from both stdout and stderr concurrently
        while time.time() - start_time < timeout:
            # Check if process died
            if instance.process.returncode is not None:
                # Read remaining stderr for error info
                if instance.process.stderr:
                    try:
                        remaining = await instance.process.stderr.read()
                        error_text = remaining.decode("utf-8", errors="replace")
                        if error_text:
                            logger.error(f"Browser process exited with code {instance.process.returncode}")
                            logger.error(f"Stderr: {error_text}")
                    except Exception:
                        pass
                return None

            # Try to read from both streams
            if instance.process.stdout:
                try:
                    line = await asyncio.wait_for(
                        instance.process.stdout.readline(),
                        timeout=0.5,
                    )
                    if line:
                        text = line.decode("utf-8", errors="replace").strip()
                        # Always log in debug mode, or if it contains 'ws://'
                        if self.settings.debug or 'ws://' in text.lower():
                            logger.debug(f"[Browser {instance.index}] stdout: {text}")

                        match = ws_pattern.search(text)
                        if match:
                            endpoint = match.group(0).rstrip('.,;:!?')  # Clean up trailing punctuation
                            logger.info(f"Found endpoint in stdout: {endpoint}")
                            return endpoint
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    if self.settings.debug:
                        logger.debug(f"Error reading stdout: {e}")

            if instance.process.stderr:
                try:
                    line = await asyncio.wait_for(
                        instance.process.stderr.readline(),
                        timeout=0.5,
                    )
                    if line:
                        text = line.decode("utf-8", errors="replace").strip()
                        # Always log in debug mode, or if it contains 'ws://'
                        if self.settings.debug or 'ws://' in text.lower():
                            logger.debug(f"[Browser {instance.index}] stderr: {text}")

                        match = ws_pattern.search(text)
                        if match:
                            endpoint = match.group(0).rstrip('.,;:!?')  # Clean up trailing punctuation
                            logger.info(f"Found endpoint in stderr: {endpoint}")
                            return endpoint
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    if self.settings.debug:
                        logger.debug(f"Error reading stderr: {e}")

            # Small sleep to avoid busy waiting
            await asyncio.sleep(0.1)

        # Before giving up, try to read any remaining output for debugging
        logger.error(f"Timeout waiting for browser {instance.index} endpoint after {timeout}s")
        
        if instance.process.stdout:
            try:
                remaining = await asyncio.wait_for(instance.process.stdout.read(), timeout=1.0)
                if remaining:
                    output = remaining.decode("utf-8", errors="replace")
                    logger.error(f"Remaining stdout from browser {instance.index}:\n{output}")
            except Exception:
                pass
        
        if instance.process.stderr:
            try:
                remaining = await asyncio.wait_for(instance.process.stderr.read(), timeout=1.0)
                if remaining:
                    output = remaining.decode("utf-8", errors="replace")
                    logger.error(f"Remaining stderr from browser {instance.index}:\n{output}")
            except Exception:
                pass
        
        return None

    async def stop(self) -> None:
        """Stop all browser instances."""
        if not self._running:
            return

        logger.info("Stopping browser pool...")
        self._running = False

        tasks = [self._stop_instance(inst) for inst in self.instances]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.instances.clear()
        self._current_index = 0
        logger.info("Browser pool stopped")

    async def _stop_instance(self, instance: BrowserInstance) -> None:
        """Stop a single browser instance."""
        if instance.process is None:
            return

        try:
            instance.process.terminate()
            try:
                await asyncio.wait_for(instance.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Force killing browser instance {instance.index}")
                instance.process.kill()
                await instance.process.wait()
        except Exception as e:
            logger.error(f"Error stopping browser instance {instance.index}: {e}")

        instance.is_healthy = False
        instance.ws_endpoint = None

    async def get_next_endpoint(self) -> Optional[str]:
        """
        Get the next available WebSocket endpoint using round-robin.

        Returns:
            WebSocket endpoint URL or None if no healthy instances available.
        """
        async with self._lock:
            if not self.instances:
                return None

            # Find next healthy instance
            attempts = 0
            while attempts < len(self.instances):
                instance = self.instances[self._current_index]
                self._current_index = (self._current_index + 1) % len(self.instances)

                if instance.is_healthy and instance.ws_endpoint:
                    instance.connections += 1
                    instance.total_connections += 1
                    return instance.ws_endpoint

                attempts += 1

            return None

    def get_all_endpoints(self) -> list[str]:
        """Get all healthy WebSocket endpoints."""
        return [
            inst.ws_endpoint
            for inst in self.instances
            if inst.is_healthy and inst.ws_endpoint
        ]

    def get_stats(self) -> dict:
        """Get pool statistics."""
        healthy = sum(1 for inst in self.instances if inst.is_healthy)
        total_connections = sum(inst.total_connections for inst in self.instances)
        active_connections = sum(inst.connections for inst in self.instances)

        return {
            "mode": self.settings.mode.value,
            "total_instances": len(self.instances),
            "healthy_instances": healthy,
            "active_connections": active_connections,
            "total_connections": total_connections,
            "instances": [inst.to_dict() for inst in self.instances],
        }

    async def restart_instance(self, index: int) -> bool:
        """Restart a specific browser instance."""
        if index < 0 or index >= len(self.instances):
            return False

        instance = self.instances[index]
        await self._stop_instance(instance)

        # Reset instance state
        instance.ws_endpoint = None
        instance.started_at = None
        instance.connections = 0
        instance.is_healthy = False

        try:
            await self._start_instance(instance)
            return True
        except Exception as e:
            logger.error(f"Failed to restart instance {index}: {e}")
            return False

    async def health_check(self) -> dict:
        """Perform health check on all instances."""
        results = {
            "healthy": True,
            "instances": [],
        }

        for instance in self.instances:
            instance.last_health_check = time.time()

            # Check if process is still running
            is_alive = (
                instance.process is not None
                and instance.process.returncode is None
            )

            if not is_alive and instance.is_healthy:
                logger.warning(f"Browser instance {instance.index} died unexpectedly")
                instance.is_healthy = False

            results["instances"].append({
                "index": instance.index,
                "healthy": instance.is_healthy,
                "endpoint": instance.ws_endpoint,
            })

        results["healthy"] = any(inst.is_healthy for inst in self.instances)
        return results
