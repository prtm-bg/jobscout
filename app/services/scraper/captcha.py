from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

async def detect_captcha(page) -> Dict[str, str] | None:
    """
    Check for CAPTCHAs on the page.
    """
    try:
        # Cloudflare Turnstile
        if await page.locator("iframe[src*='challenges.cloudflare.com'], #cf-turnstile, div.cf-turnstile").count() > 0:
            logger.info("Detected Cloudflare Turnstile.")
            sitekey = await page.evaluate("document.querySelector('div.cf-turnstile')?.getAttribute('data-sitekey')")
            if not sitekey:
                sitekey = "turnstile_sitekey_placeholder"
            return {"type": "turnstile", "sitekey": sitekey}
            
        # reCAPTCHA
        if await page.locator("iframe[src*='google.com/recaptcha'], .g-recaptcha").count() > 0:
            logger.info("Detected Google reCAPTCHA.")
            sitekey = await page.evaluate("document.querySelector('.g-recaptcha')?.getAttribute('data-sitekey')")
            return {"type": "recaptcha", "sitekey": sitekey}
            
        # hCaptcha
        if await page.locator("iframe[src*='hcaptcha.com'], .h-captcha").count() > 0:
            logger.info("Detected hCaptcha.")
            sitekey = await page.evaluate("document.querySelector('.h-captcha')?.getAttribute('data-sitekey')")
            return {"type": "hcaptcha", "sitekey": sitekey}
            
        # DataDome
        if await page.locator("iframe[src*='datadome']").count() > 0 or "datadome" in await page.content():
            logger.info("Detected DataDome.")
            return {"type": "datadome", "sitekey": None}
            
    except Exception as e:
        logger.error(f"Error detecting captcha: {e}")
        
    return None

async def solve_captcha(captcha_info: dict, page_url: str) -> str | None:
    """
    Solve CAPTCHA based on configured provider.
    """
    provider = settings.CAPTCHA_PROVIDER
    api_key = settings.CAPTCHA_API_KEY
    
    if not provider or not api_key:
        logger.warning("No CAPTCHA provider or API key configured.")
        return None
        
    sitekey = captcha_info.get("sitekey")
    captcha_type = captcha_info.get("type")
    
    if not sitekey and captcha_type != "datadome":
        logger.error("Missing sitekey for captcha.")
        return None
        
    if provider == "2captcha":
        try:
            from twocaptcha import TwoCaptcha
            solver = TwoCaptcha(api_key)
            
            def solve_2captcha():
                if captcha_type == "turnstile":
                    return solver.turnstile(sitekey=sitekey, url=page_url)
                elif captcha_type == "recaptcha":
                    return solver.recaptcha(sitekey=sitekey, url=page_url)
                elif captcha_type == "hcaptcha":
                    return solver.hcaptcha(sitekey=sitekey, url=page_url)
                return None
                
            result = await asyncio.to_thread(solve_2captcha)
            if result and "code" in result:
                return result["code"]
        except Exception as e:
            logger.error(f"2Captcha solving failed: {e}")
            
    elif provider == "capsolver":
        try:
            import capsolver
            capsolver.api_key = api_key
            
            def solve_capsolver():
                if captcha_type == "turnstile":
                    return capsolver.solve({
                        "type": "AntiCloudflareTask",
                        "websiteURL": page_url,
                        "websiteKey": sitekey
                    })
                elif captcha_type == "recaptcha":
                    return capsolver.solve({
                        "type": "ReCaptchaV2TaskProxyless",
                        "websiteURL": page_url,
                        "websiteKey": sitekey
                    })
                elif captcha_type == "hcaptcha":
                    return capsolver.solve({
                        "type": "HCaptchaTaskProxyless",
                        "websiteURL": page_url,
                        "websiteKey": sitekey
                    })
                return None
                
            result = await asyncio.to_thread(solve_capsolver)
            if result and "gRecaptchaResponse" in result:
                return result["gRecaptchaResponse"]
            if result and "token" in result:
                return result["token"]
        except Exception as e:
            logger.error(f"CapSolver solving failed: {e}")
            
    return None

import httpx

async def solve_with_flaresolverr(url: str) -> dict | None:
    """
    Use FlareSolverr to bypass Cloudflare protection and return cookies/html.
    Returns: dict with 'cookies' (list) and 'html' (str)
    """
    if not settings.FLARESOLVERR_URL:
        return None
        
    logger.info(f"Attempting to solve Cloudflare for {url} using FlareSolverr...")
    
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.FLARESOLVERR_URL,
                json=payload,
                timeout=70.0
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "ok":
                logger.info("FlareSolverr successfully bypassed Cloudflare.")
                return {
                    "cookies": data.get("solution", {}).get("cookies", []),
                    "html": data.get("solution", {}).get("response", "")
                }
            else:
                logger.warning(f"FlareSolverr failed: {data.get('message')}")
                return None
    except Exception as e:
        logger.error(f"FlareSolverr request error: {e}")
        return None

async def inject_captcha_solution(page, captcha_info: dict, token: str):
    """
    Inject solved token into the page via JavaScript.
    """
    captcha_type = captcha_info.get("type")
    try:
        if captcha_type == "turnstile":
            await page.evaluate(f"document.querySelector('[name=cf-turnstile-response]').value = '{token}';")
            # Usually needs form submission or JS callback
            logger.info("Injected Turnstile token.")
        elif captcha_type == "recaptcha":
            await page.evaluate(f"document.getElementById('g-recaptcha-response').value = '{token}';")
            # If callback exists, try to invoke it
            await page.evaluate("""
                if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients !== 'undefined') {
                    for (var key in ___grecaptcha_cfg.clients) {
                        if (___grecaptcha_cfg.clients[key].hasOwnProperty('callback')) {
                            ___grecaptcha_cfg.clients[key].callback();
                        }
                    }
                }
            """)
            logger.info("Injected reCAPTCHA token.")
        elif captcha_type == "hcaptcha":
            await page.evaluate(f"document.getElementsByName('h-captcha-response')[0].value = '{token}';")
            logger.info("Injected hCaptcha token.")
            
    except Exception as e:
        logger.error(f"Failed to inject captcha solution: {e}")
