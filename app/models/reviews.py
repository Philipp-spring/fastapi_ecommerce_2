# Модели SQLAlchemy (ORM-модели)

from app.database import Base

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, DateTime # <--  Явно говорим SQLAlchemy сделать в Postgres тип TIMESTAMP WITH TIME ZONE
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Numeric




class Review(Base):
    __tablename__ = "reviews"
                                                # autoincrement=True - можно не писать (по умолчанию)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) # nullable=False - по умолчанию          ForeignKey("__tablename__.id")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)  # <--связывает отзыв с продуктом с пользователкем
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False) # <--связывает отзыв с продуктом
    comment: Mapped[str | None] = mapped_column()
    comment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default = lambda: datetime.now(timezone.utc)) # Явно говорим SQLAlchemy сделать в Postgres тип TIMESTAMP WITH TIME ZONE
    grade: Mapped[Decimal] = mapped_column(Numeric(precision=3, scale=2)) # Numeric здесь - это на тип на стороне БД (а Decimal - на стороне Python)
    is_active: Mapped[bool] = mapped_column(default=True)

    product: Mapped["Product"] = relationship("Product", back_populates="reviews") # один ко многим
    user: Mapped["User"] = relationship("User", back_populates="reviews") # один ко многим
    # один отзыв имеет 1-го пользователя и 1 продукт


# Precision и Scale
# precision=3 (Точность): Это общее количество цифр в числе (включая цифры как до, так и после запятой).
# scale=2 (Масштаб): Это количество цифр строго после запятой.


# "server_default" - принимает SQL функции!
# mapped_column(server_default = func.now())        <---ОК (время будет всегда уникальным, но не учитывает часовые пояса)
# mapped_column(server_default = datetime.now())    <---ОШИБКА

# Можно так:
# mapped_column(default = lambda: datetime.now(timezone.utc))   <----чтобы во всех часовых поясах создавалось одинаковое UTC-время

# Лямбда-функция используется для того, чтобы отложить выполнение кода на будущее
# Если не использовать лямбду или ссылку на функцию, то время вычислится всего один раз — в момент, когда проект запускается
# SQLAlchemy (точнее, её внутренний менеджер сессий) в момент выполнения метода db.flush() или db.commit()



















































