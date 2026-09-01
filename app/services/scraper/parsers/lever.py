from __future__ import annotations

import logging
import re
import httpx
from typing import List, Dict

logger = logging.getLogger(__name__)

class LeverParser:
    """
    Lever ATS parser (API-based).
    """
    async def parse(self, target_url: str) -> List[Dict[str, str]]:
        jobs = []
        try:
            # Extract company token
            match = re.search(r'jobs\.lever\.co/([^/]+)', target_url)
            if not match:
                logger.error(f"Could not extract company from {target_url}")
                return jobs
                
            company = match.group(1)
            api_url = f"https://api.lever.co/v0/postings/{company}?mode=json"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                
                for job in data:
                    location = job.get("categories", {}).get("location", "")
                    team = job.get("categories", {}).get("team", "")
                    loc_team = f"{location} - {team}".strip(" -")
                    
                    jobs.append({
                        "title": job.get("text", ""),
                        "company": company,
                        "url": job.get("hostedUrl", ""),
                        "location": loc_team,
                        "description": job.get("descriptionPlain", "")
                    })
                    
        except Exception as e:
            logger.error(f"Error parsing Lever for {target_url}: {e}")
            
        return jobs
