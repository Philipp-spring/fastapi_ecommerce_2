import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Загружаем переменные из .env файла (временно загружает в ОЗУ системы). По умолчанию ищет файл с именем .env в текущей рабочей директории (откуда запускается скрипт).
load_dotenv()

# Строка подключения для SQLite
DATABASE_URL = "sqlite:///ecommerce.db"


# Создаём Engine (движок)
engine = create_engine(DATABASE_URL, echo=True)


# Настраиваем фабрику сеансов
SessionLocal = sessionmaker(bind=engine)


# --------------- Асинхронное подключение к PostgreSQL -------------------------

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


DATABASE_URL = os.getenv("DATABASE_URL")


# Создаём Engine (движок)
async_engine = create_async_engine(DATABASE_URL, echo=True)

# Настраиваем фабрику сеансов
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


# Определяем базовый (родительский) класс для всех ORM-моделей (совместим как с синхронным так и асинхронным кодом)
class Base(DeclarativeBase):
    pass






























































































































