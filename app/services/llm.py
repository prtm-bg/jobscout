"""
Unified LLM service for JobScout.
All modules (matcher, resume_parser, company_discovery) call through here.
Supports: OpenAI-compatible, Google Gemini, and Ollama.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
import openai

from app.config import settings
from app.database import async_session_factory
from sqlalchemy import select
from app.models import AppConfig

logger = logging.getLogger(__name__)


async def _get_runtime_config() -> dict[str, str]:
    """Load LLM config from the DB (UI-saved) with fallback to .env settings."""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(AppConfig).where(
                    AppConfig.key.in_([
                        "llm_provider", "llm_model",
                        "openai_api_key", "openai_base_url",
                        "gemini_api_key", "ollama_url",
                    ])
                )
            )
            db_config = {c.key: c.value for c in result.scalars().all()}
    except Exception:
        db_config = {}

    return {
        "provider": (db_config.get("llm_provider") or settings.LLM_PROVIDER).lower(),
        "model": db_config.get("llm_model") or settings.LLM_MODEL,
        "openai_api_key": db_config.get("openai_api_key") or settings.OPENAI_API_KEY,
        "openai_base_url": db_config.get("openai_base_url") or settings.OPENAI_BASE_URL,
        "gemini_api_key": db_config.get("gemini_api_key") or settings.GEMINI_API_KEY,
        "ollama_url": db_config.get("ollama_url") or settings.OLLAMA_URL,
    }


async def call_llm(prompt: str, *, json_mode: bool = False, system: str = "") -> str:
    """
    Call the configured LLM provider and return the raw text response.
    
    Args:
        prompt: The user prompt text.
        json_mode: If True, request JSON output format where supported.
        system: Optional system message.
    
    Returns:
        The model's text response.
    """
    cfg = await _get_runtime_config()
    provider = cfg["provider"]

    if provider == "openai":
        return await _call_openai(cfg, prompt, system=system, json_mode=json_mode)
    elif provider == "gemini":
        return await _call_gemini(cfg, prompt, system=system, json_mode=json_mode)
    elif provider == "ollama":
        return await _call_ollama(cfg, prompt, system=system, json_mode=json_mode)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


async def _call_openai(cfg: dict, prompt: str, *, system: str, json_mode: bool) -> str:
    client = openai.AsyncOpenAI(
        api_key=cfg["openai_api_key"],
        base_url=cfg["openai_base_url"] if cfg["openai_base_url"] else None,
    )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict = {
        "model": cfg["model"],
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def _call_gemini(cfg: dict, prompt: str, *, system: str, json_mode: bool) -> str:
    from google import genai

    client = genai.Client(api_key=cfg["gemini_api_key"])

    full_prompt = prompt
    if system:
        full_prompt = f"{system}\n\n{prompt}"

    config_kwargs: dict = {}
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"

    response = await client.aio.models.generate_content(
        model=cfg["model"],
        contents=full_prompt,
        config=genai.types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
    )
    return response.text or ""


async def _call_ollama(cfg: dict, prompt: str, *, system: str, json_mode: bool) -> str:
    url = f"{cfg['ollama_url'].rstrip('/')}/api/generate"
    full_prompt = f"System: {system}\n\nUser: {prompt}" if system else prompt

    payload: dict = {
        "model": cfg["model"],
        "prompt": full_prompt,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=120.0)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")
