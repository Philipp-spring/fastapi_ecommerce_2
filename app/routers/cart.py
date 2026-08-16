from decimal import Decimal # Используем Decimal для точных расчётов цен, чтобы избежать ошибок с числами с плавающей точкой (например, 0.1 + 0.2 ≠ 0.3 в float).
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload # selectinload — это инструмент SQLAlchemy для быстрой загрузки связанных данных из базы, который решает проблему лишних запросов за счет выполнения ровно двух SQL-запросов.

from app.auth import get_current_user   # для проверки, что запросы выполняются только авторизованными пользователями.
from app.db_depends import get_async_db # асинхронная сессия БД
from app.models.cart_items import CartItem as CartItemModel # ORM модель
from app.models.products import Product as ProductModel     # ORM модель
from app.models.users import User as UserModel              # ORM модель
from app.schemas import (
    Cart as CartSchema,          # Pydantic-схема
    CartItem as CartItemSchema,  # Pydantic-схема
    CartItemCreate,              # Pydantic-схема
    CartItemUpdate,              # Pydantic-схема
)


router = APIRouter(prefix="/cart", tags=["cart"])


# вспомогательные функции, используются в нескольких эндпоинтах, чтобы избежать дублирования кода:
# Эта функция проверяет, что товар с указанным product_id существует в базе данных, активен (is_active == True) и доступен для добавления в корзину.
# Он ничего не возвращает, а обрабатывает ситуацию, если товар не найден или неактивен, то функция возвращает ошибку 404 (HTTPException). Она будет использоваться в эндпоинтах добавления и обновления товаров, тем самым мы сможем избежать дублирования кода.
async def _ensure_product_available(db: AsyncSession, product_id: int) -> None:
    # ищем продукт (прсото проверка наличия товара в магазине, ничего НЕ возвращает)
    result = await db.scalars(
        select(ProductModel).where(
            ProductModel.id == product_id,
            ProductModel.is_active == True,
        )
    )
    product = result.first()
    if not product: # если продукта нет - ОШИБКА
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or inactive",
        )


# Функция ищет ТОВАР В КОРЗИНЕ текущего пользователя по product_id.
# В результате работы возвращает (ORM)объект CartItemModel или None, если товар в корзине не найден.
async def _get_cart_item(
    db: AsyncSession, user_id: int, product_id: int
) -> CartItemModel | None:
    result = await db.scalars(
        select(CartItemModel)
        .options(selectinload(CartItemModel.product))  # жадная-загрузка, т.к. объект CartItemModel не содержит ВСЕЙ информации о товаре, поэтому дополнительно запрашиваем объект Product
        .where(
            CartItemModel.user_id == user_id,
            CartItemModel.product_id == product_id,
        )
    )
    return result.first() # возвращает один объект CartItemModel, внутри которого уже лежит готовый вложенный объект Product.
# Эта функция будет использоваться во всех операциях с конкретным товаром (добавление, обновление, удаление).

# selectinload, это стратегия "жадной" загрузки связанных данных в SQLAlchemy, которая выполняет дополнительный запрос с IN (...), чтобы сразу загрузить все связанные объекты.
# То есть в нашем случае мы хотим получить элемент корзины пользователя по user_id и product_id, и сразу же иметь доступ к связанному товару (product) без дополнительных запросов.



# ПОЛУЧЕНИЕ данных ВСЕЙ корзины пользователя
@router.get("/", response_model=CartSchema)
async def get_cart(
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user), # текущий пользователь (проверка авторизации пользователя)
):
    # получаем список ВСЕХ элементов корзины CartItemModel текущего пользователя (внутри которого объект Product)
    result = await db.scalars(
        select(CartItemModel)
        .options(selectinload(CartItemModel.product)) # запрос к CartItemModel, внутри которого Product
        .where(CartItemModel.user_id == current_user.id) # где текущий пользователь есть в БД
        .order_by(CartItemModel.id) # сортировка
    )
    items = result.all()
    # считаем ВСЁ количество ВСЕХ товаров
    total_quantity = sum(item.quantity for item in items)
    # Цена всей корзины
    price_items = (
        Decimal(item.quantity) *     # <---переведем в Decimal для безопасности при расчете денег (финансовая безопасность)
        (item.product.price if item.product.price is not None else Decimal("0")) # выражение: количество текущего товара * (цену каждого товара, если она есть, иначе - 0)
        for item in items # проходимся по товарам
    )
    total_price_decimal = sum(price_items, Decimal("0.00")) # если корзина пуста, записывает 0.00

    return CartSchema( # возвращает всю корзину
        user_id=current_user.id, # пользователь
        items=items, # список ВСЕХ элементов корзины CartItemModel текущего пользователя (внутри которого объект Product)
        total_quantity=total_quantity,   # общее количество товаров
        total_price=total_price_decimal  # общая сумма товаров
    )

