# Логирование

from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger



# Обработчик (добавляем)
logger.add("info.log", format="Log: [{extra[log_id]}:{time} - {level} - {message}]", level="INFO", enqueue=True)




# ПРОСЛОЙКА ДЛЯ ЛОГГИРОВАНИЯ ВСЕГО ТРАФИКА НАШЕГО ПРИЛОЖЕНИЯ.
# @app.middleware("http")   <----если прописываем эту функци в другом файле (НЕ main.py), то декоратор здесь уже НЕ пишем (это будет просто функция)
async def log_middleware(request: Request, call_next):
    log_id = str(uuid4())
    with logger.contextualize(log_id=log_id):
        try:
            response = await call_next(request)
            if response.status_code in [401, 402, 403, 404]:
                logger.warning(f"Request to {request.url.path} failed") ь
            else:
                logger.info('Successfully accessed ' + request.url.path)
        except Exception as ex:
            logger.error(f"Request to {request.url.path} failed: {ex}")
            response = JSONResponse(content={"success": False}, status_code=500)
        return response             #
