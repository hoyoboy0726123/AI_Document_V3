from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ... import models, schemas
from ...core.security import get_current_user
from ...database import get_db

router = APIRouter()


@router.get("/{task_id}", response_model=schemas.TaskRead)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = db.query(models.BackgroundTask).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任務不存在")
    if task.creator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權存取此任務")
    return task


@router.get("/", response_model=List[schemas.TaskRead])
def list_my_tasks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """列出目前用戶的最近 20 個任務（進行中的優先）"""
    tasks = (
        db.query(models.BackgroundTask)
        .filter_by(creator_id=current_user.id)
        .order_by(models.BackgroundTask.created_at.desc())
        .limit(20)
        .all()
    )
    return tasks