# Decimal("0") - т.к. Decimal(количество) * float = ОШИБКА. В Python запрещено напрямую смешивать и перемножать типы Decimal и обычные числа с плавающей точкой(float) (кроме некоторых редких исключений).
# Когда вы передаете строку "0", модуль Decimal считывает её посимвольно (как человек на бумаге) и создает число со стопроцентной точностью, полностью обходя кривое округление процессора.
# Для целого нуля Decimal(0) без кавычек технически сработает без ошибок. Но профессиональные разработчики всегда пишут кавычки абсолютно для всех чисел в Decimal (даже для Decimal("0") или Decimal("5")) просто для единообразия кода и чтобы выработать привычку никогда не передавать туда голые цифры, защитив себя от случайных ошибок округления цен.





# ДОБАВЛЕНИЕ товара в КОРЗИНУ
@router.post("/items", response_model=CartItemSchema, status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(
    payload: CartItemCreate, # полезная нагрузка (данные берутся от фронтенда и передается сюда через Pydantic-модель CartItemCreate с помощью аннотации) -  чистые данные, которые клиент (фронтенд) отправляет на сервер в теле (Body) HTTP-запроса
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user), # текущий пользователь (проверка авторизации пользователя)
):
    # ищем продукт (прсото проверка наличия товара в магазине, ничего НЕ возвращает)
    await _ensure_product_available(db, payload.product_id) # передаем сессию(чтобы функция "_ensure_product_available" сделала через неё запрос) и CartItemCreate.product_id (product_id в CartItemCreate берется от родительского класса CartItemBase)
    # await - eсли функция внутри себя делает хоть один await (например, ждет базу данных), она автоматически становится асинхронной корутиной (async def). А любую асинхронную корутину при вызове обязан «заэвейтить» тот, кто её вызывает.
    # ищем ТОВАР в КОРЗИНЕ ТЕКУЩЕГО пользователя по "product_id"
    cart_item = await _get_cart_item(db, current_user.id, payload.product_id) # передаем сессию, текущего пользователя и id-продукта
    if cart_item: # если товар в КОРЗИНЕ ТЕКУЩЕГО ЕСТЬ                          cart_item = CartItemModel или None
        cart_item.quantity += payload.quantity # к общему количеству этого товара в корзине, добавляем добавляемое количество этого-же товара
    else: # если товара в КОРЗИНЕ ТЕКУЩЕГО пользователя НЕТ
        cart_item = CartItemModel( # создаем этот товар в корзине
            user_id=current_user.id,
            product_id=payload.product_id,
            quantity=payload.quantity,
        )
        db.add(cart_item) # добавляем в сессию новый товар(объект). (сессия — это рабочий черновик перед отправкой данных в БД) - защита от поломок(Транзакции), экономия скорости (Пакетная отправка), Защита от лишней работы (Паттерн Unit of Work)(Если вы в коде сначала добавили товар, потом передумали и удалили его, или пять раз поменяли его количество — сессия не будет мучить базу данными всеми этими промежуточными шагами. В момент коммита она посмотрит на финальное состояние объекта и сделает в базу ровно один итоговый запрос, проигнорировав всю лишнюю суету.).

    await db.commit()
    # снова ищем ТОВАР в КОРЗИНЕ ТЕКУЩЕГО пользователя по "product_id"
    updated_item = await _get_cart_item(db, current_user.id, payload.product_id) # <---после команды await db.commit() происходит техническое «обнуление» объектов в ОЗУ, из-за которого этот повторный запрос и приходится делать.
    return updated_item # возвращаем его (схема ответа - response_model=CartItemSchema)         простой refresh() НЕ подойдет из-за вложенности, т.к. refresh() вернет только объект CartItemModel

