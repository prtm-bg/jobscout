from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import ScrapeTarget
from app.schemas import TargetCreate, TargetUpdate, TargetOut

from app.auth import require_auth

router = APIRouter(prefix="/api/targets", tags=["targets"], dependencies=[Depends(require_auth)])

@router.get("", response_model=List[TargetOut])
async def list_targets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScrapeTarget).order_by(ScrapeTarget.name))
    return result.scalars().all()

@router.post("", response_model=TargetOut)
async def create_target(
    request: Request,
    target_in: TargetCreate,
    db: AsyncSession = Depends(get_db)
):
    target = ScrapeTarget(**target_in.model_dump())
    db.add(target)
    await db.commit()
    await db.refresh(target)
    
    if request.headers.get("HX-Request"):
        return RedirectResponse(url="/targets", status_code=303)
        
    return target

@router.patch("/{target_id}", response_model=TargetOut)
async def update_target(
    target_id: int,
    target_update: TargetUpdate,
    db: AsyncSession = Depends(get_db)
):
    target = await db.get(ScrapeTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
        
    update_data = target_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(target, key, value)
        
    await db.commit()
    await db.refresh(target)
    return target

@router.delete("/{target_id}")
async def delete_target(
    target_id: int,
    db: AsyncSession = Depends(get_db)
):
    target = await db.get(ScrapeTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
        
    await db.delete(target)
    await db.commit()
    return {"message": "Target deleted successfully"}

@router.post("/{target_id}/toggle", response_model=TargetOut)
async def toggle_target(
    target_id: int,
    db: AsyncSession = Depends(get_db)
):
    target = await db.get(ScrapeTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
        
    target.enabled = not target.enabled
    await db.commit()
    await db.refresh(target)
    return target
