"""
Camoufox Connector - WebSocket Bridge for Multi-Language Playwright Access

Connect to Camoufox anti-detect browser from any programming language
via Playwright's remote protocol.
"""

__version__ = "1.0.1"
__author__ = "Scrappey"

from .config import Settings
from .pool import BrowserPool, BrowserInstance
from .health import create_health_app
from .server import main

__all__ = [
    "Settings",
    "BrowserPool",
    "BrowserInstance",
    "create_health_app",
    "main",
    "__version__",
]
