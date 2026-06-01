import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import Task, TaskStatus, User
from app.notifications import NotificationType, notify
from app.schemas import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


async def _get_task_or_404(db: AsyncSession, task_id: uuid.UUID, org_id: uuid.UUID) -> Task:
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == org_id)
    )
    task = result.scalar_one_or_none()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    mine: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.organization_id == org_id)
        .order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    if mine:
        stmt = stmt.where(Task.assignee_id == user.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Task:
    data = payload.model_dump()
    if not data.get("assignee_id"):
        data["assignee_id"] = user.id
    task = Task(**data, organization_id=org_id)
    db.add(task)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="task.create",
        entity_type="task",
        entity_id=task.id,
        organization_id=org_id,
        metadata={"priority": task.priority.value},
    )
    # Bell the assignee — unless they assigned the task to themselves
    # (the common case; self-bell is noise).
    if task.assignee_id and task.assignee_id != user.id:
        await notify(
            db,
            user_id=task.assignee_id,
            organization_id=org_id,
            notification_type=NotificationType.task_assigned,
            title=f"{user.full_name} assigned you a task",
            body=task.title,
            link_url=f"/tasks?focus={task.id}",
            actor=user,
            metadata={"task_id": str(task.id), "priority": task.priority.value},
        )
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Task:
    task = await _get_task_or_404(db, task_id, org_id)
    ensure_can_mutate(user, task.assignee_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("organization_id", None)
    # Snapshot assignee BEFORE setattr so we can detect reassignment
    # and bell the NEW assignee (only when it actually changed AND
    # the new assignee isn't the user making the change).
    prev_assignee_id = task.assignee_id
    for field, value in changes.items():
        setattr(task, field, value)
    await record_audit(
        db,
        actor=user,
        action="task.update",
        entity_type="task",
        entity_id=task.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    if (
        "assignee_id" in changes
        and task.assignee_id != prev_assignee_id
        and task.assignee_id is not None
        and task.assignee_id != user.id
    ):
        await notify(
            db,
            user_id=task.assignee_id,
            organization_id=org_id,
            notification_type=NotificationType.task_assigned,
            title=f"{user.full_name} assigned you a task",
            body=task.title,
            link_url=f"/tasks?focus={task.id}",
            actor=user,
            metadata={"task_id": str(task.id)},
        )
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    task = await _get_task_or_404(db, task_id, org_id)
    ensure_can_mutate(user, task.assignee_id)
    task.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="task.soft_delete",
        entity_type="task",
        entity_id=task.id,
        organization_id=org_id,
    )
    await db.commit()
