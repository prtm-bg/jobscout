import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.services.scheduler import scheduler_service

from app.routers import dashboard, jobs, targets, scraper, settings, auth_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    scheduler_service.start()
    yield
    # Shutdown
    scheduler_service.shutdown()

app = FastAPI(
    title="JobScout API",
    description="Job scraping and matching application",
    lifespan=lifespan
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(auth_routes.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(targets.router)
app.include_router(scraper.router)
app.include_router(settings.router)
