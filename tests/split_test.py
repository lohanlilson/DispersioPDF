"""Divisão de tela: mesmo documento (edições refletem nos dois lados) e outro documento aberto."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab


def mk(n, label):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"{label} página {i + 1}")
    return d.tobytes()


w = MainWindow(); w.resize(1400, 900); w.show()
a = DocTab(mk(10, "A"), None, None, w.settings); w.add_tab(a)
b = DocTab(mk(4, "B"), None, None, w.settings); w.add_tab(b)
w.tabbar.setCurrentIndex(1)
for _ in range(20): app.processEvents()
assert a.toggle_split() and a.pane is not None
pane = a.pane
assert pane.view.doc is a.doc and pane.view.current_page() >= 0
# edição estrutural no documento (exclui página) reflete no painel
a.checkpoint(); a.doc.delete_page(0); a.changed(structure=True)
assert len(pane.view.items) == 9, len(pane.view.items)
# desfazer recarrega o documento e o painel acompanha
a.undo()
assert pane.view.doc is a.doc and len(pane.view.items) == 10
# outro documento aberto (cópia somente leitura) com rolagem sincronizada
pane._fill_sources()
idx = next(i for i in range(pane.source.count()) if pane.source.itemData(i) is b)
pane.source.setCurrentIndex(idx); pane._source_chosen(idx)
assert pane.own_doc is not None and pane.own_doc.page_count == 4 and pane.sync.isChecked()
a.view.goto(2)
for _ in range(10): app.processEvents()
assert pane.view.current_page() == 2, pane.view.current_page()
pane._toggle_orientation()
from PySide6.QtCore import Qt
assert a.splitter.orientation() == Qt.Vertical
assert not a.toggle_split() and a.pane is None
w.close_tab(1) if False else None
print("divisão de tela ok")
