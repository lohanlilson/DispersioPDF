"""Impressão: se o driver recusar começar o trabalho, tenta de novo com menos exigências; se não der, explica."""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtPrintSupport import QPrinter
app = QApplication.instance() or QApplication([])
from dispersio import print_manager as pm
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab

tmp = tempfile.mkdtemp()
out = os.path.join(tmp, "saida.pdf")

class FakeInfo:
    def printerName(self): return "Impressora de teste"
    def isNull(self): return False

class fake_printer(QPrinter):
    def __init__(self, info=None, mode=QPrinter.HighResolution):
        super().__init__(mode)
        self.setOutputFormat(QPrinter.PdfFormat)
        self.setOutputFileName(out)

fails = [0]
RealPainter = pm.QPainter
class FlakyPainter(RealPainter):
    def begin(self, dev):
        if fails[0] > 0:
            fails[0] -= 1
            return False
        return super().begin(dev)

pm.QPrinter = fake_printer
pm.QPainter = FlakyPainter
pm.printer_problem = lambda name: "Ela está desligada ou desconectada (offline)."

w = MainWindow(); w.show()
d = pymupdf.open()
for i in range(3):
    d.new_page().insert_text((72, 72), f"Página {i + 1}")
t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
for _ in range(5): app.processEvents()

def run(n_fail):
    fails[0] = n_fail
    if os.path.exists(out): os.remove(out)
    dlg = pm.PrintManager(w, w.open_tab_sources()[-1:], "teste")
    dlg._info = lambda: FakeInfo()
    dlg._rebuild()
    o, orientation, paper, area = dlg._geom
    dlg._print(o, orientation, area)
    return dlg

dlg = run(0); n = pymupdf.open(out).page_count; assert n == len(dlg.sheets) > 0, (n, len(dlg.sheets))
run(2); assert pymupdf.open(out).page_count == n, "driver recusou duas vezes: terceira tentativa imprime"
try:
    run(3)
    raise AssertionError("deveria falhar")
except RuntimeError as e:
    assert "Impressora de teste" in str(e) and "offline" in str(e), str(e)
print("impressão com nova tentativa ok")
