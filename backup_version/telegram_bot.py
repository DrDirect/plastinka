#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram бот для обработки MP3 файлов.
Создает обложку с пластинкой, вырезает аудио отрезок и создает видео.
"""

import os
import sys
import io
import random
import subprocess
import shutil
import tempfile
import logging
import requests
from pathlib import Path
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Токен бота
BOT_TOKEN = "8576051092:AAG0f8AXbcCS83NWOWVWpyuY8hv9pOlrgrE"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def extract_cover_from_mp3(mp3_path):
    """Извлекает обложку альбома из MP3 файла."""
    try:
        from mutagen.id3 import ID3, APIC
        
        try:
            tags = ID3(mp3_path)
        except ID3NoHeaderError:
            return None
        
        for key in tags.keys():
            if key.startswith('APIC'):
                apic = tags[key]
                if hasattr(apic, 'data') and apic.data:
                    try:
                        cover_image = Image.open(io.BytesIO(apic.data))
                        return cover_image
                    except Exception as e:
                        logger.error(f"Ошибка при обработке изображения: {e}")
                        continue
        
        try:
            audio = MP3(mp3_path)
            for key in audio.keys():
                if key.startswith('APIC'):
                    apic = audio[key]
                    if hasattr(apic, 'data') and apic.data:
                        try:
                            cover_image = Image.open(io.BytesIO(apic.data))
                            return cover_image
                        except Exception as e:
                            logger.error(f"Ошибка при обработке изображения: {e}")
                            continue
        except Exception as e:
            logger.error(f"Ошибка при чтении MP3: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при извлечении обложки: {e}")
    
    return None


def create_album_cover(mp3_path, base_template_path, output_path):
    """Создает обложку альбома с пластинкой."""
    album_cover = extract_cover_from_mp3(mp3_path)
    
    if album_cover is None:
        return False
    
    album_cover = album_cover.resize((300, 300), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (800, 800), (255, 255, 255, 0))
    
    x_offset = (800 - 300) // 2
    y_offset = (800 - 300) // 2
    canvas.paste(album_cover, (x_offset, y_offset))
    
    vinyl_template = Image.open(base_template_path).convert('RGBA')
    
    if vinyl_template.size != (800, 800):
        vinyl_template = vinyl_template.resize((800, 800), Image.Resampling.LANCZOS)
    
    canvas = Image.alpha_composite(canvas, vinyl_template)
    canvas.save(output_path, 'PNG')
    
    return True


def get_audio_duration(mp3_path):
    """Получает длительность аудио файла в секундах."""
    try:
        audio = MP3(mp3_path)
        return audio.info.length
    except Exception as e:
        logger.error(f"Ошибка при получении длительности: {e}")
        return None


def extract_random_segment(mp3_path, segment_length=60, output_path=None):
    """Вырезает случайный отрезок из MP3 файла. Если трек короче segment_length, использует весь трек."""
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        return False
    
    duration = get_audio_duration(mp3_path)
    if duration is None:
        return False
    
    # Если трек короче нужного отрезка, используем весь трек целиком
    if duration < segment_length:
        logger.info(f"Длительность трека ({duration:.2f} сек) меньше {segment_length} сек, используем весь трек")
        try:
            # Просто копируем весь файл
            shutil.copy2(mp3_path, output_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при копировании файла: {e}")
            return False
    
    # Если трек достаточно длинный, вырезаем случайный отрезок
    max_start = duration - segment_length
    start_time = random.uniform(0, max_start)
    
    try:
        subprocess.run(
            [
                ffmpeg_path,
                '-i', mp3_path,
                '-ss', str(start_time),
                '-t', str(segment_length),
                '-acodec', 'copy',
                '-y',
                output_path
            ],
            check=True,
            capture_output=True
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при вырезании отрезка: {e}")
        return False


def create_rotating_video(cover_path, audio_path, output_path, rotation_speed=1.0/3, size=640):
    """
    Создает квадратное видео с вращающейся обложкой и аудио для video note.
    
    Args:
        cover_path: Путь к обложке
        audio_path: Путь к аудио
        output_path: Путь для сохранения видео
        rotation_speed: Скорость вращения
        size: Размер квадратного видео (по умолчанию 512x512 для video note)
    """
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        return False
    
    # Создаем фильтр для строго квадратного видео для video note
    # Для video note нужно строго квадратное видео с правильными метаданными
    # Обложка уже квадратная 800x800, масштабируем до нужного размера и вращаем
    # Важно: используем force_original_aspect_ratio=disable для строгого квадрата
    rotate_filter = f'scale={size}:{size}:force_original_aspect_ratio=disable,rotate=2*PI*t*{rotation_speed}:fillcolor=black@0:ow={size}:oh={size}'
    
    # Создаем видео с аудио для video note
    # Используем параметры, максимально приближенные к тому, что использует Telegram при записи с камеры
    # Telegram использует базовый профиль H.264 с AAC аудио
    cmd = [
        ffmpeg_path,
        '-loop', '1',
        '-i', cover_path,
        '-i', audio_path,
        '-vf', rotate_filter,
        '-c:v', 'libx264',
        '-profile:v', 'baseline',  # Базовый профиль (как у мобильных камер)
        '-level', '3.1',
        '-crf', '28',  # Баланс между качеством и размером
        '-preset', 'medium',
        '-maxrate', '2M',  # Максимальный битрейт
        '-bufsize', '4M',  # Размер буфера
        '-c:a', 'aac',
        '-b:a', '96k',  # Битрейт аудио
        '-ar', '44100',  # Стандартная частота дискретизации
        '-ac', '2',  # Стерео
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-r', '30',  # Стандартная частота кадров
        '-g', '30',  # GOP size (1 секунда при 30 fps)
        '-shortest',  # Останавливаем когда закончится самое короткое (аудио)
        '-f', 'mp4',  # Явно указываем формат MP4
        '-y',
        output_path
    ]
    
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            encoding='utf-8',
            errors='ignore'
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании видео: {e}")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text(
        "Привет! Отправь мне MP3 файл, и я создам для него:\n"
        "🎵 Обложку с пластинкой\n"
        "🎶 Случайный 60-секундный аудио отрезок\n"
        "🎬 Видео с вращающейся обложкой\n\n"
        "Просто отправь MP3 файл!"
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает полученный MP3 файл."""
    message = update.message
    
    # Определяем файл и проверяем тип
    file = None
    file_name = None
    
    if message.audio:
        file = message.audio
        file_name = message.audio.file_name or "audio.mp3"
    elif message.document:
        file = message.document
        file_name = message.document.file_name
        # Проверяем расширение
        if not (file_name and file_name.lower().endswith('.mp3')):
            await message.reply_text("Пожалуйста, отправь MP3 файл.")
            return
    else:
        await message.reply_text("Пожалуйста, отправь MP3 файл.")
        return
    
    # Создаем временную директорию для работы
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Скачиваем файл
        file_obj = await context.bot.get_file(file.file_id)
        mp3_path = os.path.join(temp_dir, file_name or "audio.mp3")
        # Скачиваем файл (в версии 20+ python-telegram-bot используем download_to_drive)
        # Скачиваем в текущую директорию с именем файла, потом перемещаем
        downloaded_path = await file_obj.download_to_drive()
        # Перемещаем в нужное место
        if downloaded_path and os.path.exists(str(downloaded_path)):
            if str(downloaded_path) != mp3_path:
                shutil.move(str(downloaded_path), mp3_path)
        elif os.path.exists(file_name or "audio.mp3"):
            # Если файл скачался с именем из file_name
            shutil.move(file_name or "audio.mp3", mp3_path)
        
        # Проверяем наличие base.png
        base_template = 'base.png'
        if not os.path.exists(base_template):
            await message.reply_text("❌ Ошибка: файл base.png не найден.")
            return
        
        # Этап 1: Создание обложки
        cover_path = os.path.join(temp_dir, "cover.png")
        if not create_album_cover(mp3_path, base_template, cover_path):
            await message.reply_text("❌ Ошибка: не удалось создать обложку. Убедитесь, что в MP3 есть обложка.")
            return
        
        # Этап 2: Вырезание аудио отрезка
        audio_path = os.path.join(temp_dir, "sample.mp3")
        if not extract_random_segment(mp3_path, segment_length=60, output_path=audio_path):
            await message.reply_text("❌ Ошибка: не удалось вырезать аудио отрезок.")
            return
        
        # Этап 3: Создание видео для video note (квадратное, 640x640 - стандарт для video note)
        video_path = os.path.join(temp_dir, "video.mp4")
        # Используем размер 640x640 для video note (стандартный размер по документации Telegram)
        if not create_rotating_video(cover_path, audio_path, video_path, rotation_speed=1.0/3, size=640):
            await message.reply_text("❌ Ошибка: не удалось создать видео.")
            return
        
        # Дополнительная проверка: убеждаемся, что видео квадратное
        ffprobe_path = shutil.which('ffprobe')
        if ffprobe_path:
            try:
                probe_cmd = [
                    ffprobe_path,
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height',
                    '-of', 'json',
                    video_path
                ]
                result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
                import json
                probe_data = json.loads(result.stdout)
                if 'streams' in probe_data and len(probe_data['streams']) > 0:
                    width = probe_data['streams'][0].get('width')
                    height = probe_data['streams'][0].get('height')
                    logger.info(f"Размеры видео: {width}x{height}")
                    if width != height:
                        logger.warning(f"⚠️ Видео не квадратное: {width}x{height}, пересоздаю...")
                        # Пересоздаем видео с правильными размерами
                        if not create_rotating_video(cover_path, audio_path, video_path, rotation_speed=1.0/3, size=512):
                            await message.reply_text("❌ Ошибка: не удалось пересоздать квадратное видео.")
                            return
            except Exception as e:
                logger.warning(f"Не удалось проверить видео через ffprobe: {e}")
        
        # Проверяем размер файла (video note должен быть до 8 МБ по документации)
        file_size = os.path.getsize(video_path) / (1024 * 1024)  # Размер в МБ
        logger.info(f"Размер видео файла: {file_size:.2f} МБ")
        if file_size > 8:
            await message.reply_text(f"❌ Ошибка: размер видео слишком большой ({file_size:.2f} МБ). Максимум 8 МБ для video note.")
            return
        
        # Проверяем, что видео квадратное через ffprobe
        ffprobe_path = shutil.which('ffprobe')
        if ffprobe_path:
            try:
                probe_cmd = [
                    ffprobe_path,
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height',
                    '-of', 'json',
                    video_path
                ]
                result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
                import json
                probe_data = json.loads(result.stdout)
                if 'streams' in probe_data and len(probe_data['streams']) > 0:
                    width = probe_data['streams'][0].get('width')
                    height = probe_data['streams'][0].get('height')
                    if width != height:
                        logger.warning(f"Видео не квадратное: {width}x{height}")
            except Exception as e:
                logger.warning(f"Не удалось проверить видео через ffprobe: {e}")
        
        # Отправляем круглое видеосообщение (video note)
        # Используем ТОЛЬКО прямой вызов Telegram Bot API через requests
        # Это единственный способ гарантировать отправку как video note
        import requests
        from io import BytesIO
        
        chat_id = message.chat_id
        video_size = 640  # Размер квадратного видео (640x640 - стандарт для video note)
        
        # Получаем реальную длительность из аудио
        duration = get_audio_duration(audio_path)
        video_duration = int(duration) if duration else 60
        
        # Прямой вызов API метода sendVideoNote
        api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideoNote"
        
        # Читаем файл в память
        with open(video_path, 'rb') as f:
            video_bytes = f.read()
        
        # Создаем BytesIO объект для передачи
        video_file_obj = BytesIO(video_bytes)
        video_file_obj.name = 'video.mp4'
        
        # Передаем файл через multipart/form-data
        # КРИТИЧЕСКИ ВАЖНО: параметр должен называться именно 'video_note'
        # Используем правильный формат для передачи файла
        files = {
            'video_note': ('video.mp4', video_file_obj, 'video/mp4')
        }
        # Параметры передаем как строки (как требует Telegram API)
        # length и duration обязательны для video note
        data = {
            'chat_id': str(chat_id),
            'duration': str(video_duration),
            'length': str(video_size)
        }
        
        # Важно: перемещаем указатель в начало файла
        video_file_obj.seek(0)
        
        logger.info(f"Отправка video note через прямой API: chat_id={chat_id}, duration={video_duration}, length={video_size}, размер: {len(video_bytes)/1024/1024:.2f} МБ")
        
        # Отправляем запрос
        response = requests.post(api_url, files=files, data=data, timeout=300)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Ответ API (первые 500 символов): {str(result)[:500]}")
            if result.get('ok'):
                message_result = result.get('result', {})
                # Проверяем, что это действительно video note
                if 'video_note' in message_result:
                    logger.info(f"✅ Video note отправлен! Message ID: {message_result.get('message_id', 'OK')}")
                elif 'video' in message_result:
                    logger.warning(f"⚠️ Telegram API вернул 'video' вместо 'video_note'")
                    logger.warning("⚠️ Это может означать, что видео не соответствует требованиям для video note")
                    logger.warning("⚠️ Но сообщение отправлено, возможно отобразится как video note в клиенте")
                else:
                    logger.info(f"Тип сообщения в ответе: {list(message_result.keys())}")
            else:
                error_desc = result.get('description', 'Unknown error')
                logger.error(f"Ошибка API: {error_desc}, полный ответ: {result}")
                raise Exception(f"API ошибка: {error_desc}")
        else:
            logger.error(f"HTTP ошибка: {response.status_code}, ответ: {response.text}")
            raise Exception(f"HTTP ошибка: {response.status_code}: {response.text}")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке: {e}", exc_info=True)
        await message.reply_text(f"❌ Произошла ошибка: {str(e)}")
    
    finally:
        # Очищаем временные файлы
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error(f"Ошибка при удалении временной директории: {e}")


def main():
    """Запуск бота."""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    # Обрабатываем аудио файлы и документы
    application.add_handler(MessageHandler(
        filters.AUDIO | filters.Document.ALL, 
        handle_audio
    ))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

