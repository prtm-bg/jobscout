from __future__ import annotations
import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Job(Base):
    __tablename__ = "jobs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    company: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    match_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    match_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new/applied/archived/rejected
    date_found: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    source_target_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scrape_targets.id", ondelete="SET NULL"), nullable=True)
    
    source_target: Mapped[Optional["ScrapeTarget"]] = relationship(back_populates="jobs")

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}', status='{self.status}')>"


class ScrapeTarget(Base):
    __tablename__ = "scrape_targets"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    ats_type: Mapped[str] = mapped_column(String(50), default="generic")  # greenhouse/lever/workday/generic
    custom_selectors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    
    jobs: Mapped[list["Job"]] = relationship(back_populates="source_target")
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship(back_populates="target")

    def __repr__(self) -> str:
        return f"<ScrapeTarget(id={self.id}, name='{self.name}', ats_type='{self.ats_type}')>"


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scrape_targets.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/success/failed
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    target: Mapped[Optional["ScrapeTarget"]] = relationship(back_populates="scrape_runs")

    def __repr__(self) -> str:
        return f"<ScrapeRun(id={self.id}, status='{self.status}', jobs_found={self.jobs_found})>"


class AppConfig(Base):
    __tablename__ = "app_config"
    
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return f"<AppConfig(key='{self.key}')>"
