#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной скрипт для обработки альбома.
Выполняет все этапы: создание обложки, вырезание аудио отрезка и создание видео.
"""

import os
import sys
import io
import random
import subprocess
import shutil
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError


def extract_cover_from_mp3(mp3_path):
    """
    Извлекает обложку альбома из MP3 файла.
    
    Args:
        mp3_path: Путь к MP3 файлу
        
    Returns:
        PIL.Image или None, если обложка не найдена
    """
    try:
        from mutagen.id3 import ID3, APIC
        
        # Пытаемся открыть ID3 теги
        try:
            tags = ID3(mp3_path)
        except ID3NoHeaderError:
            print("MP3 файл не содержит ID3 тегов.")
            return None
        
        # Ищем обложку в тегах APIC
        for key in tags.keys():
            if key.startswith('APIC'):
                apic = tags[key]
                if hasattr(apic, 'data') and apic.data:
                    try:
                        cover_image = Image.open(io.BytesIO(apic.data))
                        return cover_image
                    except Exception as e:
                        print(f"Ошибка при обработке изображения: {e}")
                        continue
        
        # Альтернативный способ через MP3
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
                            print(f"Ошибка при обработке изображения: {e}")
                            continue
        except Exception as e:
            print(f"Ошибка при чтении MP3: {e}")
            
    except Exception as e:
        print(f"Ошибка при извлечении обложки: {e}")
    
    return None


def create_album_cover(mp3_path, base_template_path, output_path=None):
    """
    Создает обложку альбома, накладывая заготовку пластинки на обложку из MP3.
    
    Args:
        mp3_path: Путь к MP3 файлу
        base_template_path: Путь к заготовке пластинки (base.png)
        output_path: Путь для сохранения результата (по умолчанию cover.png)
        
    Returns:
        Путь к созданной обложке или None при ошибке
    """
    # Извлекаем обложку из MP3
    print(f"\n=== Этап 1: Создание обложки ===")
    print(f"Извлечение обложки из {mp3_path}...")
    album_cover = extract_cover_from_mp3(mp3_path)
    
    if album_cover is None:
        print("Ошибка: Не удалось извлечь обложку из MP3 файла.")
        return None
    
    # Уменьшаем обложку до 300x300
    print("Уменьшение обложки до 300x300...")
    album_cover = album_cover.resize((300, 300), Image.Resampling.LANCZOS)
    
    # Создаем холст 800x800
    print("Создание холста 800x800...")
    canvas = Image.new('RGBA', (800, 800), (255, 255, 255, 0))
    
    # Размещаем обложку по центру (задний план)
    x_offset = (800 - 300) // 2
    y_offset = (800 - 300) // 2
    canvas.paste(album_cover, (x_offset, y_offset))
    
    # Загружаем заготовку пластинки
    print(f"Загрузка заготовки {base_template_path}...")
    vinyl_template = Image.open(base_template_path).convert('RGBA')
    
    # Убеждаемся, что заготовка имеет размер 800x800
    if vinyl_template.size != (800, 800):
        print(f"Изменение размера заготовки с {vinyl_template.size} до 800x800...")
        vinyl_template = vinyl_template.resize((800, 800), Image.Resampling.LANCZOS)
    
    # Накладываем заготовку на передний план
    print("Наложение заготовки пластинки...")
    canvas = Image.alpha_composite(canvas, vinyl_template)
    
    # Определяем путь для сохранения
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(mp3_path))[0]
        output_path = f"{base_name}_cover.png"
    
    # Сохраняем результат
    print(f"Сохранение результата в {output_path}...")
    canvas.save(output_path, 'PNG')
    print(f"✓ Обложка сохранена в {output_path}")
    
    return output_path


def get_audio_duration(mp3_path):
    """
    Получает длительность аудио файла в секундах.
    
    Args:
        mp3_path: Путь к MP3 файлу
        
    Returns:
        Длительность в секундах (float)
    """
    try:
        audio = MP3(mp3_path)
        return audio.info.length
    except Exception as e:
        print(f"Ошибка при получении длительности: {e}")
        return None


def extract_random_segment(mp3_path, segment_length=60, output_path=None):
    """
    Вырезает случайный отрезок заданной длительности из MP3 файла.
    
    Args:
        mp3_path: Путь к MP3 файлу
        segment_length: Длина отрезка в секундах (по умолчанию 60)
        output_path: Путь для сохранения результата
        
    Returns:
        Путь к созданному аудио файлу или None при ошибке
    """
    print(f"\n=== Этап 2: Вырезание аудио отрезка ===")
    
    # Проверяем наличие ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        print("Ошибка: ffmpeg не найден в системе.")
        print("Установите ffmpeg: https://ffmpeg.org/download.html")
        return None
    
    # Получаем длительность трека
    print(f"Определение длительности трека {mp3_path}...")
    duration = get_audio_duration(mp3_path)
    
    if duration is None:
        print("Ошибка: Не удалось определить длительность трека.")
        return None
    
    print(f"Длительность трека: {duration:.2f} секунд")
    
    # Проверяем, что трек достаточно длинный
    if duration < segment_length:
        print(f"Ошибка: Трек слишком короткий ({duration:.2f} сек). Требуется минимум {segment_length} секунд.")
        return None
    
    # Выбираем случайную начальную точку
    max_start = duration - segment_length
    start_time = random.uniform(0, max_start)
    
    print(f"Вырезание отрезка с {start_time:.2f} по {start_time + segment_length:.2f} секунд...")
    
    # Определяем путь для сохранения
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(mp3_path))[0]
        output_path = f"{base_name}_sample_60s.mp3"
    
    # Используем ffmpeg для вырезания отрезка
    print(f"Сохранение отрезка в {output_path}...")
    try:
        subprocess.run(
            [
                ffmpeg_path,
                '-i', mp3_path,
                '-ss', str(start_time),
                '-t', str(segment_length),
                '-acodec', 'copy',  # Копируем без перекодирования для скорости
                '-y',  # Перезаписывать файл, если существует
                output_path
            ],
            check=True,
            capture_output=True
        )
        print(f"✓ Отрезок сохранен в {output_path}")
        print(f"  Отрезок: {start_time:.2f} - {start_time + segment_length:.2f} секунд")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении ffmpeg: {e}")
        if e.stderr:
            print(f"Детали ошибки: {e.stderr.decode('utf-8', errors='ignore')}")
        return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None


def create_rotating_video(cover_path, audio_path, output_path=None, rotation_speed=1.0/3):
    """
    Создает видео с вращающейся обложкой и аудио.
    
    Args:
        cover_path: Путь к изображению обложки
        audio_path: Путь к аудио файлу
        output_path: Путь для сохранения видео
        rotation_speed: Скорость вращения (оборотов в секунду, по умолчанию 1/3)
        
    Returns:
        Путь к созданному видео файлу или None при ошибке
    """
    print(f"\n=== Этап 3: Создание видео ===")
    
    # Проверяем наличие ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        print("Ошибка: ffmpeg не найден в системе.")
        print("Установите ffmpeg: https://ffmpeg.org/download.html")
        return None
    
    # Проверяем существование файлов
    if not os.path.exists(cover_path):
        print(f"Ошибка: Файл обложки {cover_path} не найден.")
        return None
    
    if not os.path.exists(audio_path):
        print(f"Ошибка: Файл аудио {audio_path} не найден.")
        return None
    
    # Получаем длительность аудио
    print(f"Определение длительности аудио {audio_path}...")
    duration = get_audio_duration(audio_path)
    
    if duration is None:
        print("Ошибка: Не удалось определить длительность аудио.")
        return None
    
    print(f"Длительность аудио: {duration:.2f} секунд")
    
    # Определяем путь для сохранения
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        # Убираем _sample_60s из имени, если есть
        base_name = base_name.replace('_sample_60s', '')
        output_path = f"{base_name}_video.mp4"
    
    print(f"Создание видео с вращающейся обложкой...")
    print(f"Скорость вращения: {rotation_speed:.3f} оборотов в секунду")
    
    # Формула вращения: 2*PI*t*speed (в радианах)
    # где t - время в секундах, speed - оборотов в секунду
    rotate_filter = f'rotate=2*PI*t*{rotation_speed}'
    
    cmd = [
        ffmpeg_path,
        '-loop', '1',
        '-i', cover_path,
        '-i', audio_path,
        '-vf', rotate_filter,
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-pix_fmt', 'yuv420p',
        '-shortest',
        '-y',  # Перезаписывать файл, если существует
        output_path
    ]
    
    try:
        print("Выполнение ffmpeg...")
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        print(f"✓ Видео сохранено в {output_path}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении ffmpeg: {e}")
        if e.stderr:
            print(f"Детали ошибки: {e.stderr}")
        return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None


def main():
    """Основная функция - выполняет все этапы обработки."""
    print("=" * 60)
    print("Обработка альбома: создание видео с вращающейся обложкой")
    print("=" * 60)
    
    # Ищем MP3 файлы в текущей директории
    mp3_files = [f for f in os.listdir('.') if f.lower().endswith('.mp3')]
    
    # Исключаем файлы, которые уже являются сэмплами
    mp3_files = [f for f in mp3_files if '_sample_' not in f]
    
    if not mp3_files:
        print("Ошибка: MP3 файлы не найдены в текущей директории.")
        return
    
    # Используем первый найденный MP3 файл
    mp3_path = mp3_files[0]
    base_template = 'base.png'
    
    if not os.path.exists(base_template):
        print(f"Ошибка: Файл {base_template} не найден.")
        return
    
    print(f"\nОбработка файла: {mp3_path}\n")
    
    # Этап 1: Создание обложки
    cover_path = create_album_cover(mp3_path, base_template)
    if cover_path is None:
        print("\nОшибка: Не удалось создать обложку. Прерывание.")
        return
    
    # Этап 2: Вырезание аудио отрезка
    audio_path = extract_random_segment(mp3_path, segment_length=60)
    if audio_path is None:
        print("\nОшибка: Не удалось вырезать аудио отрезок. Прерывание.")
        return
    
    # Этап 3: Создание видео
    video_path = create_rotating_video(cover_path, audio_path, rotation_speed=1.0/3)
    if video_path is None:
        print("\nОшибка: Не удалось создать видео. Прерывание.")
        return
    
    # Итоги
    print("\n" + "=" * 60)
    print("Обработка завершена успешно!")
    print("=" * 60)
    print(f"Обложка: {cover_path}")
    print(f"Аудио отрезок: {audio_path}")
    print(f"Видео: {video_path}")
    print("=" * 60)


if __name__ == '__main__':
    main()

