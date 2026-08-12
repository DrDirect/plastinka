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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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


def create_album_cover(mp3_path, base_template_path, output_path, style='vinyl'):
    """
    Создает обложку альбома.
    
    Args:
        mp3_path: Путь к MP3 файлу
        base_template_path: Путь к шаблону base.png (используется только для стиля 'vinyl')
        output_path: Путь для сохранения обложки
        style: Стиль обложки ('vinyl' - с пластинкой, 'original' - оригинальная обложка)
    """
    album_cover = extract_cover_from_mp3(mp3_path)
    
    if album_cover is None:
        return False
    
    if style == 'original':
        # Стиль 2: просто оригинальная обложка без изменений
        # Масштабируем до 800x800 для видео
        album_cover = album_cover.resize((800, 800), Image.Resampling.LANCZOS)
        album_cover.save(output_path, 'PNG')
        return True
    else:
        # Стиль 1 (vinyl): обложка с пластинкой (текущий стиль)
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


def extract_random_segment(mp3_path, segment_length=60, output_path=None, start_time=None):
    """
    Вырезает отрезок из MP3 файла.
    
    Args:
        mp3_path: Путь к MP3 файлу
        segment_length: Длина отрезка в секундах
        output_path: Путь для сохранения
        start_time: Время начала отрезка в секундах (если None, выбирается случайно)
    """
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
    
    # Если указано время начала, используем его, иначе выбираем случайно
    if start_time is not None:
        # Проверяем, что время начала не выходит за границы
        if start_time < 0:
            start_time = 0
        if start_time + segment_length > duration:
            start_time = max(0, duration - segment_length)
    else:
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
        '-r', '60',  # Частота кадров 60 fps
        '-g', '60',  # GOP size (1 секунда при 60 fps)
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


