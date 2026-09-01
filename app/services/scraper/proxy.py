from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ProxyManager:
    def __init__(self, proxies: list[str]):
        """
        Accepts a list of proxy URLs and manages rotation.
        """
        self.proxies = [{"url": p, "failures": 0} for p in proxies if p]
        self.index = 0

    def get_next(self) -> str | None:
        """
        Round-robin rotation. Returns None if no proxies are available.
        """
        available = [p for p in self.proxies if p["failures"] < 3]
        if not available:
            return None
        
        proxy = available[self.index % len(available)]
        self.index += 1
        return proxy["url"]

    def mark_failed(self, proxy_url: str):
        """
        Track failures, remove after 3 consecutive failures.
        """
        for p in self.proxies:
            if p["url"] == proxy_url:
                p["failures"] += 1
                if p["failures"] >= 3:
                    logger.warning(f"Proxy {proxy_url} failed 3 times, removing from rotation.")
                break

    def get_playwright_proxy(self) -> dict | None:
        """
        Returns a proxy dictionary for Playwright's `proxy` param:
        {"server": "..."} or {"server": "...", "username": "...", "password": "..."}
        """
        proxy_url = self.get_next()
        if not proxy_url:
            return None

        parsed = urlparse(proxy_url)
        
        # Playwright supports http/socks5 schemes directly in the server string.
        # Ensure scheme is present.
        scheme = parsed.scheme if parsed.scheme else "http"
        host = parsed.hostname
        port = parsed.port
        
        server = f"{scheme}://{host}:{port}"
        
        proxy_dict = {"server": server}
        if parsed.username and parsed.password:
            proxy_dict["username"] = parsed.username
            proxy_dict["password"] = parsed.password
            
        return proxy_dict
