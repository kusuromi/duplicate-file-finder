# algorithm.py
import os
import hashlib

# ------------------ АЛГОРИТМ ПОИСКА ДУБЛИКАТОВ ------------------
def calculate_file_hash(
    filepath, hash_algorithm=hashlib.sha256, chunk_size=4096, first_chunk_only=False
):
    hasher = hash_algorithm()
    try:
        with open(filepath, "rb") as f:
            if first_chunk_only:
                chunk = f.read(4096)
                hasher.update(chunk)
            else:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError):
        return None


def find_duplicate_files_logic(paths, progress_callback=None):
    size_dict = {}
    all_files = []
    for path in paths:
        if not os.path.exists(path) or not os.path.isdir(path):
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
                    continue
                size_dict.setdefault(size, []).append(full_path)
                all_files.append(full_path)

    total_files = len(all_files)
    processed_files = 0
    fast_hash_dict = {}
    for files in size_dict.values():
        if len(files) < 2:
            processed_files += len(files)
            if progress_callback:
                progress_callback(
                    int(processed_files / total_files * 100) if total_files > 0 else 0
                )
            continue
        for f in files:
            fhash = calculate_file_hash(f, first_chunk_only=True)
            if fhash:
                fast_hash_dict.setdefault(fhash, []).append(f)
            processed_files += 1
            if progress_callback:
                progress_callback(
                    int(processed_files / total_files * 100) if total_files > 0 else 0
                )

    full_hash_dict = {}
    for files in fast_hash_dict.values():
        if len(files) < 2:
            processed_files += len(files)
            if progress_callback:
                progress_callback(
                    int(processed_files / total_files * 100) if total_files > 0 else 0
                )
            continue
        for f in files:
            full_hash = calculate_file_hash(f, first_chunk_only=False)
            if full_hash:
                full_hash_dict.setdefault(full_hash, []).append(f)
            processed_files += 1
            if progress_callback:
                progress_callback(
                    int(processed_files / total_files * 100) if total_files > 0 else 0
                )

    if progress_callback:
        progress_callback(100)
    return {h: files for h, files in full_hash_dict.items() if len(files) > 1}
