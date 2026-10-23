"""Teste rápido: inicia o programa de verdade (main.main) e garante que tudo que o main.py chama existe."""
import os
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import main
from lumenpdf import system, updater

system.is_default_pdf = lambda: True          # não abre diálogos no CI
updater.Updater.auto_check = lambda self: None  # não acessa a rede
from lumenpdf.mainwindow import MainWindow

for attr in ("check_default_app", "bring_to_front", "open_path", "updater"):
    assert hasattr(MainWindow, attr) or attr == "updater", f"MainWindow sem {attr}"


def stop():
    app = QApplication.instance()
    win = next(w for w in app.topLevelWidgets() if isinstance(w, MainWindow))
    assert hasattr(win, "updater")
    win.check_default_app()
    app.quit()


orig_exec = QApplication.exec
QApplication.exec = lambda self=None: (QTimer.singleShot(1500, stop), orig_exec())[1]
sys.argv = ["main.py"]
rc = main.main()
print("smoke ok", rc)
