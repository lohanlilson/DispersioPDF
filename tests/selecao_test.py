"""Seleção em tabela: arrastar dentro de uma coluna pega só a coluna; texto corrido continua igual."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from dispersio.viewer import PdfView

d = pymupdf.open(); p = d.new_page(width=660, height=300)
rows = [("26/08/2026", ["COOPERATIVA CENTRAL DE CREDITO", "E ECONOMIA COM INTERACAO", "SOLIDARIA CRESOL CENTRAL BRASIL"], "07202627000174"),
        ("25/08/2026", ["SEJA CREDITO E COBRANCA LTDA"], "30527936000136"), ("21/08/2026", ["BANCO VOTORANTIM S.A."], "59588111000103")]
y = 80
for dt, name, cn in rows:
    h = len(name) * 14
    p.insert_text((28, y + h / 2), dt, fontsize=9)
    for k, l in enumerate(name):
        p.insert_text((235, y + 10 + k * 14), l, fontsize=9)
    p.insert_text((442, y + h / 2), cn, fontsize=9)
    y += h + 12
v = PdfView(); v.set_document(d)
ws = v.words(0)
ix = {w[1]: k for k, w in reversed(list(enumerate(ws)))}
v.set_selection(0, ix["COOPERATIVA"], ix["BRASIL"])
assert v.selected_text() == "COOPERATIVA CENTRAL DE CREDITO\nE ECONOMIA COM INTERACAO\nSOLIDARIA CRESOL CENTRAL BRASIL", v.selected_text()
assert len(v.sel_rects[0]) == 3, "só as três linhas da coluna ficam destacadas"
v.set_selection(0, ix["COOPERATIVA"], ix["VOTORANTIM"])
assert "26/08" not in v.selected_text() and "0720" not in v.selected_text() and "SEJA CREDITO" in v.selected_text()

d2 = pymupdf.open(); p2 = d2.new_page()
p2.insert_textbox(pymupdf.Rect(72, 72, 520, 400), "Lorem ipsum dolor sit amet consectetur adipiscing elit. " * 12, fontsize=11)
v.set_document(d2)
v.set_selection(0, 5, 60)
assert len(v.selected_text().split()) == 56, "texto corrido: nada some"
print("seleção em colunas ok")
