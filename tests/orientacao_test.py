"""Endireitar páginas de lado ou de cabeça para baixo (texto digital e digitalizado)."""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PIL import Image
from lumenpdf import ops

TXT = ["CONTRATO DE CESSÃO DE CRÉDITOS", "Pelo presente instrumento particular, de um lado a cedente,",
       "empresa com sede nesta capital, e de outro lado a cessionária, têm entre si", "justo e contratado o seguinte:",
       "Cláusula primeira. A cedente transfere à cessionária os créditos", "descritos no anexo deste contrato, com todos os direitos",
       "e garantias, pelo preço certo e ajustado entre as partes.", "Cláusula segunda. O pagamento será feito por transferência",
       "bancária na data da assinatura deste instrumento, servindo", "o comprovante como recibo de quitação plena e irrevogável."]


def text_page(doc):
    p = doc.new_page()
    for k, t in enumerate(TXT * 2):
        p.insert_text((60, 90 + 18 * k), t, fontsize=12)
    return p


def scanned(doc, angle):
    """Página "escaneada": imagem do texto girada (a imagem fica de lado/de cabeça para baixo)."""
    src = pymupdf.open(); text_page(src)
    pix = src[0].get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples).rotate(angle, expand=True, fillcolor=255)
    b = io.BytesIO(); im.save(b, "PNG")
    w, h = (595, 842) if im.width < im.height else (842, 595)
    p = doc.new_page(width=w, height=h)
    p.insert_image(p.rect, stream=b.getvalue())
    return p


doc = pymupdf.open()
text_page(doc)                                       # 0: certa
p = text_page(doc); p.set_rotation(180)              # 1: texto digital de cabeça para baixo
p = text_page(doc); p.set_rotation(90)               # 2: texto digital de lado
scanned(doc, 0)                                      # 3: escaneada certa
scanned(doc, 180)                                    # 4: escaneada de cabeça para baixo
scanned(doc, 90)                                     # 5: escaneada de lado (girada 90° anti-horário)
scanned(doc, -90)                                    # 6: escaneada de lado (horário)
p = scanned(doc, 90); p.set_rotation(90)             # 7: escaneada de lado, mas já corrigida pela rotação da página
doc.new_page()                                       # 8: em branco
fixes = ops.orientation_fixes(doc)
print(fixes)
assert fixes == {1: 0, 2: 0, 4: 180, 5: 90, 6: 270}, fixes
ops.apply_orientation(doc, fixes)
assert ops.orientation_fixes(doc) == {}, "depois de corrigir, nada mais a fazer"
print("orientação ok")

# --- interface: aviso ao abrir, botão Endireitar (com desfazer) e ferramenta
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile, time
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
app.setApplicationName("LumenPDF-teste")
from lumenpdf.config import cfg
from lumenpdf.doctab import DocTab
from lumenpdf.mainwindow import MainWindow
cfg.set("detect_orientation", True)
DocTab.AUTOSAVE_MS = 10 ** 8
d = pymupdf.open(); text_page(d); scanned(d, 180); p = text_page(d); p.set_rotation(90)
fn = os.path.join(tempfile.mkdtemp(), "torto.pdf"); d.save(fn)
w = MainWindow(); w.show(); w.open_path(fn); t = w.cur()
end = time.time() + 60
while not t.orient_bar.isVisible() and time.time() < end:
    app.processEvents(); time.sleep(0.02)
assert t.orient_bar.isVisible() and set(t.orient_bar.fixes) == {1, 2}, t.orient_bar.fixes
t.orient_bar._apply()
assert [pg.rotation for pg in t.doc] == [0, 180, 0] and t.modified
t.undo()
assert [pg.rotation for pg in t.doc] == [0, 0, 90]
# ferramenta Endireitar (com o OCR) faz o mesmo
done = []
QMessageBox.information = staticmethod(lambda *a, **k: done.append(a[2]))
w.run_tool("deskew")
end = time.time() + 60
while [pg.rotation for pg in t.doc] != [0, 180, 0] and time.time() < end:
    app.processEvents(); time.sleep(0.02)
assert [pg.rotation for pg in t.doc] == [0, 180, 0], [pg.rotation for pg in t.doc]
print("interface de orientação ok")
