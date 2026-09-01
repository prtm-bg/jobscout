from __future__ import annotations

import asyncio
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class WorkdayParser:
    """
    Workday ATS parser (browser-based with XHR interception).
    """
    async def parse(self, target_url: str, page=None) -> List[Dict[str, str]]:
        jobs = []
        if not page:
            logger.error("WorkdayParser requires a Playwright page instance.")
            return jobs
            
        try:
            intercepted_data = []

            async def handle_route(route, request):
                if "/jobs" in request.url or "/search" in request.url:
                    try:
                        # Continue request, capture response
                        response = await route.fetch()
                        if response.ok:
                            json_data = await response.json()
                            intercepted_data.append(json_data)
                        await route.fulfill(response=response)
                    except Exception as e:
                        logger.error(f"Error handling route {request.url}: {e}")
                        await route.continue_()
                else:
                    await route.continue_()

            # Set up interception
            await page.route("**/*", handle_route)
            
            # Navigate to the page
            await page.goto(target_url, wait_until="networkidle")
            
            # Additional wait to ensure dynamic data is loaded
            await asyncio.sleep(5)
            
            for data in intercepted_data:
                # Workday JSON response structures vary, but typically have job postings in lists
                # Looking for standard Workday generic API structure
                postings = data.get("jobPostings", [])
                if not postings and "body" in data and isinstance(data["body"], dict):
                    postings = data["body"].get("children", [{}])[0].get("children", [{}])[0].get("listItems", [])
                
                for item in postings:
                    # Safely handle different workday payload structures
                    title = item.get("title", "")
                    url = target_url
                    if "externalPath" in item:
                        # Usually append to target_url base
                        base_url = "/".join(target_url.split("/")[:3])
                        url = f"{base_url}{item['externalPath']}"
                        
                    location = item.get("locationsText", "")
                    
                    if title:
                        jobs.append({
                            "title": title,
                            "company": "Workday Target", # Can be extracted or overridden
                            "url": url,
                            "location": location,
                            "description": "" # Workday list usually doesn't have full description
                        })

            # Clean up route
            await page.unroute("**/*")
            
        except Exception as e:
            logger.error(f"Error parsing Workday for {target_url}: {e}")
            
        return jobs
