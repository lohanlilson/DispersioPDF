"""Dicionário: leitura do Wikcionário (texto de exemplo, sem internet), forma básica e janelinha no duplo clique."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio import dicionario as D

WT = """={{-pt-}}=
==Substantivo==
{{flex.pt|fs=casa|fp=casas}}
# [[construção]] que serve de [[moradia]]
#* ''Exemplo que não entra.''
# {{escopo|pt|Família}} [[lar]]
==Verbo==
# forma do verbo [[casar]]
={{-es-}}=
==Substantivo==
# isto é espanhol e não entra
"""
defs, lemma = D._pt_defs(WT)
assert defs[0] == ("Substantivo", "construção que serve de moradia"), defs
assert defs[1][1] == "(Família) lar" and len(defs) == 3 and lemma is None, (defs, lemma)
defs, lemma = D._pt_defs("={{-pt-}}=\n==Forma de substantivo==\n# plural de [[casa]]\n")
assert lemma == "casa"
assert D.clean_word("“Saudade!”") == "Saudade"

# janelinha: duplo clique numa palavra pede o significado
calls = []
D.lookup = lambda w, l="pt": calls.append((w, l)) or {"word": w, "lang": l, "defs": [("Substantivo", "teste")], "base": None,
                                                       "translation": None, "source": "teste"}
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
w = MainWindow(); w.resize(1200, 800); w.show()
d = pymupdf.open(); d.new_page().insert_text((72, 100), "A saudade é uma palavra bonita da língua portuguesa e de mais nada.", fontsize=14)
t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
for _ in range(10): app.processEvents()
v = t.view
k = next(n for n, wd in enumerate(v.words(0)) if wd[1] == "saudade")
r = v.words(0)[k][0]
it = v.items[0]
scene_pt = it.mapToScene(((r.x0 + r.x1) / 2) * v.scale(), ((r.y0 + r.y1) / 2) * v.scale())
vp = v.mapFromScene(scene_pt)
ev = QMouseEvent(QEvent.MouseButtonDblClick, QPointF(vp), QPointF(v.viewport().mapToGlobal(vp)), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
v.mouseDoubleClickEvent(ev)
for _ in range(20): app.processEvents()
assert v.selected_text() == "saudade", v.selected_text()
assert calls and calls[0] == ("saudade", "pt"), calls
while len(w.tab_widgets) > 1:
    w.close_tab(len(w.tab_widgets) - 1)
print("dicionário ok")
