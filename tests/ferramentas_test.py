"""Passa por todas as ferramentas do programa (com as janelas respondidas automaticamente) e falha se alguma der erro.
Pega quebras causadas por versões novas das bibliotecas (ex.: PyMuPDF 2)."""
import os, sys, tempfile, traceback, faulthandler
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6 import QtWidgets
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog, QInputDialog, QColorDialog, QMenu
from PySide6.QtGui import QColor
app = QApplication.instance() or QApplication([])
from lumenpdf import mainwindow as mw_mod
from lumenpdf.mainwindow import MainWindow
from lumenpdf.doctab import DocTab
from lumenpdf import ops

tmp = tempfile.mkdtemp()
png = os.path.join(tmp, "img.png")
pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), 0).save(png)
other = os.path.join(tmp, "outro.pdf")
od = pymupdf.open(); od.new_page().insert_text((72, 72), "Outro documento"); od.save(other)
save_n = [0]

def save_name(*a, **k):
    save_n[0] += 1
    flt = (a[3] if len(a) > 3 else k.get("filter", "")) or ""
    ext = ".pdf"
    for e in (".docx", ".xlsx", ".txt", ".png", ".jpg", ".pdf"):
        if e[1:] in flt.lower():
            ext = e
            break
    return os.path.join(tmp, f"saida{save_n[0]}{ext}"), flt

def open_name(*a, **k):
    flt = (a[3] if len(a) > 3 else k.get("filter", "")) or ""
    return (png if "imag" in flt.lower() or "png" in flt.lower() else other), flt

# respostas automáticas
QDialog.exec = lambda self: 1
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"mensagem de erro: {a[2] if len(a) > 2 else k}")))
QMessageBox.exec = lambda self: QMessageBox.Yes
QFileDialog.getSaveFileName = staticmethod(save_name)
QFileDialog.getOpenFileName = staticmethod(open_name)
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([other], ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: tmp)
QInputDialog.getText = staticmethod(lambda *a, **k: ("Texto de teste", True))
QInputDialog_text_for_pages = "x-y"   # intervalo inválido: deve avisar, sem erro
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Texto de teste", True))
QInputDialog.getInt = staticmethod(lambda *a, **k: (1, True))
QInputDialog.getItem = staticmethod(lambda *a, **k: ((a[3][0] if len(a) > 3 and a[3] else ""), True))
QColorDialog.getColor = staticmethod(lambda *a, **k: QColor("#ffeeaa"))
class AutoMenu(QMenu):
    def exec(self, *a, **k):
        acts = [x for x in self.actions() if not x.isSeparator()]
        return acts[0] if acts else None
import lumenpdf.viewer as _vw
_vw.QMenu = AutoMenu

def make():
    d = pymupdf.open()
    for i in range(4):
        p = d.new_page()
        p.insert_text((72, 100), f"Página {i + 1}: contrato de cessão — CPF 111.222.333-44, e-mail a@b.com", fontsize=11)
        p.insert_text((72, 140), "Nome: ______________________   ( ) Sim  ( ) Não", fontsize=11)
        p.insert_text((72, 700), "_____________________________", fontsize=11)
        p.insert_text((72, 715), "Assinatura do Cedente", fontsize=10)
    return d.tobytes()

w = MainWindow(); w.resize(1300, 850); w.show()
errors = []

def fresh():
    t = DocTab(make(), None, None, w.settings); w.add_tab(t)
    for _ in range(5): app.processEvents()
    return t

def run(name, fn):
    faulthandler.dump_traceback_later(40, exit=True)
    try:
        try:
            fn()
        except ops.Cancelled:
            pass
        for _ in range(3): app.processEvents()
        print("ok  ", name)
    except Exception:
        errors.append(name)
        print("ERRO", name); traceback.print_exc(limit=4)
    finally:
        faulthandler.cancel_dump_traceback_later()

t = fresh(); v = t.view
P0, P1 = pymupdf.Point(100, 300), pymupdf.Point(260, 360)
for m in ["rect", "ellipse", "redact", "freetext", "image", "link", "field_text", "field_check", "field_combo",
          "area_highlight", "line", "arrow"]:
    run(f"arrastar: {m}", lambda m=m: (setattr(v, "mode", m), v._finish_drag(0, m, pymupdf.Rect(P0, P1), P0, P1)))
for kind in ("highlight", "underline", "strikeout", "squiggly"):
    def mk(kind=kind):
        v.set_selection(0, 0, 3); v.markup_selection(kind)
    run(f"marcar texto: {kind}", mk)
run("nota", lambda: v._add_note(0, pymupdf.Point(400, 200)))
run("carimbo", lambda: v._add_stamp(0, pymupdf.Point(300, 450)))
run("tarjar seleção", lambda: (v.set_selection(0, 0, 2), v.redact_selection()))
skip = {"print", "print_batch", "read_aloud", "speak", "compare", "certsign", "rect_certsign", "organize",
        "signature", "create_signature", "ocr", "split", "merge", "create_pdf"}
for name in sorted(n[5:] for n in dir(MainWindow) if n.startswith("tool_")):
    if name in skip:
        continue
    kw = {}
    if name == "edit_span":
        kw = dict(page=0, point=pymupdf.Point(120, 96))
    elif name == "add_text_at":
        kw = dict(page=0, point=pymupdf.Point(300, 500))
    elif name.startswith("rect_"):
        kw = dict(page=0, rect=pymupdf.Rect(100, 300, 260, 360))
    tt = fresh()
    run(f"ferramenta: {name}", lambda name=name, kw=kw, tt=tt: getattr(w, "tool_" + name)(tt, **kw))
    w.tabs.removeTab(w.tabs.indexOf(tt)) if hasattr(w, "tabs") else None
print("\n" + (f"{len(errors)} com erro: {errors}" if errors else "todas as ferramentas ok"))
sys.exit(1 if errors else 0)
