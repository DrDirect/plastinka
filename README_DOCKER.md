# Запуск бота в Docker

## Требования

- Docker
- Docker Compose

## Быстрый запуск

1. Убедитесь, что файл `base.png` находится в корне проекта
2. Запустите контейнер:
```bash
docker-compose up -d
```

3. Просмотр логов:
```bash
docker-compose logs -f
```

4. Остановка:
```bash
docker-compose down
```

## Пересборка образа

Если изменили код или зависимости:
```bash
docker-compose build
docker-compose up -d
```

## Структура

- `Dockerfile` - образ с Python, ffmpeg и всеми зависимостями
- `docker-compose.yml` - конфигурация для запуска
- `.dockerignore` - файлы, которые не нужно копировать в образ

## Переменные окружения

Токен бота можно передать через переменную окружения, изменив `docker-compose.yml`:

```yaml
environment:
  - BOT_TOKEN=your_token_here
```

И обновив `telegram_bot.py` для чтения из переменной окружения:
```python
import os
BOT_TOKEN = os.getenv('BOT_TOKEN', '8576051092:AAG0f8AXbcCS83NWOWVWpyuY8hv9pOlrgrE')
```

