from fastapi import FastAPI, Request
from .log import log_middleware # импорт middleware из файла "log.py"
from app.routers import cart, categories, products, users, reviews, orders  # импортирует модуль categories.py, где определён наш маршрутизатор (router)

from fastapi.staticfiles import StaticFiles # класс позволяет обслуживать статические файлы (например, изображения, CSS, JS, PDF и т.д.) напрямую через FastAPI, без необходимости писать отдельные эндпоинты. Теперь любой файл из media/products/ будет доступен по URL: http://localhost:8000/media/products/abc123.jpg

from loguru import logger


# Мы настраиваем запись в файл "info.log" (ОБРАБОТЧИК) до того, как создается само приложение app=FastAPI(). Это гарантирует, что если при старте самого FastAPI или подключении мидлварей произойдет ошибка, логгер уже будет готов и сможет её записать.



# Приложение FastAPI
app = FastAPI(                          # инициализирует метаданные:
    title="FastAPI Интернет-магазин",   # название бэкенд-приложения (API)
    version="0.1.0",                    # версия бэкенд-приложения (API)
)



# регистрация middleware
app.middleware("http")(log_middleware)
# 1. вызывается app.middleware, принимает тип "http" (Это говорит FastAPI, что код должен срабатывать на каждый обычный HTTP-запрос)
#  В ответ этот метод возвращает внутреннюю скрытую функцию FastAPI. Эта скрытая функция и есть тот самый декоратор, который ждет, какую именно функцию ему нужно обернуть.
# 2. эта скрытая функция принимает (log_middleware) и будет запускать каждый раз, когда будет прилетать http-запрос от клиента


# Подключаем маршруты категорий, товаров и пользователей к главному объекту веб-сервера - app
app.include_router(categories.router) # Метод app.include_router() берёт маршрутизатор (экземпляр APIRouter) и добавляет его маршруты в приложение, делая их видимыми для клиентов. (router = APIRouter(...)). добавляет все маршруты из categories.py (например, GET /categories/, POST /categories/, и т.д.).
app.include_router(products.router)   # порядок вызова include_router не влияет на функциональность, но мы подключаем модули в логическом порядке (категории, затем товары)
app.include_router(users.router)
app.include_router(reviews.router)
app.include_router(cart.router)
app.include_router(orders.router)

# Корневой эндпоинт для проверки
@app.get("/") # http://localhost:8000/
async def welcome() -> dict:
    """
    Корневой маршрут, подтверждающий, что API работает.
    """
    # return {"message": "Добро пожаловать в API интернет-магазина!"} # возвращает приветственное сообщение. (Это не обязательно, но полезно для проверки, что сервер работает)
    raise Exception




# Монтирование подприложения для обслуживания статических файлов. (Монтирование - «связывает» или «подключает» физическую папку на жестком диске к определенному адресу (URL) на сайте)
# .mount() - метод FastAPI, позволяет подключить отдельное стороннее приложение или папку с файлами внутрь вашего основного веб-приложения
app.mount("/media", StaticFiles(directory="media"), name="media")
# "/media" это URL-префикс. Все запросы в браузере, начинающиеся с /media, будут обрабатываться этим подприложением
# StaticFiles(directory="media") - это экземпляр StaticFiles, который указывает, что файлы нужно брать из папки media в корне проекта (папка на диске (где лежат файлы))
# name="media" - это имя маршрута (необязательный параметр). Полезно для обратных ссылок через reverse("media") или в документации(Swagger/OpenAPI).
# reverse() — это специальная функция в Django, которая находит готовый URL-адрес по его имени (name).





