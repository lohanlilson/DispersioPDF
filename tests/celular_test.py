"""Continuar no celular: o servidor temporário entrega o documento e a página, recebe o do celular e exige o código."""
import os, sys, json, urllib.request, urllib.error, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio import celular
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
w = MainWindow(); w.show()
d = pymupdf.open()
for i in range(5):
    d.new_page().insert_text((72, 72), f"Página {i + 1}")
t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
for _ in range(5): app.processEvents()
t.view.goto(3)
for _ in range(5): app.processEvents()
dlg = w.tool_phone(t)
url = dlg.link.url.replace(celular.lan_ip(), "127.0.0.1")
info = json.load(urllib.request.urlopen(url + "/info", timeout=5))
assert info["has_doc"] and info["page"] == 3, info
pdf = urllib.request.urlopen(url + "/doc.pdf", timeout=5).read()
assert pymupdf.open(stream=pdf, filetype="pdf").page_count == 5
assert b"Baixar" in urllib.request.urlopen(url + "/", timeout=5).read()
try:
    urllib.request.urlopen(url.rsplit("/", 1)[0] + "/errado/doc.pdf", timeout=5)
    raise AssertionError("sem o código não pode baixar")
except urllib.error.HTTPError as e:
    assert e.code == 404
# o celular manda um documento
up = pymupdf.open(); [up.new_page() for _ in range(7)]
req = urllib.request.Request(url + "/upload?name=Do%20celular.pdf&page=6", data=up.tobytes(), method="POST")
assert json.load(urllib.request.urlopen(req, timeout=5))["ok"]
t0 = time.time()
while time.time() - t0 < 5 and not (w.cur() and w.cur().path and w.cur().path.endswith(".pdf") and w.cur() is not t):
    app.processEvents(); time.sleep(0.02)
got = w.cur()
assert got is not t and got.doc.page_count == 7 and got.view.current_page() == 6, (got, got.view.current_page())
dlg.reject()
try:
    urllib.request.urlopen(url + "/info", timeout=2)
    raise AssertionError("fechou a janela: o servidor para")
except (urllib.error.URLError, ConnectionError, OSError):
    pass
while len(w.tab_widgets) > 1:
    w.close_tab(len(w.tab_widgets) - 1)
print("celular ok")
