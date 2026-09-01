from __future__ import annotations

import logging
import re
import httpx
from typing import List, Dict

logger = logging.getLogger(__name__)

class GreenhouseParser:
    """
    Greenhouse ATS parser (API-based, no browser needed).
    """
    async def parse(self, target_url: str) -> List[Dict[str, str]]:
        jobs = []
        try:
            # Extract board token
            # Handles https://boards.greenhouse.io/company or https://job-boards.greenhouse.io/company
            match = re.search(r'greenhouse\.io/([^/]+)', target_url)
            if not match:
                logger.error(f"Could not extract board token from {target_url}")
                return jobs
                
            board_token = match.group(1)
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                
                for job in data.get("jobs", []):
                    jobs.append({
                        "title": job.get("title", ""),
                        "company": board_token,
                        "url": job.get("absolute_url", ""),
                        "location": job.get("location", {}).get("name", ""),
                        "description": job.get("content", "")
                    })
                    
        except Exception as e:
            logger.error(f"Error parsing Greenhouse for {target_url}: {e}")
            
        return jobs