# В SQLAlchemy действует железное правило: каждый объект базы данных жестко привязан к той сессии, которая его скачала





# ОБНОВЛЕНИЕ ТОЛЬКО количества товаров в корзине
@router.put("/items/{product_id}", response_model=CartItemSchema)
async def update_cart_item(
    product_id: int,
    payload: CartItemUpdate, # в этой модели только CartItemUpdate.quantity
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
):
    # ищем продукт (просто проверка наличия товара в магазине, ничего НЕ возвращает)
    await _ensure_product_available(db, product_id)
    # ищем ТОВАР В КОРЗИНЕ текущего пользователя по product_id
    cart_item = await _get_cart_item(db, current_user.id, product_id) # cart_item = CartItemModel или None
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    cart_item.quantity = payload.quantity # обновляем ВСЁ количество товара (перезаписывает старое значение новым)
    await db.commit()
    updated_item = await _get_cart_item(db, current_user.id, product_id) # возврат актуальных данных. снова ищем ТОВАР в КОРЗИНЕ ТЕКУЩЕГО пользователя по "product_id" (простой refresh() НЕ подойдет из-за вложенности, т.к. refresh() вернет только объект CartItemModel)
    return updated_item




# УДАЛЕНИЕ товара из корзины
@router.delete("/items/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_cart(
    product_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
):
    # ищем ТОВАР В КОРЗИНЕ текущего пользователя по product_id
    cart_item = await _get_cart_item(db, current_user.id, product_id)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    await db.delete(cart_item) # db.delete() - «при следующей отправке данных эту строку нужно удалить»
    await db.commit() #  изменения фиксируются (DELETE FROM cart_items WHERE id = 5;)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# db.delete() - встроенная функция SQLAlchemy (вашей ORM для работы с базой данных), которая помечает на уровне сессии объект для полного удаления из таблицы (но ещё не отправляет запрос на удаление в БД)
# Response(...) — это создание (инициализация) объекта специального класса в FastAPI, который выполняет роль контейнера для HTTP-ответа. (как пустая коробка для HTTP-ответа)
# Так тоже модно: Response(status_code=404)
# return Response(status_code=204) используется для успешных сценариев (когда всё прошло по плану, например, успешное удаление). Слово return мягко завершает функцию и отдает управление серверу.
# raise HTTPException(status_code=404) используется для ошибок. Слово raise мгновенно «взрывает» выполнение кода, прерывает любые внутренние процессы и гарантирует, что клиент получит внятное сообщение об ошибке (в поле detail), а не просто пустую страницу.




# ПОЛНАЯ ОЧИСТКА корзины
@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
):
# сразу отправляется в базу команда на уничтожение, даже не проверяя, был ли там этот товар. Это происходит за 1 запрос к БД (прямым SQL-запросом через ORM)
    await db.execute(delete(CartItemModel).where(CartItemModel.user_id == current_user.id)) # удаляет значение товара из корзины, если совпадает пользователь
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# db.execute(delete(CartItemModel)...  - удаление минуя ОЗУ и сессию

# При удалении товара из корзины через DELETE /items/{product_id}
# ИЛИ очистке всей корзины (DELETE /)
# НЕ НУЖНО вручную обновлять итоги, так как корзина не хранит агрегированные данные, а формируется динамически при каждом вызове GET /cart/.
# Агрегированные данные — это любые данные, которые были объединены, сгруппированы или подсчитаны на основе множества отдельных мелких записей: (Общая сумма товаров, общее количество товаров)

# Удаление записи из CartItemModel автоматически изменяет состояние, то есть  при следующем запросе total_quantity и total_price будут пересчитаны заново по оставшимся элементам.

# В отличие от POST и PUT запросов, где мы возвращаем обновлённый CartItemSchema, DELETE-запрос использует код 204 No Content без тела ответа, то есть клиент(фронтенд) должен сам перезапросить корзину.
# Это соответствует REST-стандартам, упрощает логику и исключает рассинхронизацию.
# 1. Никакой каши в коде: Разработчику не нужно писать сложную математику пересчета денег внутри функции удаления. Функция удаления занимается только удалением.
# 2. Никакого обмана в цифрах (защита от рассинхронизации): Итоговая сумма всей корзины всегда считается в одном-единственном месте — при запросе всей корзины.








