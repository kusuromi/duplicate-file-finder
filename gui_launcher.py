# -*- coding: utf-8 -*-
import sys

from PyQt6.QtCore import QObject, QThread, pyqtSignal as Signal, pyqtSlot as Slot
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QTextEdit,
    QFileDialog, QVBoxLayout, QHBoxLayout, QProgressBar, QMessageBox
)

# ваша логика: должна вернуть dict: {hash: [paths]}
import simple_duplicate_finder as sdf


# -------- фоновый worker --------
class ScanWorker(QObject):
    result = Signal(dict)   # dict[hash] = [paths]
    error = Signal(str)
    finished = Signal()

    def __init__(self, folder):
        super().__init__()
        self.folder = folder

    @Slot()
    def run(self):
        try:
            data = sdf.find_duplicate_files_logic([self.folder]) or {}
            self.result.emit(data)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


# -------- простое окно --------
class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Поисковик дубликатов (PyQt6)")
        self.resize(800, 520)

        self.folder = None
        self.thread = None
        self.worker = None

        # верхняя строка: метка + кнопки
        self.lbl = QLabel("Папка не выбрана")

        self.btn_choose = QPushButton("Выбрать папку")
        self.btn_choose.clicked.connect(self.choose_folder)

        self.btn_scan = QPushButton("Сканировать")
        self.btn_scan.clicked.connect(self.start_scan)

        row = QHBoxLayout()
        row.addWidget(self.lbl, 1)
        row.addWidget(self.btn_choose)
        row.addWidget(self.btn_scan)

        # прогресс
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)

        # вывод
        self.out = QTextEdit()
        self.out.setReadOnly(True)

        # корневой layout
        root = QVBoxLayout(self)
        root.addLayout(row)
        root.addWidget(self.bar)
        root.addWidget(self.out, 1)

        self.println("Нажмите «Выбрать папку», затем «Сканировать».")

    # ---- утилиты вывода ----
    def println(self, text=""):
        self.out.append(text)

    # ---- UI handlers ----
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку")
        if folder:
            self.folder = folder
            self.lbl.setText(folder)
            self.println(f"Выбрана папка: {folder}")
        else:
            self.println("Выбор папки отменён.")

    def start_scan(self):
        if not self.folder:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку.")
            return
        if self.thread is not None:
            QMessageBox.information(self, "Информация", "Сканирование уже выполняется.")
            return

        self.out.clear()
        self.println("Сканирование запущено...")
        self.btn_choose.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.bar.setRange(0, 0)  # indeterminate

        self.thread = QThread(self)
        self.worker = ScanWorker(self.folder)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.result.connect(self.on_result)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)

        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup)

        self.thread.start()

    # ---- обработка результатов ----
    @Slot(dict)
    def on_result(self, file_hashes):
        self.println("")
        self.println("--- Найденные дубликаты ---")
        self.println("")

        groups = 0
        for h, files in file_hashes.items():
            if isinstance(files, list) and len(files) > 1:
                groups += 1
                self.println(f"Дубликаты по хешу {h}:")
                for p in files:
                    self.println(f"  - {p}")
                self.println("")

        if groups == 0:
            self.println("Дубликатов не найдено.")
        else:
            self.println(f"Найдено {groups} групп дубликатов.")

        self.println("")
        self.println("Сканирование завершено.")

    @Slot(str)
    def on_error(self, msg):
        self.println(f"Ошибка при сканировании: {msg}")

    @Slot()
    def on_finished(self):
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.btn_choose.setEnabled(True)
        self.btn_scan.setEnabled(True)

    @Slot()
    def cleanup(self):
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())
