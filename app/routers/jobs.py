from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database import get_db
from app.models import Job
from app.schemas import JobOut, JobUpdate, PaginatedResponse

from app.auth import require_auth

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_model=PaginatedResponse[JobOut])
async def list_jobs(
    request: Request,
    min_score: int = 0,
    company: str = "",
    status: str = "",
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db)
):
    query = select(Job)
    
    if min_score:
        query = query.where(Job.match_score >= min_score)
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))
    if status:
        query = query.where(Job.status == status)
        
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    query = query.order_by(desc(Job.date_found)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    if request.headers.get("HX-Request"):
        context = {
            "request": request,
            "jobs": jobs,
            "min_score": min_score,
            "company": company,
            "status": status,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_jobs": total
        }
        return templates.TemplateResponse(request=request, name="partials/job_table.html", context=context)
        
    return PaginatedResponse(
        items=jobs,
        total=total,
        page=page,
        per_page=per_page,
        pages=total_pages
    )

@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: int,
    job_update: JobUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    update_data = job_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(job, key, value)
        
    await db.commit()
    await db.refresh(job)
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request, 
            name="partials/job_row.html", 
            context={"request": request, "job": job}
        )
        
    return job

@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    await db.delete(job)
    await db.commit()
    
    if request.headers.get("HX-Request"):
        return Response(status_code=200)
        
    return {"message": "Job deleted successfully"}
