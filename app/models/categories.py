# Модели SQLAlchemy (ORM-модели)

from sqlalchemy import Integer, String, Boolean # Типы данных SQLAlchemy для столбцов (унаследованный от DeclarativeBase)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey # внешний ключ

from app.database import Base # импортируем базовый класс Base


class Category(Base):
    __tablename__ = "categories" # задает имя таблицы в базе данных

    id: Mapped[int] = mapped_column(Integer, primary_key=True) # Соответствует id в Pydantic-модели Category из app/schemas.py (Это поле является Primary Key (Первичным ключом) для всей таблицы categories, он уникален для каждой строки, независимо от того, ссылаются ли подкатегории на одного родителя или нет (все id товаров - РАЗНЫЕ))
    name: Mapped[str] = mapped_column(String(50), nullable=False) # Соответствует name (3-50 символов) в CategoryCreate и Category.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True) #  (Иерархия / Рекурсия). Позволяет указать родительскую категорию или "None" для главных категорий. Соответствует parent_id в Pydantic-моделях. (Чтобы Pydantic-модель правильно принимала или отдавала это поле, её структура должна полностью повторять логику | None). В этой строчке кода создается рекурсивная связь (когда таблица ссылается сама на себя). Это классический способ организовать структуры в виде дерева или иерархии (например: категории и подкатегории, или папки и подпапки) внутри одной таблицы базы данных
# База данных понимает это так: каждая строка в этой таблице может указать на id другой строки в этой же самой таблице.
# ForeignKey("categories.id"): Указывает имя вашей текущей таблицы (categories) и колонку (id). Именно это замыкает связь в кольцо.
# Mapped[int | None]: Говорит SQLAlchemy на уровне типов Python, что в этой ячейке может лежать либо целое число (int), либо ничего (None). (Если бы мы сделали это поле обязательным (NOT NULL), то мы бы никогда не смогли создать самую первую, главную категорию. При попытке создать категорию «Электроника», база данных потребовала бы заполнить parent_id. Но у «Электроники» нет родителя! Возник бы замкнутый круг.Значение None (NULL) служит маркером вершины дерева. Если у записи parent_id равен None, значит это главная корневая категория. Если там стоит число, то это подкатегория.)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True) # Новое поле
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, server_default="4") # <--"один_ко_многим" (дочерняя таблица "categories" ссылается на id таблицы "users" через ForeignKey("users.id").
                                                                            # server_default - устанавливает значение по умолчанию на уровне самой базы данных
    admin: Mapped["User"] = relationship(back_populates="categories")

    products: Mapped[list["Product"]] = relationship(back_populates="category") # Атрибут связи, представляющий список объектов Product, связанных с категорией. Тип Mapped[list["Product"]] указывает, что это список объектов модели Product. Параметр back_populates="category" связывает эту связь с атрибутом category в модели Product.
    # у самой главной таблицы родителя нет - None
    parent: Mapped["Category | None"] = relationship(back_populates="children", remote_side="Category.id") # родитель(главная категория). remote_side - указывает, какая колонка представляет родительскую (удаленную) сторону связи. Позволяет сослаться таблице на саму себя, указывая какая колонка является главной(родительской), чтобы SQLAlchemy не запутался (одна строка одной таблицы ссылается на другую строку этой же таблицы)
    # эти 2 связи находятся в ОДНОЙ модели!                               (в кавычках - отложенная инициализация)                         remote_side="Category.id" означает что Category.id это колонка РОДИТЕЛЬСКОГО объекта, а parent_id колонка ДОЧЕРНЕГО.
    children: Mapped[list["Category"]] = relationship(back_populates="parent") # дети(подкатегории)
    # remote_side — указывает на колонку родителя (id), задавая направление вверх.
    # back_populates — связывает два поля друг с другом. Благодаря ему SQLAlchemy понимает, что children — это противоположное направление, то есть вниз. (два конца одной верёвки)
    # смотрим вверх - один родитель ["Category | None"], смотрим вниз - много детей [list["Category"]] (один к одному)

# - Внешний ключ: parent_id ссылается на id в таблице categories. Например, категория «Смартфоны» с parent_id=1 принадлежит категории с id=1 («Электроника»). Если parent_id=None, категория является главной.
# - relationship:
#   - category.parent возвращает родительскую категорию (или None для главных категорий).
#   - category.children возвращает список подкатегорий.
# - back_populates: Синхронизирует обе стороны связи, чтобы добавление подкатегории в category.children автоматически обновляло child.parent.



