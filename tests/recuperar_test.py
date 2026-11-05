"""PDF baixado pela metade: sem páginas legíveis avisa; com parte das páginas abre uma cópia recuperada."""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
import pymupdf
pymupdf.TOOLS.mupdf_display_errors(False)
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio.mainwindow import MainWindow
from dispersio import ops

msgs = []
QMessageBox.warning = staticmethod(lambda *a, **k: msgs.append(a[2]) or QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: msgs.append("ERRO " + a[2]) or QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
tmp = tempfile.mkdtemp()

# documento com muitas páginas e objetos grandes, gravado sem compactação de objetos
rnd = random.Random(7)
d = pymupdf.open()
for i in range(30):
    p = d.new_page()
    p.insert_text((72, 72), f"Página {i + 1}", fontsize=20)
    p.insert_image(pymupdf.Rect(72, 100, 500, 700), pixmap=pymupdf.Pixmap(pymupdf.csRGB, 120, 120, rnd.randbytes(120 * 120 * 3), 0))
full = d.tobytes()
cut = os.path.join(tmp, "metade.pdf")
open(cut, "wb").write(full[:int(len(full) * 0.6)])
empty = os.path.join(tmp, "nada.pdf")
open(empty, "wb").write(full[:400])

w = MainWindow(); w.show()
n = len(w.tab_widgets)
w.open_path(empty)
assert len(w.tab_widgets) == n, "não deveria abrir aba para arquivo sem páginas"
assert msgs and ("nenhuma" in msgs[-1].lower() or "ERRO" in msgs[-1]), msgs

probe = pymupdf.open(cut)
bad = ops.broken_pages(probe) if probe.page_count else []
print("páginas", probe.page_count, "danificadas", len(bad))
msgs.clear()
w.open_path(cut)
for _ in range(10): app.processEvents()
if probe.page_count:
    assert len(w.tab_widgets) == n + 1, msgs
    t = w.tab_widgets[-1]
    for i in range(t.doc.page_count):
        t.doc[i].get_pixmap(dpi=10)       # tudo que abriu tem de desenhar
    if bad:
        assert t.path is None and "recuperado" in t.title(), t.title()
        assert any("recuperada" in m for m in msgs), msgs
assert open(cut, "rb").read() == full[:int(len(full) * 0.6)], "o original não pode ser alterado"
# página ilegível (simulada): abre cópia "recuperada" e a página perdida vira aviso
orig_ok = ops._page_ok
ops._page_ok = lambda doc, i: i != 2 and orig_ok(doc, i)
ops.broken_pages = lambda doc: [2]
small = os.path.join(tmp, "dano.pdf")
d = pymupdf.open()
for i in range(5):
    d.new_page().insert_text((72, 72), f"Folha {i + 1}", fontsize=20)
d.save(small)
msgs.clear(); n = len(w.tab_widgets)
w.open_path(small)
for _ in range(10): app.processEvents()
assert len(w.tab_widgets) == n + 1, msgs
t = w.tab_widgets[-1]
assert t.path is None and "recuperado" in t.title(), t.title()
assert any("4 de 5" in m for m in msgs), msgs
assert "não foi possível ler" in t.doc[2].get_text() and t.doc.page_count == 5
assert not t.doc[0].get_text().strip()          # as boas viram imagem
print("recuperação ok")
os._exit(0)
