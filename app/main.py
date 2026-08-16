from fastapi import FastAPI, Request
from .log import log_middleware
from app.routers import cart, categories, products, users, reviews, orders

from fastapi.staticfiles import StaticFiles

from loguru import logger





# Приложение FastAPI
app = FastAPI(
    title="FastAPI Интернет-магазин",
    version="0.1.0",
)



# регистрация middleware
app.middleware("http")(log_middleware)



# Подключаем маршруты категорий, товаров и пользователей к главному объекту веб-сервера - app
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(users.router)
app.include_router(reviews.router)
app.include_router(cart.router)
app.include_router(orders.router)

# Корневой эндпоинт для проверки
@app.get("/")
async def welcome() -> dict:
    """
    Корневой маршрут, подтверждающий, что API работает.
    """
    # return {"message": "Добро пожаловать в API интернет-магазина!"} # возвращает приветственное сообщение. (Это не обязательно, но полезно для проверки, что сервер работает)
    raise Exception




# Монтирование подприложения для обслуживания статических файлов.
app.mount("/media", StaticFiles(directory="media"), name="media")






