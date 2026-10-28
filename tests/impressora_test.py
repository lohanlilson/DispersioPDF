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
dlg.list.clearSelection()
assert len(dlg.chosen()) == 3

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
print("impressora ok", captured["summary"])
