# Модели SQLAlchemy # Модели SQLAlchemy (ORM-модели)

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship # mapped_column(...) (Конструктор колонки) - специальная функция SQLAlchemy, которая собирает все настройки ниже и преобразует их в реальный SQL-код для создания таблицы.

from app.database import Base


class User(Base):
    __tablename__ = "users"
    #  Integer - для БД (можно не ставить, т.к. уже есть [int] для Python и SQLAlchemy понимает, что нужно подставлять)
    id: Mapped[int] = mapped_column(Integer, primary_key=True) # Добавлять autoincrement=True не нужно SQLAlchemy для целочисленных полей, при наличии "primary_key=True" (например, Mapped[int]) этот параметр уже включен по умолчанию.
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False) # unique=True автоматически создает индекс в базе данных, поэтому "index=True" НЕ НУЖЕН. index=True (Индекс для скорости). Приказывает базе данных создать специальную поисковую структуру (индекс) для этого столбца. Поскольку при авторизации (или проверке JWT) вы будете постоянно искать пользователя по его email (SELECT * FROM users WHERE email = ...), индекс позволяет базе данных находить нужную строку мгновенно, не перебирая миллионы других записей.
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True) # default=True - по умолчанию - True
    role: Mapped[str] = mapped_column(String, default="buyer")  # "buyer" or "seller" or "admin"

    products: Mapped[list["Product"]] = relationship("Product", back_populates="seller") # <--связь с продуктами (list["Product"]  <--много продуктов)
    categories: Mapped[list["Category"]] = relationship("Category", back_populates="admin")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="user") # один ко многим
    cart_items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="user", cascade="all, delete-orphan") # Если User удалён, то автоматически удаляет все дочерние(CartItem) объекты/строки
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user", cascade="all, delete-orphan") # один пользователь - много заказов

# index=True
# 1. Замедление при Записи данных (INSERT, UPDATE, DELETE)
# Индекс ускоряет только чтение (SELECT). Но если вы часто добавляете или меняете данные, индекс начинает тормозить систему.
# Почему так происходит? Представьте, что вы добавили нового пользователя. Базе данных нужно не просто вставить строчку в конец таблицы, ей приходится открыть свой скрытый алфавитный справочник (индекс), найти там правильное место по алфавиту, раздвинуть записи и вставить новый email туда.
# Результат: Если у таблицы 10 индексов, то при каждой регистрации пользователя база данных будет делать в 10 раз больше работы, перестраивая все 10 справочников.
# 2. Медленная работа при низкой уникальности данных (Кардинальность)
# Индекс становится вредным и может даже замедлить поиск, если вы ставите его на поле, где значения постоянно повторяются.
# Яркий пример — поле role из вашего кода (где есть только "buyer" или "seller"):
# Представьте, что у вас в базе 1 000 000 пользователей. Из них 500 000 — это покупатели (buyer).
# Если вы поставите index=True на поле role и попросите базу: «Найди мне всех buyer», индекс не поможет. Базе данных все равно придется прочитать половину всей таблицы.
# В этом случае поиск через индекс выйдет даже медленнее, потому что база сначала потратит время на чтение индекса, поймет, что совпадений слишком много, и всё равно пойдет сканировать саму таблицу

# лавное правило разработчика:
# Ставим индекс: на поля с высокой уникальностью, по которым идет точечный поиск (email, id, slug статьи, phone).
# НЕ ставим индекс: на поля, где данные часто повторяются (role, is_active, gender), и на таблицы, в которые постоянно (каждую секунду) записываются новые логи или метрики.

# Составной (или композитный) индекс — это один единый индекс, который создается сразу для двух или более колонок одной таблицы вместе.

# email: Уникальный столбец с индексом (unique=True, index=True) для предотвращения дублирования.
# hashed_password: Хранит пароль, зашифрованный с помощью bcrypt, для защиты данных.
# is_active: Булев флаг, по умолчанию True, для мягкого удаления пользователей.
# role: Определяет роль пользователя ("buyer" или "seller"), по умолчанию "buyer".
# products: Связь с таблицей products через relationship, позволяющая получать список товаров продавца.