# Чтобы Pydantic умел автоматически читать данные из объекта SQLAlchemy, в Pydantic включают специальный переключатель — model_config = ConfigDict(from_attributes=True)
# SQLAlchemy модели соответствуют Pydantic-моделям из app/schemas.py, что упростит интеграцию в будущем.

# ForeignKey: Задаёт связь на уровне базы данных, обеспечивая целостность. Например, SQLite не позволит создать товар с category_id, которого нет в таблице categories.
# relationship: Упрощает доступ к связанным данным в Python. Вместо SQL-запросов (например, SELECT * FROM products WHERE category_id = 1), вы можете использовать category.products для получения товаров или product.category для доступа к категории.
# back_populates: Синхронизирует обе стороны связи, чтобы изменения в category.products отражались в product.category и наоборот.

# # Проверка моделей: Проверяем SQL-код, который SQLAlchemy генерирует для создания таблиц
# if __name__ == "__main__": # <--гарантирует, что код внутри этого блока выполнится только тогда, когда вы запустите этот файл напрямую как скрипт. Если этот файл будет импортирован в другой модуль, данный блок кода проигнорируется.
#     from sqlalchemy.schema import CreateTable # служебный класс CreateTable, который умеет брать внутреннее описание таблицы из Python и переводить его в текстовую SQL-команду для создания таблицы.
#     from app.models.products import Product # Импортирует вашу SQLAlchemy-модель товара (Product) из соответствующего файла, чтобы скрипт мог прочитать её структуру.
#     print(CreateTable(Category.__table__)) # Category.__table__ обращается к скрытому объекту метаданных внутри модели, где хранится вся структура SQL (имя таблицы, столбцы, типы, ограничения).
#     print(CreateTable(Product.__table__)) # CreateTable(...) оборачивает эти метаданные и генерирует SQL-инструкцию CREATE TABLE categories (...)


# CREATE TABLE categories (
# 	id INTEGER NOT NULL,
# 	name VARCHAR(50) NOT NULL,
# 	parent_id INTEGER,
# 	is_active BOOLEAN NOT NULL,
# 	PRIMARY KEY (id),                                          <-----id автоматически индексируется благодаря primary_key=True, поэтому явный индекс не создаётся.
# 	FOREIGN KEY(parent_id) REFERENCES categories (id)          <-----Таблица содержит поле parent_id (необязательное, может быть NULL) и внешний ключ FOREIGN KEY(parent_id) REFERENCES categories (id), указывающий на id той же таблицы.
# )
#
#                                                           Атрибуты products, parent, и children не влияют на SQL-схему, так как relationship работает на уровне Python!!!
#
# CREATE TABLE products (
# 	id INTEGER NOT NULL,
# 	name VARCHAR(100) NOT NULL,
# 	description VARCHAR(500),
# 	price NUMERIC(10, 2) NOT NULL,
# 	image_url VARCHAR(200),
# 	stock INTEGER NOT NULL,
# 	is_active BOOLEAN NOT NULL,
# 	category_id INTEGER NOT NULL,
# 	PRIMARY KEY (id),
# 	FOREIGN KEY(category_id) REFERENCES categories (id)
# )

# - categories: Таблица без изменений, так как relationship (products) не влияет на SQL-схему.
# - products: Добавлено поле category_id (обязательное, NOT NULL) и внешний ключ FOREIGN KEY(category_id) REFERENCES categories (id), указывающий на таблицу categories.
# - Первичные ключи (id) не содержат явных индексов, так как primary_key=True автоматически индексирует их, как обсуждалось ранее.

# Маппер (переводчик) — это специальный механизм внутри SQLAlchemy, который стоит посередине между Python и SQL и переводит всё с одного языка на другой.
# Все модели наследуются от Base, который содержит реестр (Base.registry) всех классов, помеченных как модели.
# И SQLAlchemy ищет класс Product в реестре мапперов (Base.registry), когда настраивает модели, и когда он натыкается на строку "Product", то он понимает с какой моделью нужно сопоставить эту строку (поэтому импорты ORM-классов(моделей) делать друг в друга не нужно!).
# А если мы добавим импорты, то получится что Category импортирует Product, а Product наоборот будет импортировать Category. В результате получим ошибку циклического импорта)


# Вот так можно получить класс модели по его строковому имени:
# print(Base.registry._class_registry['Product'])    ------>  <class 'app.models.products.Product'>           <--- абсолютный путь (импортный путь) к классу Product внутри структуры проекта

# app — это корневая папка вашего проекта (пакет).
# .models — это подпапка models, где вы храните все файлы баз данных.
# .products — это конкретный файл products.py, в котором написан код товара.
# .Product — это сам Python-класс (модель SQLAlchemy) внутри этого файла.
