#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для создания обложки альбома с пластинкой.
Извлекает обложку из MP3 файла и накладывает заготовку пластинки.
"""

import os
import sys
import io
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
    """
    # Извлекаем обложку из MP3
    print(f"Извлечение обложки из {mp3_path}...")
    album_cover = extract_cover_from_mp3(mp3_path)
    
    if album_cover is None:
        print("Ошибка: Не удалось извлечь обложку из MP3 файла.")
        return False
    
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
    print(f"Готово! Обложка сохранена в {output_path}")
    
    return True


def main():
    """Основная функция."""
    # Ищем MP3 файлы в текущей директории
    mp3_files = [f for f in os.listdir('.') if f.lower().endswith('.mp3')]
    
    if not mp3_files:
        print("Ошибка: MP3 файлы не найдены в текущей директории.")
        return
    
    # Используем первый найденный MP3 файл
    mp3_path = mp3_files[0]
    base_template = 'base.png'
    
    if not os.path.exists(base_template):
        print(f"Ошибка: Файл {base_template} не найден.")
        return
    
    print(f"Обработка файла: {mp3_path}")
    create_album_cover(mp3_path, base_template)


if __name__ == '__main__':
    main()

