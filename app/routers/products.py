from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy import select, update, func, desc, asc, or_
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import Product as ProductModel
from app.schemas import ProductCreate, Product as ProductSchema, ProductList
from app.db_depends import get_db

from app.models.users import User as UserModel
from app.auth import get_current_seller

from app.models import Category as CategoryModel

from sqlalchemy.ext.asyncio import AsyncSession
from app.db_depends import get_async_db

from enum import Enum


from pathlib import Path
import uuid



# КОНСТАНТЫ:
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_ROOT = BASE_DIR / "media" / "products"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 2 * 1024 * 1024

# Создаём маршрутизатор для товаров
router = APIRouter(
    prefix="/products",
    tags=["products"],
)




# Сохраняет изображение товара и возвращает относительный URL
async def save_product_image(file: UploadFile) -> str:
    """
    Сохраняет изображение товара и возвращает относительный URL.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only JPG, PNG or WebP images are allowed")
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image is too large")

    extension = Path(file.filename or "").suffix.lower() or ".jpg"
    file_name = f"{uuid.uuid4()}{extension}"
    file_path = MEDIA_ROOT / file_name
    file_path.write_bytes(content)
    return f"/media/products/{file_name}"




# Удалением изображения
def remove_product_image(url: str | None) -> None:
    """
    Удаляет файл изображения, если он существует.
    """
    if not url:
        return
    relative_path = url.lstrip("/")
    file_path = BASE_DIR / relative_path
    if file_path.exists():
        file_path.unlink()









class ProductSortField(str, Enum):
    id = "id"
    created_at = "created_at"

class SortDir(str, Enum):
    asc = "asc"
    desc = "desc"



# Возвращает список всех активных товаров с поддержкой пагинации
@router.get("/",response_model=ProductList, status_code=status.HTTP_200_OK)
async def get_all_products(
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        category_id: Annotated[int | None, Query(description="ID категории для фильтрации")] = None,
        search: Annotated[str | None, Query(min_length=1, description="Поиск по названию товара")] = None,
        min_price: Annotated[float | None, Query(ge=0, description="Минимальная цена товара")] = None,
        max_price: Annotated[float | None, Query(ge=0, description="Максимальная цена товара")] = None,
        in_stock: Annotated[bool | None, Query(description="true — только товары в наличии, false — только без остатка")] = None,
        seller_id: Annotated[int | None, Query(description="ID продавца для фильтрации")] = None,
        sort_by: Annotated[ProductSortField, Query(description="Поле сортировки")] = ProductSortField.id,
        sort_dir: Annotated[SortDir, Query(description="Направление сортировки")] = SortDir.desc,
        db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список всех активных товаров с поддержкой пагинации и фильтров.
    """

    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price не может быть больше max_price",
        )


    # Формируем список динамических фильтров (условия для запроса)
    filters = [ProductModel.is_active == True]
    if category_id is not None:
        filters.append(ProductModel.category_id == category_id)
    if min_price is not None:
        filters.append(ProductModel.price >= min_price)
    if max_price is not None:
        filters.append(ProductModel.price <= max_price)
    if in_stock is not None:
        filters.append(ProductModel.stock > 0 if in_stock else ProductModel.stock == 0)
    if seller_id is not None:
        filters.append(ProductModel.seller_id == seller_id)

    rank_col = None
    if search:
        search_value = search.strip()
        if search_value:
            ts_query_en = func.websearch_to_tsquery('english', search_value)
            ts_query_ru = func.websearch_to_tsquery('russian', search_value)
            # Ищем совпадение в любой конфигурации и добавляем в общий фильтр
            ts_match_any = or_(
                ProductModel.tsv.op('@@')(ts_query_en),
                ProductModel.tsv.op('@@')(ts_query_ru),   # объединяем 2 выражения (если хоть одно подходит)
            )
            filters.append(ts_match_any)
            # берем ранг максимальный из двух
            rank_col = func.greatest(
                func.ts_rank_cd(ProductModel.tsv, ts_query_en),
                func.ts_rank_cd(ProductModel.tsv, ts_query_ru),
            ).label("rank")


    total_stmt = select(func.count()).select_from(ProductModel).where(*filters)

    total = await db.scalar(total_stmt) or 0

    # Основной запрос (если есть поиск — добавим ранг в выборку и сортировку)
    if rank_col is not None:
        products_stmt = (
            select(ProductModel, rank_col)
            .where(*filters)
            .order_by(desc(rank_col), ProductModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(products_stmt)
        rows = result.all()
        items = [row[0] for row in rows]
    else:
        SORT_MAPPING = {
            ProductSortField.id: ProductModel.id,
            ProductSortField.created_at: ProductModel.created_at,
        }

        sort_column = SORT_MAPPING.get(sort_by)
        sort_expression = desc(sort_column) if sort_dir == SortDir.desc else asc(sort_column)
        # Выборка товаров с фильтрами и пагинацией
        products_stmt = (
            select(ProductModel)
            .where(*filters)
            .order_by(sort_expression, desc(ProductModel.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        # Выполнение запроса и обработка результата
        items = (await db.scalars(products_stmt)).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }




# СОЗДАНИЕ нового товара
@router.post("/", response_model=ProductSchema, status_code=status.HTTP_201_CREATED)
async def create_product(
        product: ProductCreate = Depends(ProductCreate.as_form),
        image: UploadFile | None  = File(None),
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_seller)
):

    """
    Создаёт новый товар, привязанный к текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == product.category_id, CategoryModel.is_active == True)
    temp = await db.scalars(stmt)
    category = temp.first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive") # Некорректный запрос
    # Сохранение изображения (если есть)
    image_url = await save_product_image(image) if image else None
    # Создаём товар
    db_product = ProductModel(**product.model_dump(),
                              seller_id=current_user.id,
                              image_url=image_url)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product




@router.get("/category/{category_id}", response_model=list[ProductSchema], status_code=status.HTTP_200_OK)
async def get_products_by_category(category_id: int, db: Annotated[AsyncSession, Depends(get_async_db)]):
    """
    Возвращает список товаров в указанной категории по её ID.
    """
    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active == True)
    temp = await db.scalars(stmt)
    category = temp.first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or inactive")
    # Получаем активные товары в категории
    stmt = select(ProductModel).where(ProductModel.category_id == category.id, ProductModel.is_active == True)
    temp2 = await db.scalars(stmt)
    products = temp2.all()
    return products


@router.get("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def get_product(product_id: int, db: Annotated[AsyncSession, Depends(get_async_db)]):
    """
    Возвращает детальную информацию о товаре по его ID.
    """
    # Проверяем, существует ли активный товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    temp = await db.scalars(stmt)
    product = temp.first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == product.category_id, CategoryModel.is_active == True)
    temp2 = await db.scalars(stmt)
    category = temp2.first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or inactive")
    return product



# ОБНОВЛЕНИЕ товара
@router.put("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def update_product(
        product_id: int,
        new_product: ProductCreate = Depends(ProductCreate.as_form),
        image: UploadFile | None = File(None),
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_seller)):

    """
    Обновляет товар по его ID, если он принадлежит текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    temp = await db.scalars(stmt)
    db_product = temp.first()
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    if db_product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own products")
    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == new_product.category_id, CategoryModel.is_active == True)
    temp2 = await db.scalars(stmt)
    category = temp2.first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")
    # Обновляем товар
    await db.execute(update(ProductModel).where(ProductModel.id == product_id).values(**new_product.model_dump()))


    if image:
        remove_product_image(db_product.image_url)
        db_product.image_url = await save_product_image(image)
    await db.commit()
    await db.refresh(db_product)
    return db_product




# УДАЛЕНИЕ товара
@router.delete("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def delete_product(
        product_id: int,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        current_user: UserModel = Depends(get_current_seller)
):
    """
    Выполняет мягкое удаление товара по его ID, если он принадлежит текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли активный товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    temp = await db.scalars(stmt)
    product = temp.first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    if product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own products")
    # (логическое удаление) is_active=False
    product.image_url = None
    product.is_active = False
    await db.commit()
    await db.refresh(product)
    return product