def get_main_menu_keyboard():
    """Создает главное меню с кнопками выбора параметров."""
    keyboard = [
        [InlineKeyboardButton("⏱️ Длительность", callback_data="menu_duration")],
        [InlineKeyboardButton("🌀 Скорость вращения", callback_data="menu_rotation")],
        [InlineKeyboardButton("🎨 Стиль обложки", callback_data="menu_style")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопку выбора длительности."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем длительность из callback_data
    duration = int(query.data.split('_')[1])
    
    # Сохраняем выбранную длительность
    context.user_data['selected_duration'] = duration
    
    # Показываем главное меню снова
    await query.edit_message_text(
        f"✅ Выбрана длительность: {duration} секунд\n\n"
        f"Выбери следующий параметр:",
        reply_markup=get_main_menu_keyboard()
    )


async def handle_rotation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопку выбора скорости вращения."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем скорость из callback_data
    # Формат: rotation_33, rotation_45, rotation_slow, rotation_fast
    rotation_data = query.data.split('_')[1]
    
    # Скорости вращения (обороты в секунду)
    # 33⅓ об/мин (LP) = 33.333/60 = 0.556 - эталонная скорость грампластинки
    # 45 об/мин (сингл) = 45/60 = 0.75
    rotation_speeds = {
        '33': 33.333/60,  # 33⅓ об/мин - эталонная скорость LP
        '45': 45/60,      # 45 об/мин - скорость сингла
        'slow': 20/60,    # 20 об/мин - медленнее
        'fast': 60/60,   # 60 об/мин - быстрее
    }
    
    speed_labels = {
        '33': '33⅓ об/мин (LP)',
        '45': '45 об/мин (сингл)',
        'slow': '20 об/мин (медленно)',
        'fast': '60 об/мин (быстро)',
    }
    
    rotation_speed = rotation_speeds.get(rotation_data, 33.333/60)
    speed_label = speed_labels.get(rotation_data, '33⅓ об/мин (LP)')
    
    # Сохраняем выбранную скорость
    context.user_data['selected_rotation'] = rotation_speed
    
    # Показываем главное меню снова
    await query.edit_message_text(
        f"✅ Выбрана скорость вращения: {speed_label}\n\n"
        f"Выбери следующий параметр:",
        reply_markup=get_main_menu_keyboard()
    )


async def handle_style_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопку выбора стиля обложки."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем стиль из callback_data
    # Формат: style_vinyl, style_original
    style_data = query.data.split('_')[1]
    
    style_labels = {
        'vinyl': 'С пластинкой',
        'original': 'Оригинальная обложка',
    }
    
    # Сохраняем выбранный стиль
    context.user_data['selected_style'] = style_data
    
    style_label = style_labels.get(style_data, 'С пластинкой')
    
    # Показываем главное меню снова
    await query.edit_message_text(
        f"✅ Выбран стиль: {style_label}\n\n"
        f"Выбери следующий параметр:",
        reply_markup=get_main_menu_keyboard()
    )


async def handle_recreate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопку 'Пересоздать'."""
    query = update.callback_query
    await query.answer()
    
    # Увеличиваем счетчик нажатий
    recreate_count = context.user_data.get('recreate_count', 0) + 1
    context.user_data['recreate_count'] = recreate_count
    
    # Если нажато больше 3 раз, запрашиваем время начала отрезка
    if recreate_count > 3:
        await query.edit_message_text(
            "Бля, ты заебал, делай сам!\n\n"
            "Укажи время в секундах, с которого нужно начать отрезок (например: 30 или 120.5):"
        )
        # Устанавливаем флаг ожидания времени
        context.user_data['waiting_for_start_time'] = True
        return
    
    # Проверяем, есть ли сохраненный файл
    file_id = context.user_data.get('last_mp3_file_id')
    if not file_id:
        await query.answer("❌ Ошибка: не найден предыдущий MP3 файл.")
        await query.edit_message_text("❌ Ошибка: не найден предыдущий MP3 файл. Отправьте файл заново.")
        return
    
    await query.answer("🔄 Пересоздаю видео...")
    
    # Удаляем все предыдущие сообщения бота
    chat_id = query.message.chat_id
    await delete_bot_messages(context, chat_id)
    
    # Используем сохраненное время начала, если есть
    custom_start_time = context.user_data.get('custom_start_time')
    
    # Получаем файл по file_id
    try:
        file_obj = await context.bot.get_file(file_id)
        file_name = context.user_data.get('last_mp3_file_name', 'audio.mp3')
        
        # Создаем временную директорию для работы
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Скачиваем файл
            mp3_path = os.path.join(temp_dir, file_name)
            downloaded_path = await file_obj.download_to_drive()
            if downloaded_path and os.path.exists(str(downloaded_path)):
                if str(downloaded_path) != mp3_path:
                    shutil.move(str(downloaded_path), mp3_path)
            elif os.path.exists(file_name):
                shutil.move(file_name, mp3_path)
            
            # Проверяем наличие base.png
            base_template = 'base.png'
            if not os.path.exists(base_template):
                await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка: файл base.png не найден.")
                return
            
            # Этап 1: Создание обложки
            selected_style = context.user_data.get('selected_style', 'vinyl')
            cover_path = os.path.join(temp_dir, "cover.png")
            if not create_album_cover(mp3_path, base_template, cover_path, style=selected_style):
                await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка: не удалось создать обложку. Убедитесь, что в MP3 есть обложка.")
                return
            
            # Этап 2: Вырезание аудио отрезка
            selected_duration = context.user_data.get('selected_duration', 60)
            audio_path = os.path.join(temp_dir, "sample.mp3")
            if not extract_random_segment(mp3_path, segment_length=selected_duration, output_path=audio_path, start_time=custom_start_time):
                await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка: не удалось вырезать аудио отрезок.")
                return
            
            # Очищаем сохраненное время после использования
            if 'custom_start_time' in context.user_data:
                del context.user_data['custom_start_time']
            
            # Этап 3: Создание видео
            selected_rotation = context.user_data.get('selected_rotation', 33.333/60)
            video_path = os.path.join(temp_dir, "video.mp4")
            if not create_rotating_video(cover_path, audio_path, video_path, rotation_speed=selected_rotation, size=640):
                await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка: не удалось создать видео.")
                return
            
            # Проверяем размер файла
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            if file_size > 8:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка: размер видео слишком большой ({file_size:.2f} МБ). Максимум 8 МБ для video note.")
                return
            
            # Отправляем video note
            import requests
            from io import BytesIO
            
            video_size = 640
            duration = get_audio_duration(audio_path)
            video_duration = int(duration) if duration else 60
            
            api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideoNote"
            
            with open(video_path, 'rb') as f:
                video_bytes = f.read()
            
            video_file_obj = BytesIO(video_bytes)
            video_file_obj.name = 'video.mp4'
            
            files = {
                'video_note': ('video.mp4', video_file_obj, 'video/mp4')
            }
            data = {
                'chat_id': str(chat_id),
                'duration': str(video_duration),
                'length': str(video_size)
            }
            
            video_file_obj.seek(0)
            
            response = requests.post(api_url, files=files, data=data, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    message_result = result.get('result', {})
                    if 'video_note' in message_result:
                        # Сохраняем message_id
                        if 'bot_messages' not in context.user_data:
                            context.user_data['bot_messages'] = []
                        context.user_data['bot_messages'].append(message_result.get('message_id'))
                        
                        # Отправляем сообщение с кнопкой "Пересоздать"
                        keyboard = [[InlineKeyboardButton("🔄 Пересоздать", callback_data="recreate_video")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        recreate_msg = await context.bot.send_message(
                            chat_id=chat_id,
                            text="✅ Видео пересоздано и отправлено!\n\n"
                                 "Если не устраивает результат, нажми 'Пересоздать' для создания нового видео с теми же параметрами.",
                            reply_markup=reply_markup
                        )
                        context.user_data['bot_messages'].append(recreate_msg.message_id)
                    else:
                        await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при отправке видео.")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка API: {result.get('description', 'Unknown error')}")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ HTTP ошибка: {response.status_code}")
        
        finally:
            # Очищаем временные файлы
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Ошибка при удалении временной директории: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при пересоздании: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Произошла ошибка: {str(e)}")


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопки главного меню."""
    query = update.callback_query
    await query.answer()
    
    menu_type = query.data.split('_')[1]
    
    if menu_type == 'duration':
        # Меню выбора длительности
        keyboard = [
            [InlineKeyboardButton("15 сек", callback_data="duration_15")],
            [InlineKeyboardButton("30 сек", callback_data="duration_30")],
            [InlineKeyboardButton("60 сек", callback_data="duration_60")],
            [InlineKeyboardButton("◀️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⏱️ Выбери длительность видео:",
            reply_markup=reply_markup
        )
    elif menu_type == 'rotation':
        # Меню выбора скорости вращения
        keyboard = [
            [InlineKeyboardButton("33⅓ об/мин (LP)", callback_data="rotation_33")],
            [InlineKeyboardButton("45 об/мин (сингл)", callback_data="rotation_45")],
            [InlineKeyboardButton("20 об/мин (медленно)", callback_data="rotation_slow")],
            [InlineKeyboardButton("60 об/мин (быстро)", callback_data="rotation_fast")],
            [InlineKeyboardButton("◀️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🌀 Выбери скорость вращения:",
            reply_markup=reply_markup
        )
    elif menu_type == 'style':
        # Меню выбора стиля
        keyboard = [
            [InlineKeyboardButton("🎵 С пластинкой", callback_data="style_vinyl")],
            [InlineKeyboardButton("🖼️ Оригинальная", callback_data="style_original")],
            [InlineKeyboardButton("◀️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🎨 Выбери стиль обложки:",
            reply_markup=reply_markup
        )
    elif menu_type == 'main':
        # Возврат в главное меню
        await query.edit_message_text(
            "Привет! Отправь мне MP3 файл, и я создам для него:\n"
            "🎵 Обложку (с пластинкой или оригинальную)\n"
            "🎶 Аудио отрезок выбранной длительности\n"
            "🎬 Видео с вращающейся обложкой\n\n"
            "Выбери параметры:",
            reply_markup=get_main_menu_keyboard()
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text(
        "Привет! Отправь мне MP3 файл, и я создам для него:\n"
        "🎵 Обложку (с пластинкой или оригинальную)\n"
        "🎶 Аудио отрезок выбранной длительности\n"
        "🎬 Видео с вращающейся обложкой\n\n"
        "Выбери параметры:",
        reply_markup=get_main_menu_keyboard()
    )


async def delete_bot_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Удаляет все предыдущие сообщения бота из user_data."""
    bot_messages = context.user_data.get('bot_messages', [])
    for msg_id in bot_messages:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
    # Очищаем список
    context.user_data['bot_messages'] = []


async def handle_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод времени начала отрезка."""
    message = update.message
    
    # Проверяем, ожидаем ли мы время начала
    if not context.user_data.get('waiting_for_start_time', False):
        return
    
    try:
        # Парсим время
        start_time = float(message.text.strip())
        
        if start_time < 0:
            await message.reply_text("❌ Время не может быть отрицательным. Попробуй еще раз:")
            return
        
        # Сохраняем время начала
        context.user_data['custom_start_time'] = start_time
        context.user_data['waiting_for_start_time'] = False
        
        # Сбрасываем счетчик пересозданий
        context.user_data['recreate_count'] = 0
        
        # Запускаем пересоздание
        file_id = context.user_data.get('last_mp3_file_id')
        if not file_id:
            await message.reply_text("❌ Ошибка: не найден предыдущий MP3 файл. Отправьте файл заново.")
            return
        
        # Удаляем все предыдущие сообщения бота
        chat_id = message.chat_id
        await delete_bot_messages(context, chat_id)
        
        # Получаем файл по file_id
        try:
            file_obj = await context.bot.get_file(file_id)
            file_name = context.user_data.get('last_mp3_file_name', 'audio.mp3')
            
            # Создаем временную директорию для работы
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Скачиваем файл
                mp3_path = os.path.join(temp_dir, file_name)
                downloaded_path = await file_obj.download_to_drive()
                if downloaded_path and os.path.exists(str(downloaded_path)):
                    if str(downloaded_path) != mp3_path:
                        shutil.move(str(downloaded_path), mp3_path)
                elif os.path.exists(file_name):
                    shutil.move(file_name, mp3_path)
                
                # Проверяем наличие base.png
                base_template = 'base.png'
                if not os.path.exists(base_template):
                    await message.reply_text("❌ Ошибка: файл base.png не найден.")
                    return
                
                # Этап 1: Создание обложки
                selected_style = context.user_data.get('selected_style', 'vinyl')
                cover_path = os.path.join(temp_dir, "cover.png")
                if not create_album_cover(mp3_path, base_template, cover_path, style=selected_style):
                    await message.reply_text("❌ Ошибка: не удалось создать обложку. Убедитесь, что в MP3 есть обложка.")
                    return
                
                # Этап 2: Вырезание аудио отрезка с указанного времени
                selected_duration = context.user_data.get('selected_duration', 60)
                audio_path = os.path.join(temp_dir, "sample.mp3")
                if not extract_random_segment(mp3_path, segment_length=selected_duration, output_path=audio_path, start_time=start_time):
                    await message.reply_text("❌ Ошибка: не удалось вырезать аудио отрезок.")
                    return
                
                # Этап 3: Создание видео
                selected_rotation = context.user_data.get('selected_rotation', 33.333/60)
                video_path = os.path.join(temp_dir, "video.mp4")
                if not create_rotating_video(cover_path, audio_path, video_path, rotation_speed=selected_rotation, size=640):
                    await message.reply_text("❌ Ошибка: не удалось создать видео.")
                    return
                
                # Проверяем размер файла
                file_size = os.path.getsize(video_path) / (1024 * 1024)
                if file_size > 8:
                    await message.reply_text(f"❌ Ошибка: размер видео слишком большой ({file_size:.2f} МБ). Максимум 8 МБ для video note.")
                    return
                
                # Отправляем video note
                import requests
                from io import BytesIO
                
                video_size = 640
                duration = get_audio_duration(audio_path)
                video_duration = int(duration) if duration else 60
                
                api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideoNote"
                
                with open(video_path, 'rb') as f:
                    video_bytes = f.read()
                
                video_file_obj = BytesIO(video_bytes)
                video_file_obj.name = 'video.mp4'
                
                files = {
                    'video_note': ('video.mp4', video_file_obj, 'video/mp4')
                }
                data = {
                    'chat_id': str(chat_id),
                    'duration': str(video_duration),
                    'length': str(video_size)
                }
                
                video_file_obj.seek(0)
                
                response = requests.post(api_url, files=files, data=data, timeout=300)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        message_result = result.get('result', {})
                        if 'video_note' in message_result:
                            # Сохраняем message_id
                            if 'bot_messages' not in context.user_data:
                                context.user_data['bot_messages'] = []
                            context.user_data['bot_messages'].append(message_result.get('message_id'))
                            
                            # Отправляем сообщение с кнопкой "Пересоздать"
                            keyboard = [[InlineKeyboardButton("🔄 Пересоздать", callback_data="recreate_video")]]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            recreate_msg = await message.reply_text(
                                f"✅ Видео создано с начала с {start_time} секунды!\n\n"
                                "Если не устраивает результат, нажми 'Пересоздать' для создания нового видео с теми же параметрами.",
                                reply_markup=reply_markup
                            )
                            context.user_data['bot_messages'].append(recreate_msg.message_id)
                        else:
                            await message.reply_text("❌ Ошибка при отправке видео.")
                    else:
                        await message.reply_text(f"❌ Ошибка API: {result.get('description', 'Unknown error')}")
                else:
                    await message.reply_text(f"❌ HTTP ошибка: {response.status_code}")
            
            finally:
                # Очищаем временные файлы
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.error(f"Ошибка при удалении временной директории: {e}")
        
        except Exception as e:
            logger.error(f"Ошибка при пересоздании: {e}", exc_info=True)
            await message.reply_text(f"❌ Произошла ошибка: {str(e)}")
    
    except ValueError:
        await message.reply_text("❌ Неверный формат. Укажи время в секундах (например: 30 или 120.5):")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает полученный MP3 файл."""
    message = update.message
    chat_id = message.chat_id
    
    # Проверяем, ожидаем ли мы время начала (если да, обрабатываем как время)
    if context.user_data.get('waiting_for_start_time', False):
        await handle_start_time(update, context)
        return
    
    # Удаляем все предыдущие сообщения бота перед обработкой нового трека
    await delete_bot_messages(context, chat_id)
    
    # Сбрасываем счетчик пересозданий при отправке нового файла
    context.user_data['recreate_count'] = 0
    
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
            # Показываем кнопки выбора длительности, скорости вращения и стиля
            keyboard = [
                [InlineKeyboardButton("15 сек", callback_data="duration_15"),
                 InlineKeyboardButton("30 сек", callback_data="duration_30"),
                 InlineKeyboardButton("60 сек", callback_data="duration_60")],
                [InlineKeyboardButton("33⅓ об/мин (LP)", callback_data="rotation_33"),
                 InlineKeyboardButton("45 об/мин", callback_data="rotation_45")],
                [InlineKeyboardButton("20 об/мин (медленно)", callback_data="rotation_slow"),
                 InlineKeyboardButton("60 об/мин (быстро)", callback_data="rotation_fast")],
                [InlineKeyboardButton("🎵 С пластинкой", callback_data="style_vinyl"),
                 InlineKeyboardButton("🖼️ Оригинальная", callback_data="style_original")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                "Пожалуйста, отправь MP3 файл.\n\n"
                "Или выбери длительность, скорость вращения и стиль:",
                reply_markup=reply_markup
            )
            return
    else:
        # Показываем кнопки выбора длительности, скорости вращения и стиля
        keyboard = [
            [InlineKeyboardButton("15 сек", callback_data="duration_15"),
             InlineKeyboardButton("30 сек", callback_data="duration_30"),
             InlineKeyboardButton("60 сек", callback_data="duration_60")],
            [InlineKeyboardButton("33⅓ об/мин (LP)", callback_data="rotation_33"),
             InlineKeyboardButton("45 об/мин", callback_data="rotation_45")],
            [InlineKeyboardButton("20 об/мин (медленно)", callback_data="rotation_slow"),
             InlineKeyboardButton("60 об/мин (быстро)", callback_data="rotation_fast")],
            [InlineKeyboardButton("🎵 С пластинкой", callback_data="style_vinyl"),
             InlineKeyboardButton("🖼️ Оригинальная", callback_data="style_original")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(
            "Пожалуйста, отправь MP3 файл.\n\n"
            "Или выбери длительность, скорость вращения и стиль:",
            reply_markup=reply_markup
        )
        return
    
    # Сохраняем file_id для возможности пересоздания
    context.user_data['last_mp3_file_id'] = file.file_id
    context.user_data['last_mp3_file_name'] = file_name
    
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
        # Получаем выбранный стиль из user_data, по умолчанию 'vinyl' (с пластинкой)
        selected_style = context.user_data.get('selected_style', 'vinyl')
        cover_path = os.path.join(temp_dir, "cover.png")
        if not create_album_cover(mp3_path, base_template, cover_path, style=selected_style):
            await message.reply_text("❌ Ошибка: не удалось создать обложку. Убедитесь, что в MP3 есть обложка.")
            return
        
        # Этап 2: Вырезание аудио отрезка
        # Получаем выбранную длительность из user_data, по умолчанию 60 секунд
        selected_duration = context.user_data.get('selected_duration', 60)
        audio_path = os.path.join(temp_dir, "sample.mp3")
        if not extract_random_segment(mp3_path, segment_length=selected_duration, output_path=audio_path):
            await message.reply_text("❌ Ошибка: не удалось вырезать аудио отрезок.")
            return
        
        # Этап 3: Создание видео для video note (квадратное, 640x640 - стандарт для video note)
        # Получаем выбранную скорость вращения из user_data, по умолчанию 33⅓ об/мин (эталонная скорость LP)
        selected_rotation = context.user_data.get('selected_rotation', 33.333/60)
        video_path = os.path.join(temp_dir, "video.mp4")
        # Используем размер 640x640 для video note (стандартный размер по документации Telegram)
        if not create_rotating_video(cover_path, audio_path, video_path, rotation_speed=selected_rotation, size=640):
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
                        if not create_rotating_video(cover_path, audio_path, video_path, rotation_speed=selected_rotation, size=512):
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
                    # Сохраняем message_id для последующего удаления
                    if 'bot_messages' not in context.user_data:
                        context.user_data['bot_messages'] = []
                    context.user_data['bot_messages'].append(message_result.get('message_id'))
                    
                    # Отправляем сообщение с кнопкой "Пересоздать"
                    keyboard = [[InlineKeyboardButton("🔄 Пересоздать", callback_data="recreate_video")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    recreate_msg = await message.reply_text(
                        "✅ Видео создано и отправлено!\n\n"
                        "Если не устраивает результат, нажми 'Пересоздать' для создания нового видео с теми же параметрами.",
                        reply_markup=reply_markup
                    )
                    # Сохраняем message_id для последующего удаления
                    context.user_data['bot_messages'].append(recreate_msg.message_id)
                elif 'video' in message_result:
                    logger.warning(f"⚠️ Telegram API вернул 'video' вместо 'video_note'")
                    logger.warning("⚠️ Это может означать, что видео не соответствует требованиям для video note")
                    logger.warning("⚠️ Но сообщение отправлено, возможно отобразится как video note в клиенте")
                    # Сохраняем message_id для последующего удаления
                    if 'bot_messages' not in context.user_data:
                        context.user_data['bot_messages'] = []
                    context.user_data['bot_messages'].append(message_result.get('message_id'))
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
    # Обрабатываем callback запросы от inline кнопок
    application.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(handle_duration_callback, pattern="^duration_"))
    application.add_handler(CallbackQueryHandler(handle_rotation_callback, pattern="^rotation_"))
    application.add_handler(CallbackQueryHandler(handle_style_callback, pattern="^style_"))
    application.add_handler(CallbackQueryHandler(handle_recreate_callback, pattern="^recreate_video"))
    # Обрабатываем аудио файлы и документы
    # Также обрабатываем текстовые сообщения (для ввода времени начала отрезка)
    application.add_handler(MessageHandler(
        filters.AUDIO | filters.Document.ALL, 
        handle_audio
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_audio
    ))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

