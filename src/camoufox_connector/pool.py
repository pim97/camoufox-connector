"""
Browser pool management for Camoufox Connector.

Manages multiple Camoufox browser instances with round-robin load balancing.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .config import Settings
from .proxy import ProxyPool, mask_proxy_url

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
    proxy: Optional[str] = None
    active_leases: int = 0

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
            "proxy": mask_proxy_url(self.proxy),
            "active_leases": self.active_leases,
        }


@dataclass
class Lease:
    """An active reservation of a browser instance obtained via /acquire."""

    lease_id: str
    instance_index: int
    endpoint: str
    priority: int
    created_at: float
    preempted: asyncio.Event = field(default_factory=asyncio.Event)
    reclaim_task: Optional[asyncio.Task] = None

    def to_dict(self) -> dict:
        return {
            "lease_id": self.lease_id,
            "instance": self.instance_index,
            "endpoint": self.endpoint,
            "priority": self.priority,
            "age": round(time.time() - self.created_at, 2),
            "preempted": self.preempted.is_set(),
        }


@dataclass(order=True)
class _Waiter:
    """A queued /acquire request waiting for capacity.

    Ordered for the heap by (-priority, seq): higher priority first, and FIFO
    within the same priority. The future/flags are excluded from comparison.
    """

    sort_key: tuple = field(compare=True)
    priority: int = field(compare=False, default=0)
    future: asyncio.Future = field(compare=False, default=None)
    cancelled: bool = field(compare=False, default=False)
    # The lease this waiter preempted (if any), so it can be spared if this
    # waiter gives up and no other waiter still needs the reclaimed slot.
    preempt_victim: Optional[Lease] = field(compare=False, default=None)


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

    # Proxy pool (assigns a proxy per instance; empty in single/no-proxy mode).
    _proxy_pool: ProxyPool = field(default_factory=ProxyPool)

    # Priority /acquire state (guarded by _lock).
    _leases: dict[str, Lease] = field(default_factory=dict)
    _waiters: list[_Waiter] = field(default_factory=list)
    _waiter_counter: itertools.count = field(default_factory=itertools.count)
    _lease_rr_index: int = 0

    async def start(self) -> None:
        """Start all browser instances in the pool."""
        if self._running:
            logger.warning("Pool is already running")
            return

        self._running = True
        pool_size = 1 if self.settings.mode.value == "single" else self.settings.pool_size

        # Build the proxy pool (empty if no proxies configured).
        self._proxy_pool = ProxyPool(self.settings.proxy_list)
        if self._proxy_pool:
            logger.info(
                f"Proxy pool: {self._proxy_pool.size} prox"
                f"{'y' if self._proxy_pool.size == 1 else 'ies'} for {pool_size} instance(s)"
            )

        logger.info(f"Starting browser pool with {pool_size} instance(s)")

        # Create and start instances concurrently
        tasks = []
        for i in range(pool_size):
            instance = BrowserInstance(
                index=i,
                port=self.settings.get_ws_port(i),
                proxy=self._proxy_pool.assign(i),
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
            proxy_note = ""
            if instance.proxy:
                proxy_note = f" via proxy {mask_proxy_url(instance.proxy)}"
            logger.info(
                f"Starting browser instance {instance.index} on port {instance.port}{proxy_note}"
            )

            # Create the launcher script content
            launcher_code = self._generate_launcher_script(instance.port, instance.proxy)

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
                logger.info(f"Browser instance {instance.index} ready at {ws_endpoint}")
            else:
                raise RuntimeError("Failed to get WebSocket endpoint")

        except Exception as e:
            logger.error(f"Failed to start browser instance {instance.index}: {e}")
            instance.is_healthy = False
            raise

    def _generate_launcher_script(self, port: int, proxy: Optional[str] = None) -> str:
        """Generate Python script to launch Camoufox server."""
        kwargs = self.settings.to_camoufox_kwargs(proxy=proxy)
        kwargs["port"] = port

        # Build kwargs string, only including non-None values. Every value is
        # emitted via repr() so strings are safely escaped -- a proxy URL (or any
        # other string) can never break out of its literal and inject code into
        # the generated launcher source. repr(True)/repr(1)/repr(1.0) are already
        # valid Python literals, so this is uniform across types.
        kwargs_items = []
        for key, value in kwargs.items():
            if value is not None:
                kwargs_items.append(f"    {key}={value!r},")

        kwargs_str = "\n".join(kwargs_items)

        # Custom launch script that filters None values from config
        # This works around a bug in camoufox 0.4.11 where proxy=None
        # gets serialized as null and breaks the Node.js server
        script = f"""
