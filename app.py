import sys
import logging

from PyQt6.QtWidgets import QApplication

sys.dont_write_bytecode = True

from models.blockchain import Blockchain
from ui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(Blockchain())
    window.show()
    sys.exit(app.exec())
