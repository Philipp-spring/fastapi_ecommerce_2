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

from app.routers.products import router as products_router # импортируем роутер товаров с префиксом "/products"
# for route in products_router.routes: # APIRouter.routes - встроенный Python-список (list), в котором FastAPI хранит абсолютно все эндпоинты, зарегистрированные внутри этого роутера.
#     if route.path == "/products/{product_id}/reviews/": # APIRoute.path - полный URL-адрес эндпоинта (например, /products/{product_id}/reviews)
#         route.tags = ["reviews"]

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
        db: Annotated[AsyncSession, Depends(get_async_db)],  # Зависисмоть - "не запускай меня, пока не выполнишь её"
        current_user: Annotated[UserModel, Depends(get_current_buyer)] # принимает ОТ ЗАВИСИМОСТИ объект - "UserModel". # Из токена берется ID нужного пользователя (там извлекается)
        ):
        '''Добавление отзыва'''
        # Проверяем, существует ли такой товар
        product = await db.scalar(select(ProductModel).where(ProductModel.id == new_review.product_id))
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
        # Проверяем, оставлял ли этот пользователь отзыв ранее на этот товар (т.к. у одного пользователя должен быть только один отзыв на один товар)
        old_review = await db.scalar(select(ReviewModel).where(ReviewModel.user_id == current_user.id, ReviewModel.product_id == new_review.product_id)) # проверяем 2 условия: отзыв именно этого пользователя и именно на этот товар
        if old_review:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already left a review for this product") # уже есть отзыв на этт товар от этого пользователя
        # Создаем отзыв
        review = ReviewModel(**new_review.model_dump(), user_id = current_user.id)
        db.add(review)
        await db.flush() # синхронизирует изменения из памяти вашего приложения с базой данных, отправляя SQL-запросы (INSERT, UPDATE, DELETE), но НЕ сохраняет их окончательно (чтобы пересчитать рейтинг товара ниже). Изменения остаются внутри текущей транзакции базы данных до тех пор, пока не будет вызван метод db.commit(). (в этот момент генерируются id и параметры по умолчанию)
        # Пересчет рейтинга
        stmt = select(func.round(func.avg(ReviewModel.grade), 2)).where(ReviewModel.product_id == new_review.product_id, ReviewModel.is_active == True) # ищем оценки отзывов конеретного товара (c таким же "product_id"), и считаем их среднее значение с помощью (func.avg)
        new_rating = await db.scalar(stmt) # Используем .scalar() , т.к. функция func.avg возвращает ровно одно число (скаляр), иначе запишется объект-генератор, а не число.
        product.rating = new_rating
        await db.commit()
        await db.refresh(review)  # обновляем в ОЗУ
        return review



# В PostgreSQL:
# - Если grade имеет тип Integer (или SmallInt, BigInt), то AVG(grade) всегда возвращает тип numeric.
# - Если grade имеет тип Numeric (или Decimal), то AVG(grade) возвращает numeric.
# - Если grade имеет тип Real (или Double Precision), то AVG(grade) возвращает double precision (в Python это превратится во float)

# Numeric и Decimal — это два названия одного и того же типа данных, который используется для хранения чисел с фиксированной точностью, где критически важно избежать ошибок округления.
# 1.В базах данных (PostgreSQL / MySQL)
# - Это синонимы: В SQL вы можете написать как NUMERIC(10, 2), так и DECIMAL(10, 2) — для СУБД это абсолютно одинаковые типы.
# - Как они работают: Они хранят числа в виде строк или массивов цифр, а не в двоичном виде, как обычные Float или Real
# - Зачем нужны: Обычный Float из-за особенностей двоичной системы не может точно сохранить некоторые дроби (например, 0.1 + 0.2 во float будет равен 0.30000000000000004). Numeric/Decimal гарантирует, что 0.1 + 0.2 будет строго 0.3.
# - Где применяются: Везде, где нельзя ошибаться даже на микрокопейку — деньги, финансовые транзакции, точные веса и бухгалтерские отчеты.
# 2.В Python (decimal.Decimal)
# - Когда SQLAlchemy достает из PostgreSQL поле типа numeric, драйвер базы преобразует его в питоновский класс decimal.Decimal.

# func.round()
# В Postgres встроенная функция ROUND(value, decimal_places) имеет жесткое ограничение: первый аргумент обязан иметь тип NUMERIC
# Если ваше поле grade объявлено как Float или Integer, то функция func.avg() вернет тип Double Precision (число с плавающей точкой) и будет ОШИБКА
# И если это так, то есть функция .cast() из библиотеки "sqlalchemy", которая заставляет базу данных насильно перевести данные из одного типа в другой.

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
    await db.flush() # Изменение фиксируется внутри транзакции
    # Получение товара (по его отзыву)
    product = await db.scalar(select(ProductModel).where(ProductModel.id == review.product_id, ProductModel.is_active == True))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    # Пересчёт рейтинга
    new_rating = await db.scalar(select(func.round(func.sum(ReviewModel.grade) / func.nullif(func.count(ReviewModel.id), 0), 2)).where(ReviewModel.product_id == review.product_id, ReviewModel.is_active == True))
    product.rating = new_rating or 0.0 # если после удаления отзыва, их НЕ осталось, то благодаря func.nullif() в переменную "new_rating" вернется "None"
    await db.commit()                  # и если new_rating=None, то запишется 0.0
    return {"message": "Review deleted"}

# Защита от деления на НОЛЬ:
# func.nullif(выражение, значение) — это стандартная функция в базах данных (SQL), которая сравнивает два значения
# func.nullif(func.count(ReviewModel.id), 0) -----> func.nullif(5, 0) ----->  func.nullif(0, 0)  <---если отзывов ноль, то просто выведет None(Null), а не ОШИБКУ
# Если они равны, функция возвращает NULL (0)
# Если они не равны, функция возвращает первое значение

# func.sum(ReviewModel.grade) / None     <----любое математическое действие с NULL всегда возвращает NULL
# Главный принцип транзакции: «Или всё, или ничего».

# Транзакция в базе данных — это группа последовательных операций (например: найти отзыв, удалить его, пересчитать рейтинг, обновить товар), которая выполняется как одно единое целое.

# У сервер БД есть два пространства:
# «черновик» (транзакционный лог/память) -----> .flush() ---> (отправка изменений в БД)
# «чистовик» (основной диск)             -----> .commit()---> (фиксация изменений в БД)

# .commit() под капотом автоматически сам вызывает .flush() перед тем, как сохранить данные окончательно



# Со слэшем на конце (/) пишутся эндпоинты, которые отдают список или коллекцию элементов (например, GET /reviews/). Слэш как бы намекает, что это «папка», внутри которой лежат файлы-отзывы.
# БЕЗ слэша на конце пишутся пути, которые ведут на конкретное действие или на конкретный файл/объект.





# # ИЛИ отдельная функция для пересчета рейтинга:
# async def update_product_rating(db: AsyncSession, product_id: int):
#     result = await db.execute(
#         select(func.avg(ReviewModel.grade)).where(
#             ReviewModel.product_id == product_id,
#             ReviewModel.is_active == True
#         )
#     )
#     avg_rating = result.scalar() or 0.0
#     product = await db.get(ProductModel, product_id) # <--поиск одной конкретной записи в БД строго и только по её первичному ключу (id). (заменяет собой длинную конструкцию с select и where)
#     product.rating = avg_rating
#     await db.commit()

























































































































