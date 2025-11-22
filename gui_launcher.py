# -*- coding: utf-8 -*-
import sys
import os
import hashlib

from PyQt6.QtCore import QObject, QThread, pyqtSignal as Signal, pyqtSlot as Slot, Qt, QEvent, QFileInfo, QSize
from PyQt6.QtGui import QColor, QBrush, QDragEnterEvent, QDropEvent, QPalette
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QFileDialog, QVBoxLayout, QHBoxLayout, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QStyle,
    QStackedWidget, QFrame, QSizePolicy, QHeaderView, QTreeWidgetItemIterator,
    QFileIconProvider
)

# ------------------ ЛОГИКА ПОИСКА ДУБЛИКАТОВ ------------------
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
    for path in paths:
        if not os.path.exists(path) or not os.path.isdir(path): continue
        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                if "@eaDir" in full_path or "@SynoEAStream" in full_path: continue
                if os.path.islink(full_path): continue
                try:
                    size = os.path.getsize(full_path)
                    if size == 0: continue
                except OSError: continue
                size_dict.setdefault(size, []).append(full_path)
                all_files.append(full_path)

    total_files = len(all_files)
    processed_files = 0
    fast_hash_dict = {}
    for files in size_dict.values():
        if len(files) < 2:
            processed_files += len(files)
            if progress_callback: progress_callback(int(processed_files / total_files * 100) if total_files > 0 else 0)
            continue
        for f in files:
            fhash = calculate_file_hash(f, first_chunk_only=True)
            if fhash: fast_hash_dict.setdefault(fhash, []).append(f)
            processed_files += 1
            if progress_callback: progress_callback(int(processed_files / total_files * 100) if total_files > 0 else 0)

    full_hash_dict = {}
    for files in fast_hash_dict.values():
        if len(files) < 2:
            processed_files += len(files)
            if progress_callback: progress_callback(int(processed_files / total_files * 100) if total_files > 0 else 0)
            continue
        for f in files:
            full_hash = calculate_file_hash(f, first_chunk_only=False)
            if full_hash: full_hash_dict.setdefault(full_hash, []).append(f)
            processed_files += 1
            if progress_callback: progress_callback(int(processed_files / total_files * 100) if total_files > 0 else 0)

    if progress_callback: progress_callback(100)
    return {h: files for h, files in full_hash_dict.items() if len(files) > 1}

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
        self.setWindowTitle("Duplicate Finder")
        self.resize(550, 400)
        self.setAcceptDrops(True)

        self.folder = None
        self.thread = None
        self.worker = None
        
        self.secondary_text_color = QColor("gray")
        self.icon_provider = QFileIconProvider()

        # ---- ВЕРХНЯЯ ПАНЕЛЬ ----
        self.btn_path = QPushButton("Выберите папку")
        self.btn_path.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.btn_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_path.clicked.connect(self.choose_folder)

        self.btn_scan = QPushButton("Сканировать")
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_scan.setEnabled(False)
        self.btn_scan.setAutoDefault(False)
        
        self.btn_delete = QPushButton("Удалить выбранное")
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_delete.setEnabled(False)
        self.btn_delete.setAutoDefault(False)

        top_row = QHBoxLayout()
        top_row.addWidget(self.btn_path)
        top_row.addWidget(self.btn_scan)
        top_row.addWidget(self.btn_delete)
        
        top_row.setContentsMargins(15, 15, 15, 10)
        top_row.setSpacing(10)

        top_widget = QWidget()
        top_widget.setLayout(top_row)

        # ---- Прогрессбар ----
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)

        bar_widget = QWidget()
        bar_layout = QVBoxLayout(bar_widget)
        bar_layout.setContentsMargins(15, 0, 15, 10) 
        bar_layout.addWidget(self.bar)

        # ---- ЦЕНТРАЛЬНАЯ ЗОНА (STACK) ----
        self.stack = QStackedWidget()
        
        # 1. СТРАНИЦА ЗАГЛУШКИ
        self.page_empty = QFrame()
        self.page_empty.setObjectName("mainFrame") 
        
        empty_layout = QVBoxLayout(self.page_empty)
        
        empty_layout.addStretch(1)
        
        self.lbl_big_icon = QLabel()
        icon_pixmap = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon).pixmap(128, 128)
        self.lbl_big_icon.setPixmap(icon_pixmap)
        self.lbl_big_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_big_icon.setStyleSheet("background: transparent; border: none;")
        
        self.lbl_welcome = QLabel("Перетащите папку сюда\nдля поиска дубликатов")
        self.lbl_welcome.setWordWrap(True)
        self.lbl_welcome.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.lbl_welcome.setFixedHeight(80)
        
        empty_layout.addWidget(self.lbl_big_icon)
        empty_layout.addWidget(self.lbl_welcome)
        
        empty_layout.addStretch(1)

        # 2. СТРАНИЦА ДЕРЕВА
        self.tree_container = QFrame()
        self.tree_container.setObjectName("mainFrame") 
        
        tree_layout = QVBoxLayout(self.tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0) 
        tree_layout.setSpacing(0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Дубликаты файлов"])
        self.tree.setColumnCount(1)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(18, 18))

        tree_layout.addWidget(self.tree)

        self.stack.addWidget(self.page_empty)
        self.stack.addWidget(self.tree_container)

        # ---- ГЛАВНЫЙ ЛЕЙАУТ ----
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0) 
        layout.setSpacing(0)
        
        layout.addWidget(top_widget) 
        layout.addWidget(bar_widget)
        layout.addWidget(self.stack)

        self.update_theme()

    # ---- ОБНОВЛЕНИЕ ТЕМЫ ----
    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange or event.type() == QEvent.Type.StyleChange:
            self.update_theme()
        super().changeEvent(event)

    def update_theme(self):
        pal = self.palette()
        
        bg_color_q = pal.color(QPalette.ColorRole.Base)
        text_color = pal.color(QPalette.ColorRole.Text).name()
        border_color = pal.color(QPalette.ColorRole.Mid).name()
        header_bg = pal.color(QPalette.ColorRole.Button).name()
        
        base_text_color = pal.color(QPalette.ColorRole.Text)
        self.secondary_text_color = QColor(base_text_color)
        self.secondary_text_color.setAlpha(128)
        
        secondary_rgba = f"rgba({self.secondary_text_color.red()}, {self.secondary_text_color.green()}, {self.secondary_text_color.blue()}, {self.secondary_text_color.alpha()/255})"

        is_dark = bg_color_q.lightness() < 128

        if is_dark:
            bg_color_str = "#1E1E1E" 
            alt_bg_str = "#262626"
            header_bg_str = "#2D2D2D"
            border_color_str = "#333333"
        else:
            bg_color_str = bg_color_q.name()
            alt_bg_str = bg_color_q.darker(105).name()
            header_bg_str = header_bg
            border_color_str = border_color

        style_sheet = f"""
            QFrame#mainFrame {{
                background-color: {bg_color_str};
                border: none;
                border-top: 1px solid {border_color_str};
            }}
            
            QTreeWidget {{
                background-color: {bg_color_str};
                alternate-background-color: {alt_bg_str};
                color: {text_color};
                border: none;
                font-size: 13px;
            }}
            
            QTreeWidget::item {{
                padding-top: 6px;
                padding-bottom: 6px;
                padding-left: 10px;
                padding-right: 15px;
            }}
            
            QHeaderView::section {{
                background-color: {header_bg_str};
                color: {text_color};
                border: none;
                border-bottom: 1px solid {border_color_str};
                border-right: 1px solid {border_color_str};
                padding-top: 4px;
                padding-bottom: 4px;
                padding-left: 15px;
                padding-right: 15px;
                font-weight: bold;
            }}
            
            QTableCornerButton::section {{
                background-color: {header_bg_str};
                border: none;
            }}
        """
        
        self.page_empty.setStyleSheet(style_sheet)
        self.tree_container.setStyleSheet(style_sheet)
        
        self.lbl_welcome.setStyleSheet(f"background: transparent; border: none; color: {secondary_rgba}; font-size: 16px; margin-top: 15px;")

        self.update_tree_colors()

    def update_tree_colors(self):
        pal = self.palette()
        normal_color = pal.color(QPalette.ColorRole.Text)
        secondary_brush = QBrush(self.secondary_text_color)
        
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            group.setForeground(0, QBrush(normal_color))
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    child.setForeground(0, QBrush(normal_color))
                else:
                    child.setForeground(0, secondary_brush)

    # ---- Drag & Drop ----
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and len(urls) == 1:
                path = urls[0].toLocalFile()
                if os.path.isdir(path):
                    event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.set_folder(path)

    # ---- Logic ----
    def set_folder(self, path):
        self.folder = path
        # Используем normpath, чтобы убрать слеш на конце
        clean_path = os.path.normpath(path)
        folder_name = os.path.basename(clean_path)
        if not folder_name: folder_name = clean_path
        
        # Устанавливаем имя папки
        self.btn_path.setText(f"Папка: {folder_name}")
        self.btn_path.setToolTip(path)
        
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("Сканировать")
        self.btn_scan.setDefault(True)
        self.btn_delete.setDefault(False)
        
        self.bar.setValue(0)
        
        self.lbl_big_icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon).pixmap(128, 128))
        self.lbl_welcome.setText(f"Выбранная папка: {folder_name}\nнажмите сканировать")
        self.stack.setCurrentIndex(0)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку")
        if folder:
            self.set_folder(folder)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    def start_scan(self):
        if not self.folder:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку.")
            return
        if self.thread is not None: return

        is_update_mode = (self.btn_scan.text() == "Обновить")

        if not is_update_mode:
            self.stack.setCurrentIndex(0)
            self.lbl_welcome.setText("Идет поиск дубликатов...")
        else:
            self.stack.setCurrentIndex(1)
        
        self.tree.clear()
        self.btn_delete.setEnabled(False)
        self.btn_delete.setDefault(False)
        
        self.btn_scan.setEnabled(False)
        self.btn_scan.setDefault(False)
        
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
        self.tree.blockSignals(True)
        self.tree.clear()

        if not file_hashes:
            self.tree.blockSignals(False)
            self.stack.setCurrentIndex(0)
            self.folder = None
            self.btn_path.setText("Выберите папку")
            self.btn_path.setToolTip("")
            self.lbl_welcome.setText("Дубликатов не найдено\nвыберите другую папку")
            self.lbl_big_icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon).pixmap(128, 128))
            
            self.btn_scan.setText("Сканировать")
            self.btn_scan.setEnabled(False)
            self.btn_scan.setDefault(False)
            self.btn_delete.setEnabled(False)
            self.btn_delete.setDefault(False)
            return

        disabled_brush = QBrush(self.secondary_text_color)
        
        for h, files in file_hashes.items():
            first_file = files[0]
            file_name = os.path.basename(first_file)
            size_str = "Unknown"
            try:
                size_bytes = os.path.getsize(first_file)
                size_str = self.format_size(size_bytes)
            except: pass

            header_text = f"{file_name} ({size_str}) — копий: {len(files)}"
            parent = QTreeWidgetItem(self.tree, [header_text])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            
            # Иконка для заголовка
            file_icon = self.icon_provider.icon(QFileInfo(first_file))
            parent.setIcon(0, file_icon)
            
            for f in files:
                try:
                    display_text = os.path.relpath(f, self.folder)
                except ValueError:
                    display_text = f
                
                child = QTreeWidgetItem(parent, [display_text])
                child.setData(0, Qt.ItemDataRole.UserRole, f)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setForeground(0, disabled_brush)

        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.stack.setCurrentIndex(1)
        self.btn_delete.setEnabled(False)
        
        self.btn_scan.setText("Обновить")

    @Slot(QTreeWidgetItem, int)
    def on_item_changed(self, item, column):
        if item.childCount() > 0: return
        pal = self.palette()
        
        if item.checkState(0) == Qt.CheckState.Checked:
            item.setForeground(0, QBrush(pal.color(QPalette.ColorRole.Text)))
        else:
            item.setForeground(0, QBrush(self.secondary_text_color))
            
        has_checked = False
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        if iterator.value():
            has_checked = True
            
        self.btn_delete.setEnabled(has_checked)
        
        if has_checked:
            self.btn_delete.setDefault(True)
        else:
            self.btn_delete.setDefault(False)

    @Slot(str)
    def on_error(self, msg):
        QMessageBox.critical(self, "Ошибка", msg)

    @Slot()
    def on_finished(self):
        self.bar.setValue(0)
        if self.folder:
            self.btn_scan.setEnabled(True)
            self.btn_scan.setDefault(False)
        else:
            self.btn_scan.setEnabled(False)

    @Slot()
    def cleanup(self):
        if self.worker is not None: self.worker.deleteLater()
        if self.thread is not None: self.thread.deleteLater()
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
                    full_path = child.data(0, Qt.ItemDataRole.UserRole)
                    if full_path: to_delete.append(full_path)

        if not to_delete: return
        
        reply = QMessageBox.question(self, "Удаление", f"Удалить файлы? ({len(to_delete)} шт.)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from send2trash import send2trash
            except ImportError:
                QMessageBox.critical(self, "Ошибка", "Библиотека send2trash \nне установлена!\nВыполните:\npip install send2trash")
                return

            for f in to_delete:
                try:
                    send2trash(f)
                except Exception as e:
                    print(f"Ошибка при удалении {f}: {e}")
            
            self.start_scan()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())