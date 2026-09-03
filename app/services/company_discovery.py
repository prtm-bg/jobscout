"""
Automatic Company Discovery Service.

Given a structured resume profile and preferred countries, uses the LLM to
discover real companies likely to be hiring for matching roles, then
auto-creates ScrapeTarget entries in the database.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import ScrapeTarget, AppConfig
from app.services.llm import call_llm

logger = logging.getLogger(__name__)

# Known ATS URL patterns → ats_type mapping
ATS_PATTERNS: list[tuple[str, str]] = [
    (r"boards\.greenhouse\.io", "greenhouse"),
    (r"job-boards\.greenhouse\.io", "greenhouse"),
    (r"jobs\.lever\.co", "lever"),
    (r"myworkdayjobs\.com", "workday"),
    (r"wd\d+\.myworkday\.com", "workday"),
]


def _detect_ats_type(url: str) -> str:
    for pattern, ats_type in ATS_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return ats_type
    return "greenhouse"  # default — most structured, safest to scrape


DISCOVERY_PROMPT = """You are an expert tech recruiter and job market analyst.

Given the candidate's profile and their preferred countries, generate a list of **real companies** that are likely hiring for roles matching this candidate's skills right now.

**RULES:**
1. Only suggest REAL companies that actually exist and are known to hire for these roles.
2. For each company, provide their ACTUAL careers page URL. Strongly prefer Greenhouse or Lever career pages if the company uses them.
   - Greenhouse URLs look like: https://boards.greenhouse.io/companyname
   - Lever URLs look like: https://jobs.lever.co/companyname
3. Include a mix of: large tech companies, well-funded startups, and mid-size companies.
4. Target companies with offices or remote positions in the specified countries.
5. Return between 15-30 companies.
6. Do NOT invent fake URLs. If unsure about the exact careers URL, use the company's main careers page.

**Candidate Profile:**
{profile_json}

**Preferred Countries:** {countries}

**Return ONLY valid JSON array — no markdown, no explanation:**
[
  {{"name": "Company Name", "careers_url": "https://boards.greenhouse.io/example"}},
  {{"name": "Another Co", "careers_url": "https://jobs.lever.co/anotherco"}}
]
"""


async def discover_companies(profile_json: str, countries: str) -> list[dict]:
    """
    Use the LLM to discover companies matching the candidate profile.
    Returns list of dicts with keys: name, careers_url, ats_type.
    """
    if not profile_json or not countries:
        logger.warning("Cannot discover companies without profile and countries.")
        return []

    prompt = DISCOVERY_PROMPT.format(profile_json=profile_json, countries=countries)

    try:
        raw = await call_llm(prompt, json_mode=True)

        # Clean markdown
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        companies = json.loads(raw)
        if not isinstance(companies, list):
            logger.error(f"Expected JSON array from LLM, got: {type(companies)}")
            return []

        # Enrich with detected ATS type
        result = []
        for entry in companies:
            name = entry.get("name", "").strip()
            url = entry.get("careers_url", "").strip()
            if name and url:
                result.append({
                    "name": name,
                    "careers_url": url,
                    "ats_type": _detect_ats_type(url),
                })

        logger.info(f"LLM discovered {len(result)} companies.")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse company discovery JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Company discovery failed: {e}")
        return []


async def auto_create_targets(companies: list[dict]) -> int:
    """
    Create ScrapeTarget entries for discovered companies, skipping duplicates.
    Returns the count of newly created targets.
    """
    created = 0
    async with async_session_factory() as session:
        for company in companies:
            # Check if target with this URL already exists
            existing = await session.execute(
                select(ScrapeTarget).where(ScrapeTarget.url == company["careers_url"])
            )
            if existing.scalars().first():
                continue

            target = ScrapeTarget(
                name=company["name"],
                url=company["careers_url"],
                ats_type=company["ats_type"],
                enabled=True,
            )
            session.add(target)
            created += 1

        if created > 0:
            await session.commit()
            logger.info(f"Auto-created {created} new scrape targets.")

    return created


async def run_discovery_pipeline() -> int:
    """
    Full discovery pipeline:
    1. Load resume profile + preferred countries from AppConfig.
    2. Call LLM to discover companies.
    3. Auto-create scrape targets.
    Returns count of new targets created.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(AppConfig).where(
                AppConfig.key.in_(["resume_profile", "preferred_countries"])
            )
        )
        configs = {c.key: c.value for c in result.scalars().all()}

    profile_json = configs.get("resume_profile", "")
    countries = configs.get("preferred_countries", "")

    if not profile_json:
        logger.warning("No resume profile found. Upload a resume first.")
        return 0
    if not countries:
        logger.warning("No preferred countries set. Set countries first.")
        return 0

    companies = await discover_companies(profile_json, countries)
    if not companies:
        return 0

    created = await auto_create_targets(companies)

    # Save last discovery timestamp
    async with async_session_factory() as session:
        from app.routers.settings import set_config
        await set_config(session, "last_discovery_at", datetime.now(timezone.utc).isoformat())

    return created
