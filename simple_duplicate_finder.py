import os
import hashlib
import sys
import shutil

# --- Функции для вывода в терминал ---
def terminal_output(message, end='\n'):
    """Выводит сообщение в терминал сразу"""
    sys.stdout.write(message + end)
    sys.stdout.flush()


def calculate_file_hash(filepath, hash_algorithm=hashlib.sha256, chunk_size=4096, first_chunk_only=False):
    """Вычисляет хеш файла. Если first_chunk_only=True, хеширует только первые 4КБ"""
    hasher = hash_algorithm()
    try:
        with open(filepath, 'rb') as f:
            if first_chunk_only:
                chunk = f.read(4096)
                hasher.update(chunk)
            else:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, OSError):
        return None


def find_duplicate_files_logic(paths):
    """
    Оптимизированная логика поиска дубликатов:
    1. Группировка по размеру.
    2. Быстрый хеш первых 4КБ.
    3. Полный хеш только для подозрительных файлов.
    """
    size_dict = {}
    terminal_output("Начинаем сканирование файлов...")

    total_files_scanned = 0
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
                if os.path.islink(full_path):
                    continue
                try:
                    size = os.path.getsize(full_path)
                    if size == 0:
                        continue
                except OSError:
                    terminal_output(f"Ошибка: не удалось получить размер файла {full_path}. Пропускаем.")
                    continue

                size_dict.setdefault(size, []).append(full_path)
                total_files_scanned += 1

    terminal_output(f"\nСканирование завершено. Всего файлов: {total_files_scanned}")

    # Быстрый хеш первых 4КБ для файлов одинакового размера
    fast_hash_dict = {}
    for size, files in size_dict.items():
        if len(files) < 2:
            continue
        for f in files:
            fhash = calculate_file_hash(f, first_chunk_only=True)
            if fhash:
                fast_hash_dict.setdefault(fhash, []).append(f)

    # Полный хеш только для подозрительных файлов
    full_hash_dict = {}
    for fhash, files in fast_hash_dict.items():
        if len(files) < 2:
            continue
        for f in files:
            full_hash = calculate_file_hash(f, first_chunk_only=False)
            if full_hash:
                full_hash_dict.setdefault(full_hash, []).append(f)

    return full_hash_dict


def print_duplicates_and_prompt_delete(file_hashes):
    """Выводит дубликаты и спрашивает пользователя, хочет ли он удалить лишние файлы"""
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

            # Спрашиваем пользователя, хочет ли удалить дубликаты (оставляем первый файл)
            while True:
                choice = input("\nУдалить лишние копии этих файлов? (y/n): ").strip().lower()
                if choice == 'y':
                    for f in files[1:]:
                        try:
                            os.remove(f)
                            terminal_output(f"Удалён файл: {f}")
                        except OSError as e:
                            terminal_output(f"Ошибка при удалении {f}: {e}")
                    break
                elif choice == 'n':
                    break
                else:
                    terminal_output("Введите y или n.")

    if not found:
        terminal_output("Дубликатов не найдено.")
    else:
        terminal_output(f"\nНайдено {groups} групп дубликатов.")

    terminal_output("\nСканирование завершено.")


if __name__ == "__main__":
    paths_to_scan = sys.argv[1:] if len(sys.argv) > 1 else ["."]
    duplicates = find_duplicate_files_logic(paths_to_scan)
    print_duplicates_and_prompt_delete(duplicates)

