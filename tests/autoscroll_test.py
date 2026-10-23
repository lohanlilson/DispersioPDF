import os, sys; os.environ["QT_QPA_PLATFORM"]="offscreen"; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
app = QApplication([])
from lumenpdf.viewer import PdfView
d = pymupdf.open()
for _ in range(30): d.new_page()
v = PdfView(); v.resize(800, 600); v.show()
v.set_document(d) if hasattr(v, "set_document") else v.load(d)
for _ in range(20): app.processEvents()
vp = v.viewport(); bar = v.verticalScrollBar()
# modo clique: clicar e soltar o meio, mover para baixo
start = bar.value()
QTest.mouseClick(vp, Qt.MiddleButton, pos=QPoint(400, 300))
assert v._as_active, "não ativou"
QTest.mouseMove(vp, QPoint(400, 420))
QTest.qWait(400)
assert bar.value() > start + 50, (start, bar.value())
mid = bar.value()
QTest.mouseMove(vp, QPoint(400, 180)); QTest.qWait(300)
assert bar.value() < mid, "não subiu"
QTest.mouseClick(vp, Qt.LeftButton, pos=QPoint(400, 180))
assert not v._as_active
# modo segurar-arrastar
QTest.mousePress(vp, Qt.MiddleButton, pos=QPoint(400, 300))
QTest.mouseMove(vp, QPoint(400, 450)); QTest.qWait(200)
QTest.mouseRelease(vp, Qt.MiddleButton, pos=QPoint(400, 450))
assert not v._as_active
# desativado nas preferências
v.middle_autoscroll = False
QTest.mouseClick(vp, Qt.MiddleButton, pos=QPoint(400, 300))
assert not v._as_active
print("OK autoscroll", start, mid, bar.value())
