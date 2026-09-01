from __future__ import annotations

import random
import asyncio
import logging
from typing import Tuple

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 720},
]

def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)

def get_random_viewport() -> dict:
    return random.choice(VIEWPORTS)

async def launch_stealth_browser(proxy_manager=None) -> Tuple[Playwright, Browser, BrowserContext]:
    """
    Launches a browser context with stealth baked in.
    """
    try:
        from playwright_stealth import Stealth
    except ImportError:
        logger.warning("playwright_stealth not installed. Stealth features may be limited.")
        Stealth = None

    playwright = await async_playwright().start()
    
    proxy = None
    if proxy_manager:
        proxy = proxy_manager.get_playwright_proxy()
    
    # In some stealth setups, stealth modifies the playwright instance. 
    # For robust async usage without closing the context manager prematurely,
    # we start playwright manually and apply stealth to context/page where applicable.
    
    browser = await playwright.chromium.launch(headless=True, proxy=proxy)
    
    context = await browser.new_context(
        user_agent=get_random_user_agent(),
        viewport=get_random_viewport()
    )
    
    if Stealth:
        # Applying stealth to context (v2 typical setup or fallback to page creation later)
        # We will attempt apply_stealth_async or use it globally if supported
        stealth = Stealth()
        try:
            if hasattr(stealth, "apply_stealth_async"):
                await stealth.apply_stealth_async(context)
            elif hasattr(stealth, "use_async"):
                # If it's a wrapper context manager, we might just apply it on individual pages.
                logger.info("Using playwright_stealth fallback on context.")
        except Exception as e:
            logger.error(f"Failed to apply stealth: {e}")

    return playwright, browser, context

async def random_delay(min_s: float = 1.0, max_s: float = 4.0):
    """
    Human-like random wait.
    """
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)

async def human_like_scroll(page: Page):
    """
    Scroll down incrementally with random pauses.
    """
    try:
        total_height = await page.evaluate("document.body.scrollHeight")
        current_position = 0
        
        while current_position < total_height:
            scroll_step = random.randint(300, 700)
            current_position += scroll_step
            await page.evaluate(f"window.scrollTo(0, {current_position})")
            await random_delay(0.2, 0.8)
            
            # Re-evaluate in case page grew (lazy loading)
            total_height = await page.evaluate("document.body.scrollHeight")
    except Exception as e:
        logger.warning(f"Failed to perform human_like_scroll: {e}")
