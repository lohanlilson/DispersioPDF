"""Fila da impressora Dispersio PDF e "Imprimir todas as abas abertas" (parte que roda em qualquer sistema)."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DISPERSIO_PRINTER_TEST_DIR"] = tempfile.mkdtemp()
import pymupdf
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

app = QApplication.instance() or QApplication([])
from dispersio import impressora, impressora_ui
from dispersio.doctab import DocTab
from dispersio.mainwindow import MainWindow
from dispersio import print_manager

DocTab.AUTOSAVE_MS = 10 ** 8
assert impressora.safe_name("Relatório: março/2026.docx - Word") == "Relatório março 2026"
assert impressora.safe_name("") == "Documento"

q = impressora.queue_dir()
for i, t in enumerate(["Primeiro documento", "Segundo documento", "Terceiro"]):
    d = pymupdf.open(); d.new_page().insert_text((72, 72), f"Página do {t}")
    if i == 1:
        d.new_page().insert_text((72, 72), "Segunda página do segundo")
    d.save(os.path.join(q, f"20261028-08000{i}-{i+1} {t}.pdf"))
    time.sleep(0.02)
assert [impressora.title_of(f) for f in impressora.queue_files()] == ["Primeiro documento", "Segundo documento", "Terceiro"]

w = MainWindow(); w.show()
w.receive_printed([impressora.queue_files()[1]])
dlg = w._printer_dlg
assert dlg.list.count() == 3 and [it.isSelected() for it in (dlg.list.item(i) for i in range(3))] == [False, True, False]
assert dlg.chosen() == [impressora.queue_files()[1]]
assert dlg.parent() is None and dlg.isWindow(), "a fila é uma janela independente do leitor"
assert dlg.paths("sel") == [impressora.queue_files()[1]] and len(dlg.paths("all")) == 3
assert dlg.buttons[("sel", "save")].isEnabled() and dlg.buttons[("all", "save")].isEnabled()
assert dlg.buttons[("sel", "save")].text() == "Salvar como…" and dlg.buttons[("all", "save")].text() == "Salvar num PDF só…"
dlg.list.clearSelection()
assert len(dlg.chosen()) == 3 and not dlg.buttons[("sel", "merge")].isEnabled() and dlg.buttons[("all", "merge")].isEnabled()

# juntar tudo num PDF só, na ordem da lista
out = os.path.join(tempfile.mkdtemp(), "junto.pdf")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
dlg.save()
j = pymupdf.open(out)
assert j.page_count == 4 and "Primeiro" in j[0].get_text() and "Terceiro" in j[3].get_text(), [p.get_text() for p in j]

# reordenar (arrastar) muda a ordem do resultado
it = dlg.list.takeItem(2); dlg.list.insertItem(0, it)
dlg.merge_open()
t = w.cur()
assert t.doc.page_count == 4 and "Terceiro" in t.doc[0].get_text()

# tirar da fila
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
dlg.list.item(0).setSelected(True)
dlg.remove()
assert dlg.list.count() == 2 and len(impressora.queue_files()) == 2

# indicador de página no topo
w.cur().view.goto(1); app.processEvents()
assert w.page_box.isVisible() and w.page_edit.text() == "2" and w.page_total.text() == f"de {w.cur().doc.page_count}"
w.page_edit.setText("4"); w.page_edit.returnPressed.emit(); app.processEvents()
assert w.cur().view.current_page() == 3

# imprimir todas as abas abertas: o diálogo oferece e usa todas as abas, na ordem
dlg.open_each()
n_tabs = len(w.open_tab_sources())
assert n_tabs >= 3, n_tabs
captured = {}
orig_exec = print_manager.PrintManager.exec
def fake_exec(self):
    captured["one"] = [s.name for s in self.sources]
    self.scope_all.setChecked(True)
    captured["all"] = [s.name for s in self.sources]
    captured["range_enabled"] = self.pg_rng.isEnabled()
    captured["summary"] = self.summary.text()
    return 0
print_manager.PrintManager.exec = fake_exec
w.tool_print(w.cur())
assert len(captured["one"]) == 1 and len(captured["all"]) == n_tabs and not captured["range_enabled"], captured
captured.clear()
w.run_tool("print_all")
assert len(captured["one"]) == n_tabs, captured  # já abre com todas as abas
print_manager.PrintManager.exec = orig_exec
# fechar o leitor com a fila aberta e depois abrir um documento da fila: o leitor volta a aparecer
dlg.show(); w.close(); app.processEvents()
assert not w.isVisible() and dlg.isVisible()
dlg._open([impressora.queue_files()[0]]); app.processEvents()
assert w.isVisible() and w.cur() is not None and w.cur().path == impressora.queue_files()[0], "o leitor reabriu com o arquivo"
print("impressora ok", captured["summary"])
