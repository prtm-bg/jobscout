import json
import logging
import httpx
from typing import Tuple
from sqlalchemy import select

from app.models import Job, AppConfig
from app.config import settings
from app.database import async_session_factory
import openai

logger = logging.getLogger(__name__)

class MatcherService:
    def __init__(self):
        pass

    def _build_prompt(self, resume_text: str, profile_json: str, job_description: str) -> str:
        profile_context = f"\nApplicant Structured Profile:\n{profile_json}\n" if profile_json else ""
        return f"""You are a job matching expert. Score how well this job description matches the candidate's resume.

Resume:
{resume_text}
{profile_context}

Job Description:
{job_description}

Respond with JSON only: {{"score": <0-100>, "summary": "<2-3 sentence explanation>"}}

Scoring guidelines:
- 90-100: Perfect match — all key skills and experience align
- 70-89: Strong match — most requirements met
- 40-69: Partial match — some relevant skills
- 0-39: Weak match — few overlapping qualifications
"""

    async def score_job(self, job_description: str, resume_text: str, profile_json: str = "") -> tuple[int, str]:
        """Score a job description against a resume. Returns (score 0-100, summary string)."""
        prompt = self._build_prompt(resume_text, profile_json, job_description)
        
        try:
            if settings.LLM_PROVIDER.lower() == 'openai':
                response_text = await self._call_openai(prompt)
            elif settings.LLM_PROVIDER.lower() == 'ollama':
                response_text = await self._call_ollama(prompt)
            else:
                logger.error(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
                return 0, "Failed to score: unknown provider"

            data = json.loads(response_text)
            score = int(data.get("score", 0))
            summary = str(data.get("summary", "No summary provided"))
            
            score = max(0, min(100, score))
            return score, summary

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from LLM response: {e}. Raw response: {response_text}")
            return 0, "Failed to score: invalid JSON"
        except Exception as e:
            logger.error(f"Error scoring job: {e}")
            return 0, f"Failed to score: {str(e)}"

    async def score_new_jobs(self) -> int:
        """Score all jobs that have match_score=None. Returns count of scored jobs."""
        scored_count = 0
        async with async_session_factory() as session:
            # 1. Load resume & profile from AppConfig table
            result = await session.execute(select(AppConfig).where(AppConfig.key.in_(['resume_text', 'resume_profile'])))
            configs = {c.key: c.value for c in result.scalars().all()}
            
            resume_text = configs.get('resume_text', '')
            resume_profile = configs.get('resume_profile', '')
            
            if not resume_text:
                logger.warning("No resume_text found in AppConfig. Cannot score jobs.")
                return 0
                
            # 2. Query all jobs where match_score IS NULL
            jobs_stmt = select(Job).where(Job.match_score.is_(None))
            jobs_result = await session.execute(jobs_stmt)
            jobs_to_score = jobs_result.scalars().all()

            # 3. For each job, call score_job() and update job
            for job in jobs_to_score:
                job_desc = job.description or ""
                if not job_desc:
                    job.match_score = 0
                    job.match_summary = "No description available to score."
                else:
                    score, summary = await self.score_job(job_description=job_desc, resume_text=resume_text, profile_json=resume_profile)
                    job.match_score = score
                    job.match_summary = summary
                
                scored_count += 1
            
            if scored_count > 0:
                await session.commit()
                logger.info(f"Successfully scored {scored_count} jobs.")
                
        return scored_count

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI-compatible API."""
        client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL if settings.OPENAI_BASE_URL else None
        )
        
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content or "{}"

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API."""
        url = f"{settings.OLLAMA_URL.rstrip('/')}/api/generate"
        payload = {
            "model": settings.LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "{}")

matcher_service = MatcherService()
