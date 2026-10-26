"""Desfazer rápido de comentários: mover, apagar, mudar cor e editar nota voltam exatamente ao que era."""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QInputDialog
app = QApplication.instance() or QApplication([])
from lumenpdf.mainwindow import MainWindow
from lumenpdf.doctab import DocTab

d = pymupdf.open()
for i in range(3):
    p = d.new_page()
    p.insert_text((72, 100), f"Página {i + 1} — texto de exemplo para comentários", fontsize=12)
p = d[0]
h = p.add_highlight_annot(pymupdf.Rect(72, 88, 300, 104)); h.set_info(content="destaque"); h.update()
n = p.add_text_annot((400, 200), "nota original"); n.update()
ft = p.add_freetext_annot(pymupdf.Rect(72, 300, 300, 340), "Caixa de texto", fontsize=12, text_color=(0, 0, 1)); ft.update()
ink = p.add_ink_annot([[(100, 500), (150, 520), (200, 480)]]); ink.set_colors(stroke=(1, 0, 0)); ink.update()
data = d.tobytes()

w = MainWindow(); w.resize(1200, 800); w.show()
t = DocTab(data, None, None, w.settings); w.add_tab(t)
for _ in range(10): app.processEvents()
v = t.view


def state():
    pg = t.doc[0]
    pix = pg.get_pixmap(dpi=72).samples
    info = sorted((a.xref, a.type[1], tuple(round(c, 2) for c in a.rect), str(a.colors), a.info.get("content", "")) for a in pg.annots())
    return pix, info


def xref_of(kind):
    return next(a.xref for a in t.doc[0].annots() if a.type[1] == kind)


s0 = state()
ops_done = []
for kind in ("Highlight", "Text", "FreeText", "Ink"):
    v.sel_annot = (0, xref_of(kind))
    pg0 = t.doc[0]; r0 = pg0.load_annot(xref_of(kind)).rect
    v._move_annot((25, 15))
    pg0 = t.doc[0]; r1 = pg0.load_annot(xref_of(kind)).rect
    assert abs(r1.x0 - r0.x0 - 25) < 1 and abs(r1.y0 - r0.y0 - 15) < 1, f"{kind} não se moveu: {r0} -> {r1}"
    ops_done.append(f"mover {kind}")
    v.sel_annot = (0, xref_of(kind))
    v.recolor_selected_annot("#2d9d78")
    ops_done.append(f"cor {kind}")
v.sel_annot = (0, xref_of("Text"))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("nota alterada", True))
v.edit_annot_contents(); ops_done.append("nota")
for kind in ("Ink", "Highlight"):
    v.sel_annot = (0, xref_of(kind)); v.delete_selected_annot(); ops_done.append(f"apagar {kind}")
assert all(isinstance(e, tuple) and e[0] == "objetos" for e in t.undo_stack[-len(ops_done):]), "deveria usar o desfazer rápido"
s1 = state()
assert s1 != s0
for _ in ops_done:
    t.undo()
s2 = state()
assert s2[1] == s0[1], f"comentários diferentes:\n{s2[1]}\n{s0[1]}"
assert s2[0] == s0[0], "a página desenhada ficou diferente depois de desfazer"
# refazer tudo volta ao estado editado
for _ in ops_done:
    t.redo()
assert state()[1] == s1[1]
print(f"desfazer rápido ok ({len(ops_done)} operações)")

# criar caixa de texto pela ferramenta (falhava com o PyMuPDF 2)
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Caixa nova", True))
n0 = len(list(t.doc[0].annots()))
v._finish_drag(0, "freetext", pymupdf.Rect(300, 600, 500, 650), pymupdf.Point(300, 600), pymupdf.Point(500, 650))
assert len(list(t.doc[0].annots())) == n0 + 1, "caixa de texto não foi criada"
print("caixa de texto ok")

# tempo num documento grande
big = pymupdf.open()
for i in range(250):
    pg = big.new_page(); pg.insert_text((50, 60), "texto " * 40, fontsize=9)
    if i % 3 == 0:
        pg.insert_image(pymupdf.Rect(60, 300, 540, 800), pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 700, 700), 0))
pg = big[0]; a = pg.add_highlight_annot(pymupdf.Rect(50, 50, 300, 64)); a.update()
bd = big.tobytes()
t2 = DocTab(bd, None, None, w.settings); w.add_tab(t2)
for _ in range(10): app.processEvents()
xr = next(a.xref for a in t2.doc[0].annots())
t2.view.sel_annot = (0, xr)
a0 = time.perf_counter(); t2.view._move_annot((10, 10)); t1 = time.perf_counter() - a0
t2.view.sel_annot = (0, xr)
a0 = time.perf_counter(); t2.view.recolor_selected_annot("#ff0000"); t2_ = time.perf_counter() - a0
print(f"PDF de {len(bd) / 1e6:.0f} MB: mover {t1 * 1000:.0f} ms, cor {t2_ * 1000:.0f} ms")
assert t1 < 0.25 and t2_ < 0.25
