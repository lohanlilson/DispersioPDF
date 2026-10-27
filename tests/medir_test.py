"""Medir, localizar e substituir, links, captura, imagens e comentários em FDF (computador)."""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QInputDialog
app = QApplication.instance() or QApplication([])
from dispersio import ops, dialogs
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab

tmp = tempfile.mkdtemp()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
png = os.path.join(tmp, "novo.png")
pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 30), 0).save(png)

d = pymupdf.open(); p = d.new_page()
p.insert_text((72, 100), "Cedente: ", fontname="helv", fontsize=12)
p.insert_text((125, 100), "FULANO DE TAL", fontname="hebo", fontsize=12, color=(0.8, 0, 0))
p.insert_text((225, 100), " - CPF 111.222.333-44", fontname="helv", fontsize=12)
p.insert_text((72, 130), "Assina FULANO DE TAL. Site www.exemplo.com.br", fontname="tiro", fontsize=11)
p.insert_image(pymupdf.Rect(300, 300, 400, 380), pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 60), 0))
w = MainWindow(); w.show()
t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
for _ in range(5): app.processEvents()
v = t.view

# localizar e substituir
dialogs.ReplaceDialog.exec = lambda self: (self.find.setText("fulano de tal"), self.repl.setText("BELTRANO DA SILVA"), 1)[2]
w.tool_find_replace(t)
txt = t.doc[0].get_text()
assert "FULANO" not in txt and txt.count("BELTRANO DA SILVA") == 2, txt
sp = [s for b in t.doc[0].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if "BELTRANO" in s["text"]]
assert any("Bold" in s["font"] and s["color"] == 0xcc0000 for s in sp), sp
cpf = [s for b in t.doc[0].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if "CPF" in s["text"]][0]
bel = [s for s in sp if "Bold" in s["font"]][0]
assert cpf["bbox"][0] >= bel["bbox"][2] - 1, (cpf["bbox"], bel["bbox"])
print("substituir ok")

# links
w.tool_autolink(t)
assert any(l.get("uri", "").startswith("https://www.exemplo") for l in t.doc[0].get_links())
print("links ok")

# medir: escala 1:100 em m; linha de 72 pt (1 polegada = 2,54 cm no papel → 2,54 m)
dialogs.ScaleDialog.exec = lambda self: (self.n.setValue(100), self.unit.setCurrentText("m"), self._ok())[2] or 1
w.tool_measure_scale(t)
pg = pymupdf.Point
v.set_mode("measure")
v._finish_drag(0, "measure", pymupdf.Rect(100, 400, 172, 400), pg(100, 400), pg(172, 400))
m = [a.info["content"] for a in t.doc[0].annots() if a.info.get("subject") == "Medida" and a.type[1] == "Line"]
assert m and "2,54 m" in m[0], m
# área: quadrado de 72×72 pt → 2,54 × 2,54 = 6,45 m²
v.set_mode("measure_area")
v._poly = [0, [pg(100, 450), pg(172, 450), pg(172, 522), pg(100, 522)]]
v.finish_area()
ar = [a.info["content"] for a in t.doc[0].annots() if a.type[1] == "Polygon"]
assert ar and "6,45 m²" in ar[0], ar
# calibrar: linha de 50 pt = 5 m
QInputDialog.getText = staticmethod(lambda *a, **k: ("5 m", True))
w.tool_measure_calibrate(t, length_pt=50)
assert abs(v.measure_value([pg(0, 0), pg(100, 0)]) - 10) < 0.01
print("medidas ok")

# captura de área
w.tool_rect_snapshot(t, page=0, rect=pymupdf.Rect(60, 80, 300, 140))
assert not QApplication.clipboard().image().isNull()
print("captura ok")

# imagens: mover, trocar, excluir
v.set_mode("image_edit")
v._press_image(0, pg(350, 340))
assert v._img_sel, "imagem não selecionada"
v._apply_image_move(pymupdf.Rect(50, 600, 150, 680))
info = t.doc[0].get_image_info(xrefs=True)
assert any(abs(i["bbox"][0] - 50) < 1 and abs(i["bbox"][1] - 600) < 1 for i in info), info
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (png, ""))
v.replace_selected_image()
xr = v._img_sel[1]
assert t.doc.extract_image(xr)["width"] == 50
v.delete_selected_image()
print("imagens ok")

# comentários em FDF: exporta deste e importa num documento novo
fdf = os.path.join(tmp, "c.fdf")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (fdf, ""))
w.tool_export_comments(t)
t2 = DocTab(pymupdf.open().tobytes() if False else d.tobytes(), None, None, w.settings); w.add_tab(t2)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (fdf, ""))
n0 = len(list(t2.doc[0].annots()))
w.tool_import_comments(t2)
n1 = len(list(t2.doc[0].annots()))
assert n1 - n0 == len([a for a in t.doc[0].annots() if a.type[1] not in ("Popup", "Link", "Widget")]), (n0, n1)
print("FDF ok")
