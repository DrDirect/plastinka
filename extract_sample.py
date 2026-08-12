#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для вырезания случайного 60-секундного отрезка из MP3 файла.
"""

import os
import random
from mutagen.mp3 import MP3


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
        True если успешно, False в противном случае
    """
    import subprocess
    import shutil
    
    # Проверяем наличие ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        print("Ошибка: ffmpeg не найден в системе.")
        print("Установите ffmpeg: https://ffmpeg.org/download.html")
        return False
    
    # Получаем длительность трека
    print(f"Определение длительности трека {mp3_path}...")
    duration = get_audio_duration(mp3_path)
    
    if duration is None:
        print("Ошибка: Не удалось определить длительность трека.")
        return False
    
    print(f"Длительность трека: {duration:.2f} секунд")
    
    # Проверяем, что трек достаточно длинный
    if duration < segment_length:
        print(f"Ошибка: Трек слишком короткий ({duration:.2f} сек). Требуется минимум {segment_length} секунд.")
        return False
    
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
        print(f"Готово! Отрезок сохранен в {output_path}")
        print(f"Отрезок: {start_time:.2f} - {start_time + segment_length:.2f} секунд")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении ffmpeg: {e}")
        if e.stderr:
            print(f"Детали ошибки: {e.stderr.decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"Ошибка: {e}")
        return False


def main():
    """Основная функция."""
    # Ищем MP3 файлы в текущей директории
    mp3_files = [f for f in os.listdir('.') if f.lower().endswith('.mp3')]
    
    # Исключаем файлы, которые уже являются сэмплами
    mp3_files = [f for f in mp3_files if '_sample_' not in f]
    
    if not mp3_files:
        print("Ошибка: MP3 файлы не найдены в текущей директории.")
        return
    
    # Используем первый найденный MP3 файл
    mp3_path = mp3_files[0]
    
    print(f"Обработка файла: {mp3_path}")
    extract_random_segment(mp3_path, segment_length=60)


if __name__ == '__main__':
    main()

