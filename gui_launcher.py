# -*- coding: utf-8 -*-
import sys
import os
import hashlib
import shutil

from PyQt6.QtCore import QObject, QThread, pyqtSignal as Signal, pyqtSlot as Slot, Qt
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QTextEdit,
    QFileDialog, QVBoxLayout, QHBoxLayout, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QMessageBox
)

# ------------------ логика поиска дубликатов с прогрессом ------------------
def calculate_file_hash(filepath, hash_algorithm=hashlib.sha256, chunk_size=4096, first_chunk_only=False):
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
    except (OSError, IOError):
        return None


def find_duplicate_files_logic(paths, progress_callback=None):
    size_dict = {}
    all_files = []

    # собираем все файлы
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

    # быстрый хеш первых 4КБ
    fast_hash_dict = {}
    for files in size_dict.values():
        if len(files) < 2:
            processed_files += len(files)
            if progress_callback:
                progress_callback(int(processed_files / total_files * 100))
            continue
        for f in files:
            fhash = calculate_file_hash(f, first_chunk_only=True)
            if fhash:
                fast_hash_dict.setdefault(fhash, []).append(f)
            processed_files += 1
            if progress_callback:
                progress_callback(int(processed_files / total_files * 100))

    # полный хеш только для подозрительных
    full_hash_dict = {}
    for files in fast_hash_dict.values():
        if len(files) < 2:
            processed_files += len(files)
            if progress_callback:
                progress_callback(int(processed_files / total_files * 100))
            continue
        for f in files:
            full_hash = calculate_file_hash(f, first_chunk_only=False)
            if full_hash:
                full_hash_dict.setdefault(full_hash, []).append(f)
            processed_files += 1
            if progress_callback:
                progress_callback(int(processed_files / total_files * 100))

    if progress_callback:
        progress_callback(100)

    # оставляем только группы с дубликатами
    return {h: files for h, files in full_hash_dict.items() if len(files) > 1}


# ------------------ фоновый worker ------------------
class ScanWorker(QObject):
    result = Signal(dict)
    error = Signal(str)
    finished = Signal()
    progress = Signal(int)

    def __init__(self, folder):
        super().__init__()
        self.folder = folder

    @Slot()
    def run(self):
        try:
            data = find_duplicate_files_logic([self.folder], progress_callback=self.progress.emit)
            self.result.emit(data)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


# ------------------ GUI ------------------
class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Поисковик дубликатов с выбором удаления")
        self.resize(900, 600)

        self.folder = None
        self.thread = None
        self.worker = None

        # ---- верхняя панель ----
        self.lbl = QLabel("Папка не выбрана")
        self.btn_choose = QPushButton("Выбрать папку")
        self.btn_choose.clicked.connect(self.choose_folder)
        self.btn_scan = QPushButton("Сканировать")
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_delete = QPushButton("Удалить выбранное")
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_delete.setEnabled(False)

        top_row = QHBoxLayout()
        top_row.addWidget(self.lbl, 1)
        top_row.addWidget(self.btn_choose)
        top_row.addWidget(self.btn_scan)
        top_row.addWidget(self.btn_delete)

        # ---- прогрессбар ----
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)

        # ---- дерево дубликатов ----
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Дубликаты файлов"])
        self.tree.setColumnCount(1)

        # ---- корневой layout ----
        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.bar)
        layout.addWidget(self.tree, 1)

    def println(self, text=""):
        # Можно добавить отдельный QTextEdit для логов, если нужно
        print(text)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку")
        if folder:
            self.folder = folder
            self.lbl.setText(folder)
            self.println(f"Выбрана папка: {folder}")

    def start_scan(self):
        if not self.folder:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку.")
            return
        if self.thread is not None:
            QMessageBox.information(self, "Информация", "Сканирование уже выполняется.")
            return

        self.tree.clear()
        self.btn_delete.setEnabled(False)
        self.bar.setValue(0)

        self.thread = QThread(self)
        self.worker = ScanWorker(self.folder)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.result.connect(self.on_result)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.progress.connect(self.on_progress)

        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup)

        self.thread.start()

    @Slot(int)
    def on_progress(self, value):
        self.bar.setValue(value)

    @Slot(dict)
    def on_result(self, file_hashes):
        self.tree.clear()
        for h, files in file_hashes.items():
            parent = QTreeWidgetItem(self.tree, [f"Группа дубликатов (hash: {h})"])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for f in files:
                child = QTreeWidgetItem(parent, [f])
                child.setCheckState(0, Qt.CheckState.Unchecked)
        self.tree.expandAll()
        self.btn_delete.setEnabled(True)

    @Slot(str)
    def on_error(self, msg):
        QMessageBox.critical(self, "Ошибка", msg)

    @Slot()
    def on_finished(self):
        self.bar.setValue(100)
        self.btn_scan.setEnabled(True)
        self.btn_choose.setEnabled(True)

    @Slot()
    def cleanup(self):
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None

    def delete_selected(self):
        to_delete = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    to_delete.append(child.text(0))

        if not to_delete:
            QMessageBox.information(self, "Информация", "Выберите файлы для удаления.")
            return

        reply = QMessageBox.question(
            self, "Подтверждение удаления",
            f"Удалить {len(to_delete)} выбранных файлов?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            deleted = 0
            for f in to_delete:
                try:
                    os.remove(f)
                    deleted += 1
                except OSError as e:
                    print(f"Ошибка при удалении {f}: {e}")
            QMessageBox.information(self, "Удаление завершено", f"Удалено файлов: {deleted}")
            self.start_scan()  # пересканировать и обновить дерево


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())
