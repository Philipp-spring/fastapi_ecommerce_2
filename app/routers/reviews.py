from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm # для создания классической асинхронной авторизации по логину и паролю (под капотом работает библиотека python-multipart, которая заставляет эндпоинт принимать данные в формате HTML-формы (Form Data))
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Annotated # typing - печать, печатание, набор текста

import jwt # библиотека - PyJWT (отвечает за создание (кодирование) и проверку (декодирование) JWT-токенов (JSON Web Tokens))
from app.config import SECRET_KEY, ALGORITHM
from app.models import Review as ReviewModel
from app.models import Product as ProductModel
from app.models import User as UserModel
from app.schemas import Review as ReviewSchema, ReviewCreate
from app.db_depends import get_async_db
from app.auth import get_current_seller, get_current_admin, get_current_buyer

from app.routers.products import router as products_router

router = APIRouter(prefix="/reviews", tags=["reviews"])

# Получение всех отзывов
@router.get('/', response_model=list[ReviewSchema], status_code=status.HTTP_200_OK)
async def get_reviews(db: Annotated[AsyncSession, Depends(get_async_db)]):
    '''Получение всех отзывов'''
    stmt = select(ReviewModel).where(ReviewModel.is_active == True)
    reviews = await db.scalars(stmt)
    return reviews.all()




# Получение отзывов о конкретном товаре
@products_router.get('/{product_id}/reviews/', response_model=list[ReviewSchema], status_code=status.HTTP_200_OK)
async def get_product_reviews(product_id: int,
                        db: Annotated[AsyncSession, Depends(get_async_db)]):
    '''Получение отзывов о конкретном товаре'''
    # Проверяем, существует ли товар и активен ли он
    product = await db.scalar(select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    stmt = select(ReviewModel).where(ReviewModel.product_id == product_id, ReviewModel.is_active == True)
    reviews = await db.scalars(stmt)
    return reviews.all()


# Добавление отзыва
@router.post('/reviews', response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(
        new_review: ReviewCreate,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        current_user: Annotated[UserModel, Depends(get_current_buyer)]
        ):
        '''Добавление отзыва'''
        # Проверяем, существует ли такой товар
        product = await db.scalar(select(ProductModel).where(ProductModel.id == new_review.product_id))
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
        # Проверяем, оставлял ли этот пользователь отзыв ранее на этот товар (т.к. у одного пользователя должен быть только один отзыв на один товар)
        old_review = await db.scalar(select(ReviewModel).where(ReviewModel.user_id == current_user.id, ReviewModel.product_id == new_review.product_id))
        if old_review:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already left a review for this product")
        # Создаем отзыв
        review = ReviewModel(**new_review.model_dump(), user_id = current_user.id)
        db.add(review)
        await db.flush()
        # Пересчет рейтинга
        stmt = select(func.round(func.avg(ReviewModel.grade), 2)).where(ReviewModel.product_id == new_review.product_id, ReviewModel.is_active == True)
        new_rating = await db.scalar(stmt)
        product.rating = new_rating
        await db.commit()
        await db.refresh(review)
        return review





# Мягкое удаление отзыва
@router.delete('/{review_id}', response_model=dict, status_code=status.HTTP_200_OK)
async def delete_review(
                        review_id: int,
                        db:  Annotated[AsyncSession, Depends(get_async_db)],
                        current_user: Annotated[UserModel, Depends(get_current_admin)]
                       ):
    '''Мягкое удаление отзыва по ID'''
    # Получаем отзыв по его ID
    stmt = select(ReviewModel).where(ReviewModel.id == review_id, ReviewModel.is_active == True)
    review = await db.scalar(stmt)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found or inactive")
    review.is_active = False
    await db.flush()
    # Получение товара (по его отзыву)
    product = await db.scalar(select(ProductModel).where(ProductModel.id == review.product_id, ProductModel.is_active == True))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    # Пересчёт рейтинга
    new_rating = await db.scalar(select(func.round(func.sum(ReviewModel.grade) / func.nullif(func.count(ReviewModel.id), 0), 2)).where(ReviewModel.product_id == review.product_id, ReviewModel.is_active == True))
    product.rating = new_rating or 0.0
    await db.commit()
    return {"message": "Review deleted"}

























































































































