from app.database import Base
from sqlalchemy import ForeignKey, String, Numeric, func, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from decimal import Decimal





# Общая информация о заказе
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True) # №-заказа
    user_id: Mapped[int] = mapped_column( # пользователь (обязательное поле)
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False) # общая сумма. (default= срабатывает при вставке в БД (flush/commit), а не в момент создания объекта OrderModel())
    created_at: Mapped[datetime] = mapped_column( # дата создания
        DateTime(timezone=True), server_default=func.now(), nullable=False # server_default= - время будет установлено на стороне базы данных в момент СОЗДАНИЯ строки - INSERT.
    )
    updated_at: Mapped[datetime] = mapped_column( # дата обновления          "server_default=" - время будет установлено на стороне базы данных в момент СОЗДАНИЯ строки - INSERT, а также "onupdate=" ОБНОВЛЯТЬСЯ в момент вызова - UPDATE
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False # обновляется при каждом изменении строки благодаря onupdate=   (DateTime(timezone=True) конвертирует время в UTC и в "server_default=func.now()" и в "onupdate=func.now()")
    )
    # Но если мы в ручную передадим значения "created_at" и "updated_at", то Postgres возьмёт ваше значение и НЕ применит этот дефолт (server_default= и onupdate= игнорируются)

    user: Mapped["User"] = relationship("User", back_populates="orders") # один пользователь - много заказов
    items: Mapped[list["OrderItem"]] = relationship( # один_заказ - много_позиция_заказов
        "OrderItem", back_populates="order", cascade="all, delete-orphan" # при удалении заказа(Order) удалятся все его позиции(OrderItem)
    )

# Поля created_at и updated_at это не просто технические метки времени. Это критически важные данные для аудита, аналитики и пользовательского опыта. Например, покупатель хочет знать, когда именно он оформил заказ. А продавец хочет знать когда последний раз менялся статус. Администратор системы может отследить, как долго заказ находится в статусе Ожидает оплаты. А в случае споров эти временные метки могут стать доказательством в юридическом смысле.


# Самое главное, это то, что нам нужна информация о цене товара на момент заказа. Ведь цена товара может меняться: скидки, акции и тд. И если мы будем хранить только product_id и текущее состояние товара, то через месяц пользователь увидит в истории заказов цену, которая уже не соответствует той, за которую он платил. А в нашем случае записи в OrderItem фиксируют unit_price и total_price на момент покупки.
# Позиции в заказе
class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column( # №-заказа
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column( # №-товара
        ForeignKey("products.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # количество
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False) # цена за единицу
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False) # общая сумма

    order: Mapped["Order"] = relationship("Order", back_populates="items") # один_заказ - много_позиция_заказов
    product: Mapped["Product"] = relationship("Product", back_populates="order_items") # один_товар - много_позиций_заказов (т.е. ОДИН товар разные пользователи могут класть в МНОГО РАЗНЫХ ЗАКАЗОВ)

