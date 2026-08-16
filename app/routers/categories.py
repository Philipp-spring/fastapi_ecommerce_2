from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.categories import Category as CategoryModel
from app.schemas import Category as CategorySchema, CategoryCreate
from app.db_depends import get_db

from app.models.users import User as UserModel
from app.auth import get_current_admin

from sqlalchemy.ext.asyncio import AsyncSession
from app.db_depends import get_async_db

# Создаём маршрутизатор с префиксом и тегом
router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)



@router.get("/", response_model=list[CategorySchema])
async def get_all_categories(db: Annotated[AsyncSession, Depends(get_async_db)]):
    """
    Возвращает список всех (активных) категорий товаров.
    """
    stmt = select(CategoryModel).where(CategoryModel.is_active == True)
    result  = await db.scalars(stmt)
    categories = result.all()
    return categories


@router.post("/", response_model=CategorySchema, status_code=status.HTTP_201_CREATED)
async def create_category(
        category: CategoryCreate,
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_admin)
):

    """
    Создаёт новую категорию, привязанную к текущему продавцу (только для 'admin').
    """
    # Проверка существования parent_id, если указан
    if category.parent_id is not None:
        stmt = select(CategoryModel).where(CategoryModel.id == category.parent_id, CategoryModel.is_active == True)
        result = await db.scalars(stmt)
        parent = result.first()
        if parent is None:
            raise HTTPException(status_code=400, detail="Parent category not found")
    # Создание новой категории
    db_category = CategoryModel(**category.model_dump(), admin_id=current_user.id)
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    return db_category



@router.put("/{category_id}", response_model=CategorySchema)
async def update_category(
        category_id: int,
        category: CategoryCreate,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        current_user: UserModel = Depends(get_current_admin)
):
    """
    Обновляет категорию по её ID, если она принадлежит текущему админу (только для 'admin').
    """
    # Проверка существования категории
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active == True)
    result = await db.scalars(stmt)
    db_category = result.first()
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if db_category.admin_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own categories")
    # Проверка существования parent_id, если указан
    if category.parent_id is not None:
        parent_stmt = select(CategoryModel).where(CategoryModel.id == category.parent_id, CategoryModel.is_active == True)
        parent_result = await db.scalars(parent_stmt)
        parent = parent_result.first()
        if parent is None: # существует ли родитель
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent category not found")
        if parent.id == category_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category cannot be its own parent")

    # Обновление категории
    update_data = category.model_dump(exclude_unset=True)
    await db.execute(update(CategoryModel).where(CategoryModel.id == category_id).values(**update_data))
    await db.commit()
    await db.refresh(db_category)
    return db_category




@router.delete("/{category_id}", status_code=status.HTTP_200_OK)
async def delete_category(
        category_id: int,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        current_user: UserModel = Depends(get_current_admin)
):
    """
    Удаляет категорию по её ID, если она принадлежит текущему админу (только для 'admin').
    """
    # Проверка существования активной категории
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active == True)
    result = await db.scalars(stmt)
    db_category = result.first()
    if db_category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if db_category.admin_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own categories")

    # ЛОГИЧЕСКОЕ/(мягкое) удаление категории (установка is_active=False)
    stmt = update(CategoryModel).where(CategoryModel.id == category_id).values(is_active=False)
    await db.execute(stmt)
    await db.commit()
    await db.refresh(db_category)
    return db_category

