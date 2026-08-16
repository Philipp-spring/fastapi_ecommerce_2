from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.db_depends import get_async_db
from app.models.cart_items import CartItem as CartItemModel
from app.models.orders import Order as OrderModel, OrderItem as OrderItemModel
from app.models.users import User as UserModel
from app.schemas import Order as OrderSchema, OrderList

router = APIRouter(prefix="/orders", tags=["orders"])


# Вспомогательная функция, которая будет заниматься загрузкой заказа с товарами
async def _load_order_with_items(db: AsyncSession, order_id: int) -> OrderModel | None:
    result = await db.scalars(
        select(OrderModel) # выбирает модель заказа
        .options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.product), # подгружает модели позиций (OrderItemModel), подгружает модели товаров (ProductModel)
        ) # selectinload() принимает в качестве аргумента не саму модель (класс), а конкретное свойство связи (Relationship),
        .where(OrderModel.id == order_id) # (В память загружаются все 3 модели). Структура: Order --> OrderItem --> Product
    )
    return result.first()

# selectinload не делает один запрос с JOIN’ами. Он выполняет несколько эффективных запросов:
# 1. Первый - заказы
# 2. Второй - все связанные OrderItem для выбранных заказов по WHERE ... IN (...)
# 3. Третий - все связанные Product для этих OrderItem (тоже по IN)

# 1. OrderModel — один главный объект (Заказ)
# 2. order.items — список [OrderItemModel, OrderItemModel, ...]
# 3. внутри каждого элемента списка в свойстве .product лежит один объект ProductModel (SQLAlchemy понимает, что там лежит список позиций, и загружает его целиком. SQLAlchemy мысленно встает внутрь ОДНОЙ конкретной позиции (OrderItemModel) из этого списка и спрашивает: «А из этой позиции куда мне идти дальше?». Вы отвечаете: «Иди в её свойство product». А свойство product внутри одной позиции — это один одиночный товар, а не список!)

# Итого 2-3 запроса для всей выборки, без N+1 (N+1 — это когда вместо одного хорошего запроса база данных делает запрос + запрос + запрос + запрос... в цикле). Если бы вы хотели именно «один запрос с JOINами», это был бы joinedload, но он тащит дубликаты строк и не всегда эффективен на больших коллекциях. (joinedload склеивает это в один SQL-отчет: База данных берет строку заказа и дублирует её столько раз, сколько позиций к ней привязано). А selectinload использует несколько IN-запросов, лучше для больших коллекций, и получается меньше дубликатов строк.


