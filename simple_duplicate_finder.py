import os
import hashlib
import sys

# --- Функции для вывода в терминал ---
def terminal_output(message, end='\n'):
    """Выводит сообщение в терминал."""
    sys.stdout.write(message + end)
    sys.stdout.flush()


def calculate_file_hash(filepath, hash_algorithm=hashlib.sha256, chunk_size=4096):
    """Вычисляет хеш указанного файла."""
    hasher = hash_algorithm()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, OSError):
        return None


def find_duplicate_files_logic(paths):
    """
    Основная логика поиска дубликатов.
    Весь вывод идёт через terminal_output.
    """
    hashes = {}
    total_files_scanned = 0
    
    terminal_output("Начинаем сканирование файлов...")

    for path in paths:
        if not os.path.exists(path):
            terminal_output(f"Предупреждение: Путь '{path}' не существует. Пропускаем.")
            continue
        if not os.path.isdir(path):
            terminal_output(f"Предупреждение: Путь '{path}' не является директорией. Пропускаем.")
            continue

        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)

                if "@eaDir" in full_path or "@SynoEAStream" in full_path:
                    continue

                total_files_scanned += 1

                if os.path.islink(full_path):
                    continue

                try:
                    if os.path.getsize(full_path) == 0:
                        continue
                except OSError:
                    terminal_output(f"Ошибка: Не удалось получить размер файла {full_path}. Пропускаем.")
                    continue

                file_hash = calculate_file_hash(full_path)

                if file_hash:
                    hashes.setdefault(file_hash, []).append(full_path)

    terminal_output(f"\nЗавершено сканирование {total_files_scanned} файлов.")
    return hashes


def print_duplicates(file_hashes):
    """
    Выводит найденные дубликаты через terminal_output.
    """
    terminal_output("\n--- Найденные дубликаты ---")

    found = False
    groups = 0

    for h, files in file_hashes.items():
        if len(files) > 1:
            found = True
            groups += 1
            terminal_output(f"\nДубликаты по хешу {h}:")
            for f in files:
                terminal_output(f"  - {f}")

    if not found:
        terminal_output("Дубликатов не найдено.")
    else:
        terminal_output(f"\nНайдено {groups} групп дубликатов.")

    terminal_output("\nСканирование завершено.")
