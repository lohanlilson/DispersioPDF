"""A página na tela deve ser desenhada 1:1 com a renderização (sem reamostragem que borra o texto)."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
app = QApplication([])
from lumenpdf.viewer import PdfView
d = pymupdf.open()
pg = d.new_page()
for k in range(40):
    pg.insert_text((50, 60 + k * 18), "Texto de teste nítido 0123456789 ABCDEFGHIJ abcdefghij", fontsize=11)
v = PdfView(); v.resize(900, 700); v.show()
v.set_document(d)
for z in (1.0, 1.37):
    v.set_zoom(z)
    for _ in range(60):
        app.processEvents()
    v._render_next()
    for _ in range(20):
        app.processEvents()
    s, pm = v.cache[0]
    ref = pm.toImage().convertToFormat(QImage.Format_RGB32)
    shot = v.viewport().grab().toImage().convertToFormat(QImage.Format_RGB32)
    it = v.items[0]
    o = v.mapFromScene(it.pos())
    W, H = 300, 300
    # procura o deslocamento exato (±1px) — tem de existir um alinhamento com diferença zero
    best = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            diff = 0
            x0, y0 = max(0, -o.x()) + 30, max(0, -o.y()) + 40
            for y in range(y0, y0 + H, 3):
                for x in range(x0, x0 + W, 3):
                    a = shot.pixel(o.x() + x + dx, o.y() + y + dy) & 0xFFFFFF
                    b = ref.pixel(x, y) & 0xFFFFFF
                    diff += a != b
            best = diff if best is None else min(best, diff)
    assert best == 0, f"zoom {z}: página reamostrada ({best} pixels diferentes)"
print("nitidez ok (desenho 1:1)")