import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

import subprocess
import base64
import orjson
from pathlib import Path
from playwright._impl._driver import compute_driver_executable
from camoufox.pkgman import LOCAL_DATA
from camoufox.utils import launch_options
from camoufox.server import to_camel_case_dict

# Get config from launch_options
config = launch_options(
{kwargs_str}
)

# Filter out None values (workaround for camoufox bug)
config = {{k: v for k, v in config.items() if v is not None}}

# Launch the server (same as camoufox.server.launch_server but with filtered config)
LAUNCH_SCRIPT = LOCAL_DATA / "launchServer.js"
nodejs, cli_path = compute_driver_executable()
driver_package_path = Path(cli_path).parent

data = orjson.dumps(to_camel_case_dict(config))

process = subprocess.Popen(
    [nodejs, str(LAUNCH_SCRIPT), driver_package_path],
    cwd=driver_package_path,
    stdin=subprocess.PIPE,
    text=True,
)
if process.stdin:
    process.stdin.write(base64.b64encode(data).decode() + "\\n")
    process.stdin.flush()

process.wait()
raise RuntimeError("Server process terminated unexpectedly")
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
                            logger.error(
                                f"Browser process exited with code {instance.process.returncode}"
                            )
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
                        if self.settings.debug or "ws://" in text.lower():
                            logger.debug(f"[Browser {instance.index}] stdout: {text}")

                        match = ws_pattern.search(text)
                        if match:
                            endpoint = match.group(0).rstrip(
                                ".,;:!?"
                            )  # Clean up trailing punctuation
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
                        if self.settings.debug or "ws://" in text.lower():
                            logger.debug(f"[Browser {instance.index}] stderr: {text}")

                        match = ws_pattern.search(text)
                        if match:
                            endpoint = match.group(0).rstrip(
                                ".,;:!?"
                            )  # Clean up trailing punctuation
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

        # Fail any queued acquirers and cancel pending preempt-reclaim tasks so
        # shutdown never hangs on an outstanding future.
        async with self._lock:
            for waiter in self._waiters:
                if waiter.future is not None and not waiter.future.done():
                    waiter.future.cancel()
            self._waiters.clear()
            for lease in list(self._leases.values()):
                if lease.reclaim_task is not None and not lease.reclaim_task.done():
                    lease.reclaim_task.cancel()
            self._leases.clear()

        tasks = [self._stop_instance(inst) for inst in self.instances]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.instances.clear()
        self._current_index = 0
        self._lease_rr_index = 0
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

    # ------------------------------------------------------------------
    # Priority acquisition API (/acquire + /release)
    #
    # This is an *opt-in* layer on top of the round-robin /next handout. A
    # client acquires a lease on a browser (optionally with a priority); when
    # every instance is at capacity, acquirers wait in a priority-ordered queue
    # so a higher-priority request is served before lower-priority ones as soon
    # as capacity frees. With preemption enabled, a higher-priority acquire can
    # reclaim a browser from a strictly-lower-priority lease.
    #
    # NOTE: the connector is an endpoint *handout* bridge -- clients connect to
    # the browser directly, so it cannot pause/resume an opaque in-flight session.
    # Preemption is therefore cooperative (the holder is asked to yield and can
    # release within a grace window) and, failing that, the browser is restarted
    # to guarantee the high-priority request gets a clean instance. /next is
    # completely unaffected by any of this.
    # ------------------------------------------------------------------

    def _find_free_instance_locked(self) -> Optional[BrowserInstance]:
        """Return a healthy instance below its lease capacity (round-robin)."""
        n = len(self.instances)
        cap = self.settings.max_concurrency_per_instance
        for k in range(n):
            idx = (self._lease_rr_index + k) % n
            inst = self.instances[idx]
            if inst.is_healthy and inst.ws_endpoint and inst.active_leases < cap:
                self._lease_rr_index = (idx + 1) % n
                return inst
        return None

    def _make_lease_locked(self, instance: BrowserInstance, priority: int) -> Lease:
        lease = Lease(
            lease_id=uuid.uuid4().hex,
            instance_index=instance.index,
            endpoint=instance.ws_endpoint,
            priority=priority,
            created_at=time.time(),
        )
        instance.active_leases += 1
        self._leases[lease.lease_id] = lease
        return lease

    def _dispatch_waiters_locked(self) -> None:
        """Hand freed capacity to the highest-priority live waiters."""
        while self._waiters:
            waiter = self._waiters[0]
            if waiter.cancelled or (waiter.future is not None and waiter.future.done()):
                heapq.heappop(self._waiters)
                continue
            inst = self._find_free_instance_locked()
            if inst is None:
                break
            heapq.heappop(self._waiters)
            lease = self._make_lease_locked(inst, waiter.priority)
            waiter.future.set_result(lease)

    def _find_preemptible_lease_locked(self, priority: int) -> Optional[Lease]:
        """Lowest-priority (then oldest) active lease strictly below ``priority``."""
        victim: Optional[Lease] = None
        for lease in self._leases.values():
            if lease.preempted.is_set():
                continue  # already scheduled for reclaim
            if lease.priority < priority:
                if (
                    victim is None
                    or lease.priority < victim.priority
                    or (lease.priority == victim.priority and lease.created_at < victim.created_at)
                ):
                    victim = lease
        return victim

    def _schedule_preempt_locked(self, victim: Lease) -> None:
        victim.preempted.set()
        victim.reclaim_task = asyncio.ensure_future(self._reclaim_after_grace(victim))
        logger.info(
            f"Preempting lease {victim.lease_id} (priority {victim.priority}) on "
            f"instance {victim.instance_index}; {self.settings.preempt_grace}s grace"
        )

    async def acquire(
        self,
        priority: int = 0,
        timeout: Optional[float] = None,
    ) -> Optional[Lease]:
        """Acquire a lease on a browser instance, honoring priority.

        Returns a :class:`Lease` on success, or ``None`` if no capacity became
        available within ``timeout`` seconds (falls back to
        ``settings.acquire_timeout`` when ``timeout`` is None). ``timeout=0``
        means do not wait: return None immediately if at capacity.
        """
        if timeout is None:
            timeout = self.settings.acquire_timeout

        async with self._lock:
            if not any(i.is_healthy and i.ws_endpoint for i in self.instances):
                return None

            inst = self._find_free_instance_locked()
            if inst is not None:
                return self._make_lease_locked(inst, priority)

            # No free capacity.
            if timeout <= 0:
                # Non-blocking request: don't preempt (that takes a grace period
                # the caller won't wait for) and don't queue -- just report busy.
                return None

            # Bound the queue so a client cannot grow pool state without limit.
            self._compact_waiters_locked()
            if sum(1 for w in self._waiters if not w.cancelled) >= self.settings.max_waiters:
                return None

            # Blocking request: optionally preempt a lower-priority lease, then
            # queue a waiter to be served when capacity frees.
            loop = asyncio.get_running_loop()
            waiter = _Waiter(
                sort_key=(-priority, next(self._waiter_counter)),
                priority=priority,
                future=loop.create_future(),
            )
            if self.settings.preemption:
                victim = self._find_preemptible_lease_locked(priority)
                if victim is not None:
                    self._schedule_preempt_locked(victim)
                    waiter.preempt_victim = victim
            heapq.heappush(self._waiters, waiter)

        try:
            return await asyncio.wait_for(asyncio.shield(waiter.future), timeout)
        except asyncio.TimeoutError:
            async with self._lock:
                self._cancel_waiter_locked(waiter)
            return None
        except asyncio.CancelledError:
            # The awaiting task was cancelled (e.g. client disconnect / shutdown).
            # Clean up, then re-raise so cancellation propagates per the contract.
            async with self._lock:
                self._cancel_waiter_locked(waiter)
            raise

    def _cancel_waiter_locked(self, waiter: _Waiter) -> None:
        """Mark a waiter cancelled; reconcile the lease/preemption it was tied to."""
        waiter.cancelled = True
        if waiter.future is not None and waiter.future.done() and not waiter.future.cancelled():
            # It was granted a lease right as we timed out -- give it back.
            lease = waiter.future.result()
            self._release_lease_locked(lease.lease_id)
            return

        # This waiter gave up without a lease. If it triggered a preemption purely
        # for itself and no other waiter still needs the reclaimed slot, spare the
        # victim: cancel the pending reclaim and un-flag it, so a lower-priority
        # session is not destroyed for a requester that already left.
        victim = waiter.preempt_victim
        waiter.preempt_victim = None
        if victim is None:
            return
        if any(not w.cancelled and w is not waiter for w in self._waiters):
            return  # another queued waiter still benefits from the reclaim
        live = self._leases.get(victim.lease_id)
        if live is not None and live.reclaim_task is not None and not live.reclaim_task.done():
            live.reclaim_task.cancel()
            live.reclaim_task = None
            live.preempted.clear()

    def _compact_waiters_locked(self) -> None:
        """Drop cancelled waiters buried in the heap so it can't grow unbounded."""
        if len(self._waiters) > 16:
            cancelled = sum(1 for w in self._waiters if w.cancelled)
            if cancelled * 2 > len(self._waiters):
                self._waiters = [w for w in self._waiters if not w.cancelled]
                heapq.heapify(self._waiters)

    async def release(self, lease_id: str) -> dict:
        """Release a lease and wake the next waiter.

        Returns ``{"released": bool, "preempted": bool}``.
        """
        async with self._lock:
            lease = self._leases.get(lease_id)
            preempted = bool(lease and lease.preempted.is_set())
            released = self._release_lease_locked(lease_id)
            self._dispatch_waiters_locked()
        return {"released": released, "preempted": preempted}

    def _release_lease_locked(self, lease_id: str) -> bool:
        lease = self._leases.pop(lease_id, None)
        if lease is None:
            return False
        inst = self.instances[lease.instance_index]
        inst.active_leases = max(0, inst.active_leases - 1)
        if lease.reclaim_task is not None and not lease.reclaim_task.done():
            lease.reclaim_task.cancel()
        return True

    def _drop_instance_leases_locked(self, index: int) -> None:
        """Invalidate every lease bound to an instance (its browser is going away)."""
        bound = [lid for lid, lease in self._leases.items() if lease.instance_index == index]
        for lease_id in bound:
            lease = self._leases.pop(lease_id)
            lease.preempted.set()
            if lease.reclaim_task is not None and not lease.reclaim_task.done():
                lease.reclaim_task.cancel()
        self.instances[index].active_leases = 0

    async def _reclaim_after_grace(self, lease: Lease) -> None:
        """After the grace period, forcibly reclaim a preempted lease's slot."""
        try:
            await asyncio.sleep(self.settings.preempt_grace)
        except asyncio.CancelledError:
            return  # holder released voluntarily within grace

        restart_needed = False
        index = lease.instance_index
        async with self._lock:
            if lease.lease_id not in self._leases:
                return  # already gone
            self._leases.pop(lease.lease_id, None)
            inst = self.instances[index]
            inst.active_leases = max(0, inst.active_leases - 1)
            # Restart only if this was the last lease on the instance, so we
            # don't nuke unrelated leases sharing a high-capacity instance.
            if self.settings.restart_on_preempt and inst.active_leases == 0:
                restart_needed = True
            else:
                self._dispatch_waiters_locked()

        if restart_needed:
            logger.info(f"Reclaiming instance {index} after preemption grace expired")
            await self.restart_instance(index)
            async with self._lock:
                self._dispatch_waiters_locked()

    def get_lease(self, lease_id: str) -> Optional[dict]:
        """Snapshot of a lease for the /lease/{id} endpoint (None if unknown)."""
        lease = self._leases.get(lease_id)
        return lease.to_dict() if lease else None

    def get_all_endpoints(self) -> list[str]:
        """Get all healthy WebSocket endpoints."""
        return [inst.ws_endpoint for inst in self.instances if inst.is_healthy and inst.ws_endpoint]

    def get_stats(self) -> dict:
        """Get pool statistics."""
        healthy = sum(1 for inst in self.instances if inst.is_healthy)
        total_connections = sum(inst.total_connections for inst in self.instances)
        active_connections = sum(inst.connections for inst in self.instances)
        active_leases = sum(inst.active_leases for inst in self.instances)
        waiting = sum(1 for w in self._waiters if not w.cancelled)

        return {
            "mode": self.settings.mode.value,
            "total_instances": len(self.instances),
            "healthy_instances": healthy,
            "active_connections": active_connections,
            "total_connections": total_connections,
            "instances": [inst.to_dict() for inst in self.instances],
            "leases": {
                "active": active_leases,
                "waiting": waiting,
                "capacity": len(self.instances) * self.settings.max_concurrency_per_instance,
                "max_per_instance": self.settings.max_concurrency_per_instance,
                "preemption": self.settings.preemption,
            },
            "proxies": self._proxy_pool.to_dict(),
        }

    async def restart_instance(
        self,
        index: int,
        rotate_proxy: bool = False,
        blacklist_proxy: bool = False,
    ) -> bool:
        """Restart a specific browser instance.

        ``rotate_proxy`` reassigns the instance to a different proxy from the
        pool on relaunch; ``blacklist_proxy`` also marks its current proxy as bad
        so it is not reused (useful when a proxy is failing).
        """
        if index < 0 or index >= len(self.instances):
            return False

        instance = self.instances[index]

        # Any leases bound to this instance die with its browser; drop them and
        # optionally rotate the proxy, all under the lock.
        async with self._lock:
            self._drop_instance_leases_locked(index)
            if (rotate_proxy or blacklist_proxy) and self._proxy_pool:
                instance.proxy = self._proxy_pool.rotate(index, blacklist_current=blacklist_proxy)

        await self._stop_instance(instance)

        # Reset instance state
        instance.ws_endpoint = None
        instance.started_at = None
        instance.connections = 0
        instance.active_leases = 0
        instance.is_healthy = False

        try:
            await self._start_instance(instance)
            ok = True
        except Exception as e:
            logger.error(f"Failed to restart instance {index}: {e}")
            ok = False

        # Freed/new capacity may satisfy queued acquirers.
        async with self._lock:
            self._dispatch_waiters_locked()
        return ok

    async def health_check(self) -> dict:
        """Perform health check on all instances."""
        results = {
            "healthy": True,
            "instances": [],
        }

        for instance in self.instances:
            instance.last_health_check = time.time()

            # Check if process is still running
            is_alive = instance.process is not None and instance.process.returncode is None

            if not is_alive and instance.is_healthy:
                logger.warning(f"Browser instance {instance.index} died unexpectedly")
                instance.is_healthy = False

            results["instances"].append(
                {
                    "index": instance.index,
                    "healthy": instance.is_healthy,
                    "endpoint": instance.ws_endpoint,
                }
            )

        results["healthy"] = any(inst.is_healthy for inst in self.instances)
        return results