# СОЗДАНИЕ заказа (на основе текущей корзины пользователя)
@router.post("/checkout", response_model=OrderSchema, status_code=status.HTTP_201_CREATED)
async def checkout_order(
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Создаёт заказ на основе текущей корзины пользователя.
    Сохраняет позиции заказа, вычитает остатки и очищает корзину.
    """
    # Получаем текущее состояние корзины
    cart_result = await db.scalars(
        select(CartItemModel)
        .options(selectinload(CartItemModel.product)) # CartItem(одна_позиция_в_корзине) ----> Product(один_товар)   (здесь нет "Order" или "OrderItem")
        .where(CartItemModel.user_id == current_user.id) # позиции принадлежащее текущему пользователю
        .order_by(CartItemModel.id) # сортировка
    )
    cart_items = cart_result.all()
    # Проверяем, что корзина не пуста
    if not cart_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")
    # Создаём ЗАКАЗ (объект заказа)
    order = OrderModel(user_id=current_user.id) # остальные поля подставятся по умолчанию
    total_amount = Decimal("0") # общая стоимость заказа. На этом этапе мы имеем еще свеже созданный объект OrderModel и его поле total_amount ещё не инициализировано (и будет None)-->(Пока мы не вызвали session.flush() или session.commit(), SQLAlchemy НЕ заполняет это поле. Для Python этот атрибут физически равен None (точнее, возвращается специальное состояние MissingWithValue)). Соответственно, такой код внутри цикла: (order.total_amount += total_price) превращается в: None + Decimal("100.00"). А по умолчанию(в нашем случае default=0 выдаст - Decimal("0.00")--благодаря, что в mapped_column() есть настройка - Numeric(10, 2))--(макс._кол-во_цифр, цифр_после_запятой)
    # Проходим по позициям в корзине
    for cart_item in cart_items:
        product = cart_item.product # получаем конкретный (каждый) товар (в цикле)
        if not product or not product.is_active: # если товара нет или не активен - ОШИБКА
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {cart_item.product_id} is unavailable",
            )
        if product.stock < cart_item.quantity: # если наличие (каждого) товара (в цикле) МЕНЬШЕ количества этого товара в корзине - ОШИБКА
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not enough stock for product {product.name}",
            )
        # Фиксируем цену и считаем сумму заказа
        unit_price = product.price # фиксируем цену за единицу (каждого) товара (в цикле). (сохраняя в отдельной переменной)
        if unit_price is None: # если цены нет или она - 0 (<---эту проверку можно убрать, т.к. поле "price" у "Product" не может быть пустым - nullable=False)
            raise HTTPException( # ОШИБКА
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {product.name} has no price set",
            )
        total_price = unit_price * cart_item.quantity # цена за единицу УМНОЖАЕМ_НА количество товара в корзине
        total_amount += total_price # к общей стоимости заказа ПЛЮСУЕМ общую стоимость (каждого) товара (в цикле)
        # Создаём каждую ПОЗИЦИЮ ЗАКАЗА (каждого товара (в цикле)):
        order_item = OrderItemModel(
            product_id=cart_item.product_id, # №-товара
            quantity=cart_item.quantity,     # количество конкретного товара в корзине
            unit_price=unit_price, # <---unit_price берётся из текущего состояния товара, но сохраняется в OrderItem. Даже если цена потом изменится, то в заказе останется старая.
            total_price=total_price,         # общая стоимость
        )
        order.items.append(order_item) # добавляем/закидываем позицию_заказа(OrderItem) в заказ(Order). (Order.items - это и есть СПИСОК с позициями_заказов - Mapped[list["OrderItem"]])
        # Уменьшаем остатки
        product.stock -= cart_item.quantity # у каждого товара (Product) уменьшаем поле "stock"
    # Сохраняем заказ:
    order.total_amount = total_amount # сохраняем в заказ(Order) ОБЩУЮ стоимость позиций
    db.add(order) # добавляем заказ(Order) в сессию
    # Очищаем КОРЗИНУ:
    await db.execute(delete(CartItemModel).where(CartItemModel.user_id == current_user.id)) # удаляем объекты позиций_КОРЗИНЫ(CartItem), если они принадлежат текущему пользователю
    await db.commit() # сохраняем изменения сессии (фиксирует заказ(Order) в БД)            # Для DELETE используем только execute()! Т.к. метод db.scalars() предназначен строго для запросов чтения (select), которые возвращают строки с данными (для чтения)
    # Перезагружаем заказ с полными данными в ОЗУ (чтобы вернуть клиенту(фронтенду)):
    created_order = await _load_order_with_items(db, order.id) # Структура загрузки: Order --> OrderItem --> Product (refresh() - НЕ подойдет, т.к. не умеет делать цепочку запросов)
    if not created_order: # если заказа НЕТ - ОШИБКА (проверка на всякий случай)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load created order",
        )
    return created_order # возвращаем перезагруженный заказ


# order.items.append(order_item)
# order.items — это не обычный список, это relationship-коллекция, у которой под капотом «магический» класс от SQLAlchemy
# SQLAlchemy делает за кулисами примерно такое:
# 1. Добавляет объект в коллекцию
# 2. Выставляет ему order_id = order.id
# 3. Помечает объект как “изменённый”
# 4. Следит, чтобы при session.commit() INSERT пошёл с корректным ForeignKey
# То есть append автоматически связывает объекты через внешний ключ
# 🔥 Почему product “не при чём” в этом контексте
# Именно потому, что ты добавляешь OrderItem к Order, а не к Product:
# order.items.append(item)
# Операция логически означает: «Этот OrderItem теперь принадлежит этому Order»




# ПОЛУЧЕНИЕ заказов текущего пользователя с простой пагинацией
@router.get("/", response_model=OrderList)
async def list_orders(
    page: int = Query(1, ge=1),                 # №-страницы
    page_size: int = Query(10, ge=1, le=100),   # размер страницы (сколько заказов на странице)
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
    ):
    """
    Возвращает заказы текущего пользователя с простой пагинацией.
    """
    # Считаем общее количество заказов (это нужно чтобы фронтенд мог отображать общее количество страниц и индикатор например «показано 1–10 из 42»)
    total = await db.scalar( # <---сюда попадает число
        select(func.count(OrderModel.id)).where(OrderModel.user_id == current_user.id)
    )
    # Загружаем заказы с полными данными
    result = await db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.product)) # жадная загрузка:  Order ---> OrderItem ---> Product
        .where(OrderModel.user_id == current_user.id) # заказы текущего пользователя
        .order_by(OrderModel.created_at.desc()) # сортируем заказы по дате создания (от новых к старым)
        .offset((page - 1) * page_size) # пагинация: сколько строк пропустить
        .limit(page_size) # сколько строк отобразить
    ) # На странице выводятся именно заказы текущего пользователя, но выстроены они в виде матрешки: Заказ ---> Позиции ---> Товары.
    orders = result.all()

    return OrderList(items=orders, total=total or 0, page=page, page_size=page_size) # (Pydantic OrderList)




# ПОЛУЧЕНИЕ полной информации по заказу (пользователя) включая все позиции и товары
@router.get("/{order_id}", response_model=OrderSchema)
async def get_order(
    order_id: int, # №-заказа
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
    ):
    """
    Возвращает детальную информацию по заказу, если он принадлежит пользователю.
    """
    order = await _load_order_with_items(db, order_id) # структура загрузки: Order --> OrderItem --> Product
    if not order or order.user_id != current_user.id: # если нет заказа или заказ не принадлежит текущему пользователю
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found") # ОШИБКА. 404 код ошибки, а не 403 (Это важно с точки зрения безопасности, так как мы не раскрываем, существует ли заказ с таким ID у другого пользователя)
    return order # возвращаем заказ

# 403 Forbidden (Доступ запрещен) ---> уязвимость: злоумышленник знает, что заказ существует и начнёт подбирать id-пользователя
# 404 Not Found (Не найдено)      ---> для чужого пользователя эта страница будет выглядеть точно так же, как если бы он ввел случайный, несуществующий ID. Система отвечает: «Такого заказа нет (для тебя)». Это полностью лишает злоумышленника информации.
