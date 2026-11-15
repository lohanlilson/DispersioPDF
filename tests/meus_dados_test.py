"""Meus dados: casa rótulos com os dados, cria campos nas linhas em branco e preenche."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio import meus_dados as md
from dispersio.config import cfg
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab

assert md.match("Nome completo:") == "nome" and md.match("Nome da mãe") is None
assert md.match("Estado civil") == "estadocivil" and md.match("CPF/MF nº") == "cpf" and md.match("Data") == "hoje"
assert md.match("", "txtEnderecoCompleto") == "endereco"

old = md.load()
md.save({"nome": "Fulano de Tal", "cpf": "111.222.333-44", "cidade": "Goiânia", "email": "f@x.com"})
try:
    d = pymupdf.open(); p = d.new_page()
    p.insert_text((72, 100), "Nome: ______________________________", fontsize=11)
    p.insert_text((72, 140), "CPF: ______________________", fontsize=11)
    p.insert_text((72, 180), "Nome da mãe: ______________________", fontsize=11)
    p.insert_text((72, 220), "Cidade: ____________________", fontsize=11)
    QDialog.exec = lambda self: 1
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
    w = MainWindow(); w.show()
    t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
    w.tool_autofill(t)
    vals = {wd.field_value for pg in t.doc for wd in pg.widgets() if wd.field_value}
    assert {"Fulano de Tal", "111.222.333-44", "Goiânia"} <= vals, vals
    assert sum(1 for pg in t.doc for wd in pg.widgets() if wd.field_value == "Fulano de Tal") == 1, "nome da mãe fica vazio"
    t.undo()
    assert not any(pg.first_widget for pg in t.doc), "Ctrl+Z desfaz tudo (campos e preenchimento)"
    while len(w.tab_widgets) > 1:
        w.close_tab(len(w.tab_widgets) - 1)
finally:
    md.save(old)
print("meus dados ok")
