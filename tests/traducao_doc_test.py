"""Tradução de artigo: ordem das colunas, citações fora da tradução, referências/cabeçalhos/números de página intactos,
parágrafo que continua na outra coluna, tradução no próprio documento (Original/Tradução), leitura e trecho selecionado."""
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from lumenpdf import traducao as T

if not T._installed("en", "pt"):
    T.download(("en", "pt"))
PATH = [("en", "pt")]

def article():
    d = pymupdf.open()
    for n in range(2):
        p = d.new_page()                      # 595 x 842
        p.insert_text((50, 30), "Journal of Veterinary Forensics 2021; 12: 34-40", fontsize=8)
        p.insert_text((290, 820), str(n + 1), fontsize=8)
        if n == 0:
            p.insert_text((50, 70), "Animal cruelty and family violence", fontsize=16, fontname="hebo")
            left = ("Animal cruelty is a significant indicator of interpersonal violence [12, 15]. Veterinarians should "
                    "document injuries carefully (Arkow et al., 2011). In this study we examined the records of 120 dogs that were")
            right = ("brought to the clinic between 2015 and 2019. Most animals presented fractures and burns. "
                     "The results suggest that early reporting reduces mortality.")
            p.insert_textbox(pymupdf.Rect(50, 90, 285, 140), "Dogs with chronic lesions were more frequent in rural areas.", fontsize=10)
            p.insert_textbox(pymupdf.Rect(50, 150, 285, 300), left, fontsize=10)
            p.insert_textbox(pymupdf.Rect(310, 90, 545, 300), right, fontsize=10)
            # número sobrescrito grudado na palavra
            p.insert_text((310, 330), "Neglect was common", fontsize=10)
            p.insert_text((310 + pymupdf.get_text_length("Neglect was common", fontsize=10), 326), "3", fontsize=6)
            p.insert_text((310 + pymupdf.get_text_length("Neglect was common", fontsize=10) + 4, 330), " in all regions studied.", fontsize=10)
            p.insert_textbox(pymupdf.Rect(310, 345, 545, 420), "Owners rarely sought veterinary care for injured animals.", fontsize=10)
        else:
            p.insert_textbox(pymupdf.Rect(50, 80, 545, 140), "Conclusions: cruelty must be reported to the authorities.", fontsize=10)
            p.insert_text((50, 170), "References", fontsize=12, fontname="hebo")
            p.insert_textbox(pymupdf.Rect(50, 180, 545, 260), "1. Arkow P. The relationships between animal abuse and other forms of family violence. "
                                                              "Family Violence & Sexual Assault Bulletin. 1996;12:29-34.", fontsize=9)
    return d

doc = article()
per = T.analyze(doc)
for p, bl in per.items():
    for b in bl:
        print(p, "KEEP" if b.keep else "    ", "CONT" if b.cont else "    ", b.why.ljust(16), b.shown[:70])
txt0 = [b.shown for b in per[0]]
i_left = next(i for i, t in enumerate(txt0) if t.startswith("Animal cruelty is"))
i_right = next(i for i, t in enumerate(txt0) if t.startswith("brought to the clinic"))
i_rural = next(i for i, t in enumerate(txt0) if t.startswith("Dogs with chronic"))
assert i_rural < i_left < i_right, "coluna da esquerda inteira antes da direita"
assert next(b for b in per[0] if b.shown.startswith("brought")).cont, "parágrafo continua na outra coluna"
assert all(b.keep for b in per[0] + per[1] if b.shown.startswith("Journal of") or b.shown in ("1", "2")), "cabeçalho e número da página"
assert next(b for b in per[1] if b.shown.startswith("1. Arkow")).keep, "referências não se traduzem"
assert any("³" in b.shown for b in per[0]), [b.shown for b in per[0]]

res = {}
T.translate_document(doc, PATH, "pt", lambda p, items: res.__setitem__(p, items))
assert sorted(res) == [0, 1]
tr = lambda pre: next(t for b, t in res[0] if b.shown.startswith(pre))  # noqa: E731
left_t, right_t = tr("Animal cruelty is a"), tr("brought to the clinic")
print(left_t, "|", right_t)
assert "[12, 15]" in left_t and "(Arkow et al., 2011)" in left_t
assert left_t.index("[12, 15]") < left_t.index("Os veterinários") if "Os veterinários" in left_t else True
assert "120" in left_t and "clínica" in (left_t + right_t).lower()
neg = tr("Neglect")
assert "³" in neg and "" not in neg, neg
assert next(t for b, t in res[1] if b.shown.startswith("1. Arkow")) is None

# --- interface
from PySide6.QtWidgets import QApplication, QFileDialog
app = QApplication.instance() or QApplication([])
app.setApplicationName("LumenPDF-teste")
from lumenpdf.config import cfg
from lumenpdf.doctab import DocTab
from lumenpdf.mainwindow import MainWindow
from lumenpdf import artigos_ui
DocTab.AUTOSAVE_MS = 10 ** 8
cfg.set("translate_to", "pt"); cfg.set("offer_translation", True)
tmp = tempfile.mkdtemp()
fn = os.path.join(tmp, "artigo.pdf"); doc.save(fn)
w = MainWindow(); w.show(); w.open_path(fn); t = w.cur()
assert t.translate_bar.isVisible() and "inglês" in t.translate_bar.text.text()
w.run_tool("translate")
end = time.time() + 120
while (t.tr is None or t.tr["running"]) and time.time() < end:
    app.processEvents(); time.sleep(0.03)
assert t.tr and not t.tr["running"] and len(t.tr["pages"]) == 2
assert t.showing_translation() and not t.view.isVisible()
assert "Traduzido" in t.translate_bar.text.text() and t.translate_bar.trad.isChecked()
txt = t.tr_view.doc[0].get_text()
assert "crueldade" in txt.lower() and "Journal of Veterinary Forensics" in txt, txt[:300]
assert "Animal cruelty is a significant" not in txt
t.translate_bar.orig.click(); assert not t.showing_translation() and t.view.isVisible()
assert "Animal cruelty is a significant" in t.doc[0].get_text(), "o original não muda"
t.translate_bar.trad.click(); assert t.showing_translation()
t.set_mode("highlight"); assert not t.showing_translation(), "editar volta ao original"
t.open_reading()
rw = w.findChildren(artigos_ui.TranslateWindow)[-1]
for m in range(4):
    rw.mode.button(m).setChecked(True); app.processEvents()
    h = rw.view.toPlainText()
    assert "Página 1" in h and "Journal of" not in h
    if m in (0, 2, 3):
        assert "crueldade" in h.lower()
    if m in (1, 2, 3):
        assert "Animal cruelty is" in h
rw.close()
fn2 = os.path.join(tmp, "traduzido.pdf")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (fn2, ""))
t.save_translation(); assert "crueldade" in pymupdf.open(fn2)[0].get_text().lower()
t.translate_selection("The results suggest that early reporting reduces mortality.")
pop = w.findChildren(artigos_ui.SelectionTranslation)[-1]
end = time.time() + 30
while pop.out.toPlainText() == "Traduzindo…" and time.time() < end:
    app.processEvents(); time.sleep(0.03)
print(pop.out.toPlainText())
assert "mortalidade" in pop.out.toPlainText()
print("tradução de artigo ok")
