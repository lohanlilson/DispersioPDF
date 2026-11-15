"""Busca em pasta: acentos/maiúsculas, CPF/CNPJ com ou sem pontuação, subpastas, protegidos e digitalizados."""
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio import busca_pasta as B
from dispersio.mainwindow import MainWindow

root = tempfile.mkdtemp()
os.makedirs(os.path.join(root, "clientes", "2026"))
def pdf(path, *pages, **kw):
    d = pymupdf.open()
    for t in pages:
        d.new_page().insert_text((72, 72), t, fontsize=11)
    d.save(os.path.join(root, path), **kw)
pdf("contrato.pdf", "Contrato de cessão de crédito", "Cedente: COOPERATIVA CENTRAL DE CRÉDITO, CNPJ 07.202.627/0001-74")
pdf("clientes/2026/ficha.pdf", "Ficha cadastral — cnpj 07202627000174 — Crédito aprovado")
pdf("outro.pdf", "Nada a ver aqui")
pdf("senha.pdf", "credito", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="x")
img = pymupdf.open(); img.new_page(); img.save(os.path.join(root, "digitalizado.pdf"))

pat = B.make_pattern("credito")
hits, _ = B.search_file(os.path.join(root, "contrato.pdf"), pat)
assert [h[0] for h in hits] == [0, 1], hits
assert hits[0][2] == "crédito", "o texto achado é o original (com acento)"
pat = B.make_pattern("07202627000174")
assert B.search_file(os.path.join(root, "contrato.pdf"), pat)[0][0][2] == "07.202.627/0001-74"
assert B.make_pattern("07.202.627/0001-74").search(B.fold("cnpj 07202627000174"))
assert B.search_file(os.path.join(root, "senha.pdf"), pat)[1] == "protegido por senha"
assert "OCR" in B.search_file(os.path.join(root, "digitalizado.pdf"), pat)[1]
assert len(B.list_pdfs(root)) == 5 and len(B.list_pdfs(root, recursive=False)) == 4

# na janela
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
w = MainWindow(); w.show()
dlg = w.tool_search_folder()
dlg.folder.setText(root); dlg.query.setText("07202627000174")
dlg.start()
t0 = time.time()
while dlg.worker.isRunning() and time.time() - t0 < 30:
    app.processEvents(); time.sleep(0.02)
app.processEvents()
assert dlg.tree.topLevelItemCount() == 2, dlg.status.text()
assert "2 resultado(s) em 2 arquivo(s)" in dlg.status.text() and "protegido" in dlg.status.text(), dlg.status.text()
first = dlg.tree.topLevelItem(0).child(0)
dlg._open(first)
for _ in range(10): app.processEvents()
tab = w.cur()
assert tab and tab.path and tab.path.endswith(("contrato.pdf", "ficha.pdf")), tab
assert tab.view.hit_list, "o trecho achado fica destacado"
dlg.close()
while len(w.tab_widgets) > 1:
    w.close_tab(len(w.tab_widgets) - 1)
print("busca em pasta ok")
