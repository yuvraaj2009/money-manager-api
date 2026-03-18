"""Category CRUD routes. JWT required, scoped to current user."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def get_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Category)
        .where(Category.user_id == current_user.id)
        .order_by(Category.type, Category.name)
    )
    categories = list(result.scalars().all())
    return {
        "success": True,
        "data": [CategoryResponse.model_validate(c).model_dump() for c in categories],
    }


@router.post("")
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    category = Category(
        user_id=current_user.id,
        name=data.name,
        icon=data.icon,
        color=data.color,
        type=data.type,
        is_default=False,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return {
        "success": True,
        "data": CategoryResponse.model_validate(category).model_dump(),
    }


@router.put("/{category_id}")
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Category).where(
            and_(Category.id == category_id, Category.user_id == current_user.id)
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")

    if data.name is not None:
        category.name = data.name
    if data.icon is not None:
        category.icon = data.icon
    if data.color is not None:
        category.color = data.color
    if data.type is not None:
        category.type = data.type

    await db.commit()
    await db.refresh(category)
    return {
        "success": True,
        "data": CategoryResponse.model_validate(category).model_dump(),
    }


@router.delete("/{category_id}")
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Category).where(
            and_(Category.id == category_id, Category.user_id == current_user.id)
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")

    await db.delete(category)
    await db.commit()
    return {
        "success": True,
        "data": {"id": str(category_id), "deleted": True},
    }
