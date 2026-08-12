#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для создания видео с вращающейся обложкой альбома.
Объединяет обложку с аудио отрезком и добавляет эффект вращения.
"""

import os
import subprocess
import shutil
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


def create_rotating_video(cover_path, audio_path, output_path=None, rotation_speed=1.0):
    """
    Создает видео с вращающейся обложкой и аудио.
    
    Args:
        cover_path: Путь к изображению обложки
        audio_path: Путь к аудио файлу
        output_path: Путь для сохранения видео
        rotation_speed: Скорость вращения (оборотов в секунду, по умолчанию 1.0)
        
    Returns:
        True если успешно, False в противном случае
    """
    # Проверяем наличие ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        print("Ошибка: ffmpeg не найден в системе.")
        print("Установите ffmpeg: https://ffmpeg.org/download.html")
        return False
    
    # Проверяем существование файлов
    if not os.path.exists(cover_path):
        print(f"Ошибка: Файл обложки {cover_path} не найден.")
        return False
    
    if not os.path.exists(audio_path):
        print(f"Ошибка: Файл аудио {audio_path} не найден.")
        return False
    
    # Получаем длительность аудио
    print(f"Определение длительности аудио {audio_path}...")
    duration = get_audio_duration(audio_path)
    
    if duration is None:
        print("Ошибка: Не удалось определить длительность аудио.")
        return False
    
    print(f"Длительность аудио: {duration:.2f} секунд")
    
    # Определяем путь для сохранения
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        # Убираем _sample_60s из имени, если есть
        base_name = base_name.replace('_sample_60s', '')
        output_path = f"{base_name}_video.mp4"
    
    print(f"Создание видео с вращающейся обложкой...")
    print(f"Скорость вращения: {rotation_speed} оборотов в секунду")
    
    # Вычисляем угол поворота в градусах за секунду
    # 360 градусов * скорость вращения
    rotation_per_second = 360 * rotation_speed
    
    # Создаем команду ffmpeg для создания видео с вращением
    # Используем фильтр rotate с выражением для непрерывного вращения
    try:
        # Формула для вращения: 2*PI*t*speed (в радианах), где t - время
        # В ffmpeg используем выражение: 2*PI*t*{speed} для угла в радианах
        # Или можно использовать градусы: 360*t*{speed}
        
        # Команда ffmpeg:
        # -loop 1: зацикливаем изображение
        # -i cover: входное изображение
        # -i audio: входное аудио
        # -vf "rotate=2*PI*t*{speed}": фильтр вращения (угол в радианах)
        # -c:v libx264: кодек видео
        # -c:a aac: кодек аудио
        # -pix_fmt yuv420p: формат пикселей для совместимости
        # -shortest: закончить когда закончится самое короткое (аудио)
        
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
        
        print("Выполнение ffmpeg...")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        print(f"Готово! Видео сохранено в {output_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении ffmpeg: {e}")
        if e.stderr:
            print(f"Детали ошибки: {e.stderr}")
        return False
    except Exception as e:
        print(f"Ошибка: {e}")
        return False


def main():
    """Основная функция."""
    # Ищем файлы обложки и аудио
    cover_files = [f for f in os.listdir('.') if f.endswith('_cover.png')]
    audio_files = [f for f in os.listdir('.') if f.endswith('_sample_60s.mp3')]
    
    if not cover_files:
        print("Ошибка: Файлы обложки (*_cover.png) не найдены в текущей директории.")
        print("Сначала запустите create_cover.py для создания обложки.")
        return
    
    if not audio_files:
        print("Ошибка: Файлы аудио отрезков (*_sample_60s.mp3) не найдены в текущей директории.")
        print("Сначала запустите extract_sample.py для создания аудио отрезка.")
        return
    
    # Используем первый найденный файл каждого типа
    cover_path = cover_files[0]
    audio_path = audio_files[0]
    
    print(f"Обложка: {cover_path}")
    print(f"Аудио: {audio_path}")
    
    # Создаем видео с вращением (1/3 оборота в секунду - в 3 раза медленнее)
    create_rotating_video(cover_path, audio_path, rotation_speed=1.0/3)


if __name__ == '__main__':
    main()

