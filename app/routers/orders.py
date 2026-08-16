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
        select(OrderModel)
        .options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.product),
        )
        .where(OrderModel.id == order_id)
    )
    return result.first()



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
        .options(selectinload(CartItemModel.product))
        .where(CartItemModel.user_id == current_user.id)
        .order_by(CartItemModel.id)
    )
    cart_items = cart_result.all()
    # Проверяем, что корзина не пуста
    if not cart_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")
    # Создаём ЗАКАЗ (объект заказа)
    order = OrderModel(user_id=current_user.id) #
    total_amount = Decimal("0")
    # Проходим по позициям в корзине
    for cart_item in cart_items:
        product = cart_item.product
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {cart_item.product_id} is unavailable",
            )
        if product.stock < cart_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not enough stock for product {product.name}",
            )
        # Фиксируем цену и считаем сумму заказа
        unit_price = product.price
        if unit_price is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {product.name} has no price set",
            )
        total_price = unit_price * cart_item.quantity
        total_amount += total_price
        # Создаём каждую ПОЗИЦИЮ ЗАКАЗА
        order_item = OrderItemModel(
            product_id=cart_item.product_id,
            quantity=cart_item.quantity,
            unit_price=unit_price,
            total_price=total_price,
        )
        order.items.append(order_item)
        # Уменьшаем остатки
        product.stock -= cart_item.quantity
    # Сохраняем заказ:
    order.total_amount = total_amount
    db.add(order)
    # Очищаем КОРЗИНУ:
    await db.execute(delete(CartItemModel).where(CartItemModel.user_id == current_user.id))
    await db.commit()
    # Перезагружаем заказ с полными данными в ОЗУ
    created_order = await _load_order_with_items(db, order.id)
    if not created_order:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load created order",
        )
    return created_order





# ПОЛУЧЕНИЕ заказов текущего пользователя с простой пагинацией
@router.get("/", response_model=OrderList)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
    ):
    """
    Возвращает заказы текущего пользователя с простой пагинацией.
    """
    # Считаем общее количество заказов
    total = await db.scalar(
        select(func.count(OrderModel.id)).where(OrderModel.user_id == current_user.id)
    )
    # Загружаем заказы с полными данными
    result = await db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.product))
        .where(OrderModel.user_id == current_user.id)
        .order_by(OrderModel.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    orders = result.all()

    return OrderList(items=orders, total=total or 0, page=page, page_size=page_size)




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
    order = await _load_order_with_items(db, order_id)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

