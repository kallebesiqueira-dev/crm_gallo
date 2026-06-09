import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._concurrency import check_if_match
from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import Product, User
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage, paginate
from app.schemas import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/api/products", tags=["products"])

# Tenant-scoped via `get_current_org_id` (sets the org GUC; RLS does the rest).
# `organization_id` is set server-side on create and stripped on update;
# cross-org reads return 404, not 403 — same model as companies.py.


async def _get_product_or_404(
    db: AsyncSession, product_id: uuid.UUID, org_id: uuid.UUID
) -> Product:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.organization_id == org_id)
    )
    product = result.scalar_one_or_none()
    if not product or product.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("", response_model=CursorPage[ProductOut])
async def list_products(
    q: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    stmt = select(Product).where(Product.organization_id == org_id)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    return await paginate(db, stmt, Product, limit=limit, cursor=cursor)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Product:
    data = payload.model_dump()
    data["owner_id"] = data.get("owner_id") or user.id
    product = Product(**data, organization_id=org_id)
    db.add(product)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="product.create",
        entity_type="product",
        entity_id=product.id,
        organization_id=org_id,
    )
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Product:
    return await _get_product_or_404(db, product_id, org_id)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Product:
    product = await _get_product_or_404(db, product_id, org_id)
    ensure_can_mutate(user, product.owner_id)
    check_if_match(
        entity="product",
        entity_id=product.id,
        current_version=product.version,
        if_match=if_match,
    )
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("organization_id", None)
    for field, value in changes.items():
        setattr(product, field, value)
    product.version = product.version + 1
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="product.update",
        entity_type="product",
        entity_id=product.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    product = await _get_product_or_404(db, product_id, org_id)
    ensure_can_mutate(user, product.owner_id)
    product.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="product.soft_delete",
        entity_type="product",
        entity_id=product.id,
        organization_id=org_id,
    )
    await db.commit()
