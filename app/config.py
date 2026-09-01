from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/jobscout.db"
    
    # Auth
    SECRET_KEY: str = "change-me-in-production-jobscout-super-secret"
    SESSION_EXPIRY_HOURS: int = 24
    
    # LLM
    LLM_PROVIDER: str = "openai"  # openai or ollama
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OLLAMA_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "gpt-4o-mini"
    
    # CAPTCHA
    CAPTCHA_PROVIDER: str = ""  # 2captcha, capsolver, flaresolverr, or empty
    CAPTCHA_API_KEY: str = ""
    FLARESOLVERR_URL: str = "http://flaresolverr:8191/v1"
    
    # Proxies
    PROXY_LIST: str = ""  # comma-separated
    
    # Notifications
    APPRISE_URLS: str = ""  # comma-separated
    MATCH_THRESHOLD: int = 70
    
    # Schedule
    SCRAPE_INTERVAL_HOURS: int = 6
    
    # Anti-bot
    UA_ROTATION_ENABLED: bool = True
    
    def get_proxy_list(self) -> list[str]:
        if not self.PROXY_LIST:
            return []
        return [p.strip() for p in self.PROXY_LIST.split(",") if p.strip()]
    
    def get_apprise_urls(self) -> list[str]:
        if not self.APPRISE_URLS:
            return []
        return [u.strip() for u in self.APPRISE_URLS.split(",") if u.strip()]

settings = Settings()
