"""Cópia de segurança: salvar por cima guarda a versão anterior, e dá para restaurá-la."""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
app.setApplicationName("DispersioPDF-teste")
from dispersio import backups, dialogs
from dispersio.mainwindow import MainWindow

tmp = tempfile.mkdtemp()
fn = os.path.join(tmp, "contrato.pdf")
d = pymupdf.open(); d.new_page().insert_text((72, 72), "VERSAO ORIGINAL"); d.save(fn)
w = MainWindow(); w.show()
w.open_path(fn)
for _ in range(10): app.processEvents()
t = w.cur()
pg = t.doc[0]; pg.insert_text((72, 120), "ALTERACAO 1"); t.changed([0])
assert t.save()
vs = backups.versions(fn)
assert len(vs) == 1, vs
assert "VERSAO ORIGINAL" in pymupdf.open(vs[0][0])[0].get_text() and "ALTERACAO" not in pymupdf.open(vs[0][0])[0].get_text()
# restaurar pela janela
dialogs.VersionsDialog.exec = lambda self: (self._pick("restaurar"), 1)[1]
w.show_versions()
assert "ALTERACAO" not in t.doc[0].get_text() and t.modified
t.undo()
assert "ALTERACAO 1" in t.doc[0].get_text(), "desfazer a restauração"
# limite de versões
for k in range(14):
    t.doc[0].insert_text((72, 150 + k), "."); t.changed([0]); t.save()
assert len(backups.versions(fn)) == backups.KEEP
print("versões anteriores ok", backups.base_dir())
