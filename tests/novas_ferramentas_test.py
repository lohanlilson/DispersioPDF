"""Páginas em branco, endireitar, extrair imagens e PDF/A (pelas ferramentas do programa)."""
import io, os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
app = QApplication.instance() or QApplication([])
from dispersio import ops, pdfa, resource
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes if "Abrir" not in str(a[2] if len(a) > 2 else "") else QMessageBox.No)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
tmp = tempfile.mkdtemp()
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: tmp)
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(tmp, "saida_PDFA.pdf"), ""))

im = Image.new("L", (1240, 1754), 245); dr = ImageDraw.Draw(im)
f = ImageFont.truetype(resource("assets", "fontes", "LiberationSerif-Regular.ttf"), 30)
for k in range(30):
    dr.text((120, 150 + k * 48), "Cláusula %d. O cedente transfere ao cessionário os créditos." % (k + 1), fill=20, font=f)
d = pymupdf.open()
for img in (im.rotate(-2.5, resample=Image.BICUBIC, fillcolor=245), Image.new("L", (1240, 1754), 247)):
    b = io.BytesIO(); img.save(b, "JPEG", quality=85)
    p = d.new_page(); p.insert_image(p.rect, stream=b.getvalue())
p = d.new_page(); p.insert_text((72, 72), "Página com texto em Helvetica", fontname="helv")
w = MainWindow(); w.show()
t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
for _ in range(5): app.processEvents()
w.tool_remove_blank(t)
assert t.doc.page_count == 2, t.doc.page_count
w.tool_deskew(t)
import time as _t
_end = _t.time() + 120
while (w._worker.isRunning() or abs(ops.skew_angle(t.doc[0])) > 0.3) and _t.time() < _end:   # roda em segundo plano
    app.processEvents(); _t.sleep(0.02)
assert abs(ops.skew_angle(t.doc[0])) < 0.3, ops.skew_angle(t.doc[0])
t.undo(); assert abs(ops.skew_angle(t.doc[0])) > 2
t.redo()
w.tool_extract_images(t)
assert len([x for x in os.listdir(tmp) if x.endswith(".jpeg") or x.endswith(".jpg") or x.endswith(".png")]) >= 1
w.tool_pdfa(t)
out = os.path.join(tmp, "saida_PDFA.pdf")
od = pymupdf.open(out)
assert "pdfaid:part>2" in od.get_xml_metadata() and od.page_count == 2
for x in range(1, od.xref_length()):
    o = od.xref_object(x)
    import re
    if re.search(r"/Type\s*/Font\b(?!Descriptor)", o) and od.xref_get_key(x, "Subtype")[1] in ("/Type1", "/TrueType"):
        fd = od.xref_get_key(x, "FontDescriptor")
        assert fd[0] == "xref" and any(od.xref_get_key(int(fd[1].split()[0]), k)[0] != "null" for k in ("FontFile", "FontFile2", "FontFile3")), o
print("páginas em branco, endireitar, imagens e PDF/A ok")
