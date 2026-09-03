"""
Resume file parser and LLM-based profile extractor.
Supports PDF (.pdf) and DOCX (.docx) files.
"""
import io
import json
import logging

from fastapi import UploadFile
import fitz  # PyMuPDF
import docx

from app.services.llm import call_llm

logger = logging.getLogger(__name__)


async def extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        return _extract_from_pdf(content)
    elif filename.endswith(".docx"):
        return _extract_from_docx(content)
    else:
        return content.decode("utf-8", errors="ignore")


def _extract_from_pdf(content: bytes) -> str:
    text = ""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            text += page.get_text()
    except Exception as e:
        logger.error(f"Error reading PDF: {e}")
    return text


def _extract_from_docx(content: bytes) -> str:
    text = ""
    try:
        doc = docx.Document(io.BytesIO(content))
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        logger.error(f"Error reading DOCX: {e}")
    return text


async def analyze_resume_profile(resume_text: str) -> str:
    """Uses the configured LLM to extract a structured JSON profile from resume text."""
    prompt = (
        "Analyze this resume and extract a structured profile as JSON.\n"
        "Return ONLY valid JSON without markdown formatting.\n"
        "{\n"
        '  "skills": ["skill1", "skill2"],\n'
        '  "experience_years": 5,\n'
        '  "preferred_titles": ["Software Engineer", "Backend Developer"],\n'
        '  "industries": ["Tech", "Finance"],\n'
        '  "education": "B.S. Computer Science",\n'
        '  "summary": "Brief professional summary here..."\n'
        "}\n\n"
        f"RESUME:\n{resume_text}"
    )

    try:
        result_text = await call_llm(prompt, json_mode=True)

        # Clean markdown fences
        result_text = result_text.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()

        # Validate JSON
        json.loads(result_text)
        return result_text
    except Exception as e:
        logger.error(f"Failed to analyze resume: {e}")
        return json.dumps({
            "skills": [],
            "experience_years": 0,
            "preferred_titles": [],
            "industries": [],
            "education": "",
            "summary": "Could not analyze resume automatically.",
        })
