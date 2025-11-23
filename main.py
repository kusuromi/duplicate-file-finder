# main.py
import sys
from PyQt6.QtWidgets import QApplication
from gui import Window

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())
