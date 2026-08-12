FROM python:3.11-slim

# Устанавливаем системные зависимости, включая ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Создаем директорию для временных файлов
RUN mkdir -p /tmp/bot_temp

# Запускаем бота
CMD ["python", "telegram_bot.py"]

