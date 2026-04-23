import sys
import os
import shutil
import logging
import tkinter as tk

sys.dont_write_bytecode = True

from models.blockchain import Blockchain
from ui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    root = tk.Tk()
    MainWindow(root, Blockchain())
    root.mainloop()
