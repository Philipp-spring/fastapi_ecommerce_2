# Используем готовый официальный образ Python
FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и устанавливаем их (внутри Докера всё пройдет без ошибок)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код
COPY . .

# Команда запуска (если главный файл называется не main.py, замените "main:app")
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

