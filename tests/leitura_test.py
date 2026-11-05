"""Modo de leitura: entra e sai pelo menu (Ctrl+H), por Esc e pelo botão flutuante."""
import os, sys, tempfile
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
app = QApplication([])
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab
DocTab.AUTOSAVE_MS = 10 ** 8
d = pymupdf.open(); d.new_page().insert_text((72, 72), "Teste"); fn = os.path.join(tempfile.mkdtemp(), "rm.pdf"); d.save(fn)
w = MainWindow(); w.resize(1366, 768); w.show(); w.open_path(fn)
for _ in range(20): app.processEvents(); time.sleep(0.02)
top = w.doc_area.layout().itemAt(0).widget()
# liga pelo menu (como Ctrl+H) e desliga de novo
from PySide6.QtGui import QAction
act = [a for a in w.findChildren(QAction) if a.text() == "Modo de leitura"]
act[0].trigger(); app.processEvents()
assert not top.isVisible() and w._reading_bar.isVisible(), "entrou"
act[0].trigger(); app.processEvents()
assert top.isVisible() and not w._reading_bar.isVisible(), "Ctrl+H sai"
act[0].trigger(); app.processEvents(); w._reading_esc.trigger(); app.processEvents()
assert top.isVisible() and not w._reading_esc.isEnabled(), "Esc sai"
act[0].trigger(); app.processEvents()
btn = [b for b in w._reading_bar.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)][0]
btn.click(); app.processEvents()
assert top.isVisible() and w.cur().rail.isVisible(), "botão sai"
print("modo de leitura ok")
