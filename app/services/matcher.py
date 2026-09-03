import json
import logging
from sqlalchemy import select

from app.models import Job, AppConfig
from app.database import async_session_factory
from app.services.llm import call_llm

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
            response_text = await call_llm(
                prompt,
                system="You are an expert technical recruiter analyzing job matches.",
                json_mode=True,
            )

            data = json.loads(response_text)
            score = int(data.get("score", 0))
            summary = str(data.get("summary", "No summary provided"))

            score = max(0, min(100, score))
            return score, summary

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from LLM response: {e}")
            return 0, "Failed to score: invalid JSON"
        except Exception as e:
            logger.error(f"Error scoring job: {e}")
            return 0, f"Failed to score: {str(e)}"

    async def score_new_jobs(self) -> int:
        """Score all jobs that have match_score=None. Returns count of scored jobs."""
        scored_count = 0
        async with async_session_factory() as session:
            result = await session.execute(
                select(AppConfig).where(AppConfig.key.in_(["resume_text", "resume_profile"]))
            )
            configs = {c.key: c.value for c in result.scalars().all()}

            resume_text = configs.get("resume_text", "")
            resume_profile = configs.get("resume_profile", "")

            if not resume_text:
                logger.warning("No resume_text found in AppConfig. Cannot score jobs.")
                return 0

            jobs_stmt = select(Job).where(Job.match_score.is_(None))
            jobs_result = await session.execute(jobs_stmt)
            jobs_to_score = jobs_result.scalars().all()

            for job in jobs_to_score:
                job_desc = job.description or ""
                if not job_desc:
                    job.match_score = 0
                    job.match_summary = "No description available to score."
                else:
                    score, summary = await self.score_job(
                        job_description=job_desc,
                        resume_text=resume_text,
                        profile_json=resume_profile,
                    )
                    job.match_score = score
                    job.match_summary = summary

                scored_count += 1

            if scored_count > 0:
                await session.commit()
                logger.info(f"Successfully scored {scored_count} jobs.")

        return scored_count


matcher_service = MatcherService()
