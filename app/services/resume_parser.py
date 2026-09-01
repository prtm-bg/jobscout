import io
import json
import logging
from typing import Dict, Any

from fastapi import UploadFile
import fitz  # PyMuPDF
import docx

from app.config import settings
import openai

logger = logging.getLogger(__name__)

async def extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    if file.filename.endswith(".pdf"):
        return _extract_from_pdf(content)
    elif file.filename.endswith(".docx"):
        return _extract_from_docx(content)
    else:
        # Fallback to plain text decoding
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
    """Uses LLM to analyze the resume text and return a structured JSON profile."""
    prompt = (
        "Analyze this resume and extract a structured profile as JSON.\n"
        "Return ONLY valid JSON without markdown formatting.\n"
        "{\n"
        "  \"skills\": [\"skill1\", \"skill2\"],\n"
        "  \"experience_years\": 5,\n"
        "  \"preferred_titles\": [\"Software Engineer\", \"Backend Developer\"],\n"
        "  \"industries\": [\"Tech\", \"Finance\"],\n"
        "  \"education\": \"B.S. Computer Science\",\n"
        "  \"summary\": \"Brief professional summary here...\"\n"
        "}\n\n"
        f"RESUME:\n{resume_text}"
    )
    
    try:
        # Use OpenAI client
        client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL if settings.OPENAI_BASE_URL else None
        )
        
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        
        result_text = response.choices[0].message.content.strip()
        # Clean up markdown code blocks if present
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
            
        # Verify it's valid JSON
        json.loads(result_text)
        return result_text.strip()
    except Exception as e:
        logger.error(f"Failed to analyze resume: {e}")
        # Return basic fallback profile
        return json.dumps({
            "skills": [],
            "experience_years": 0,
            "preferred_titles": [],
            "industries": [],
            "education": "",
            "summary": "Could not analyze resume automatically."
        })
