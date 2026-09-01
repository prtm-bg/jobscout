from __future__ import annotations
import datetime
from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int

class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    url: str
    company: str
    title: str
    description: str
    location: Optional[str] = None
    match_score: Optional[int] = None
    match_summary: Optional[str] = None
    status: str
    date_found: datetime.datetime
    source_target_id: Optional[int] = None

class JobUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(new|applied|archived|rejected)$")
    match_score: Optional[int] = None
    match_summary: Optional[str] = None

class JobFilter(BaseModel):
    min_score: Optional[int] = None
    company: Optional[str] = None
    status: Optional[str] = None
    page: int = 1
    per_page: int = 50

class TargetCreate(BaseModel):
    name: str
    url: str
    ats_type: str = "generic"
    custom_selectors: Optional[str] = None
    enabled: bool = True

class TargetUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    ats_type: Optional[str] = None
    custom_selectors: Optional[str] = None
    enabled: Optional[bool] = None

class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    url: str
    ats_type: str
    custom_selectors: Optional[str] = None
    enabled: bool
    last_scraped_at: Optional[datetime.datetime] = None

class ScrapeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    target_id: Optional[int] = None
    started_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    status: str
    jobs_found: int
    error_message: Optional[str] = None

class ScheduleConfig(BaseModel):
    interval_hours: int

class SettingsUpdate(BaseModel):
    key: str
    value: str

class ResumeUpdate(BaseModel):
    text: str

class AntiBotConfig(BaseModel):
    proxy_list: str = ""
    captcha_provider: str = ""
    captcha_api_key: str = ""
    ua_rotation_enabled: bool = True
    delay_seconds: float = 2.0

class NotificationConfig(BaseModel):
    apprise_urls: str = ""
    min_score_threshold: int = 70

