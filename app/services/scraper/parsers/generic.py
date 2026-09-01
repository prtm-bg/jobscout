from __future__ import annotations

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class GenericParser:
    """
    Generic career page parser (browser DOM extraction).
    """
    async def parse(self, target_url: str, page=None, custom_selectors: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
        jobs = []
        if not page:
            logger.error("GenericParser requires a Playwright page instance.")
            return jobs
            
        try:
            await page.goto(target_url, wait_until="networkidle")
            
            selectors = custom_selectors or {}
            
            # Default selectors
            job_card_selectors = selectors.get("job_card", "a[href*='job'], a[href*='career'], a[href*='position'], .job-listing, .job-card, [data-job], article").split(",")
            title_selectors = selectors.get("title", "h2, h3, .title, .job-title").split(",")
            
            cards = []
            # Try to find the first job card selector that yields results
            for js in job_card_selectors:
                elements = await page.locator(js.strip()).all()
                if elements:
                    cards = elements
                    break
                    
            seen_urls = set()
            
            for card in cards:
                try:
                    # URL extraction
                    url = selectors.get("url")
                    if url:
                        href = await card.locator(url).get_attribute("href")
                    else:
                        href = await card.get_attribute("href")
                        if not href:
                            href = await card.locator("a").first.get_attribute("href")
                            
                    if not href:
                        continue
                        
                    # Title extraction
                    title = ""
                    for ts in title_selectors:
                        try:
                            title_el = await card.locator(ts.strip()).first.text_content()
                            if title_el:
                                title = title_el.strip()
                                break
                        except Exception:
                            continue
                            
                    if not title:
                        title = await card.text_content()
                        title = title.strip().split("\n")[0] if title else "Unknown Title"
                    
                    full_url = href if href.startswith("http") else f"{target_url.rstrip('/')}/{href.lstrip('/')}"
                    
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    
                    jobs.append({
                        "title": title,
                        "company": selectors.get("company", "Unknown"),
                        "url": full_url,
                        "location": selectors.get("location", ""),
                        "description": selectors.get("description", "")
                    })
                except Exception as card_error:
                    logger.debug(f"Error parsing generic job card: {card_error}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing Generic target for {target_url}: {e}")
            
        return jobs
