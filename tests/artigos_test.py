"""Pesquisa de artigos (OpenAlex/Europe PMC simulados), referência ABNT e tradução offline (leitura e PDF traduzido)."""
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
app = QApplication.instance() or QApplication([])
app.setApplicationName("LumenPDF-teste")
from lumenpdf import artigos, traducao
from lumenpdf.config import cfg
from lumenpdf.doctab import DocTab

DocTab.AUTOSAVE_MS = 10 ** 8
tmp = tempfile.mkdtemp()

# --- OpenAlex: leitura da resposta
OA = {"meta": {"count": 2}, "results": [
    {"display_name": "Veterinary forensics: animal cruelty", "publication_year": 2021, "language": "en", "cited_by_count": 12,
     "doi": "https://doi.org/10.1/abc", "authorships": [{"author": {"display_name": "Melissa J. Behr"}}, {"author": {"display_name": "Ana Souza"}}],
     "primary_location": {"source": {"display_name": "Veterinary Pathology"}},
     "best_oa_location": {"is_oa": True, "pdf_url": "https://x.org/a.pdf", "landing_page_url": "https://x.org/a"},
     "locations": [{"is_oa": True, "pdf_url": "https://repo.org/a.pdf"}], "biblio": {"volume": "58", "issue": "2", "first_page": "10", "last_page": "20"}},
    {"display_name": "Sem PDF", "best_oa_location": {"pdf_url": None}, "locations": []}]}
artigos._get_json = lambda url, timeout=25: OA
arts, n = artigos.search("animal cruelty")
assert len(arts) == 1 and arts[0].pdf_urls == ["https://x.org/a.pdf", "https://repo.org/a.pdf"], arts
ref = arts[0].abnt()
assert ref.startswith("BEHR, Melissa J.; SOUZA, Ana. Veterinary forensics: animal cruelty. Veterinary Pathology, v. 58, n. 2, p. 10-20, 2021. DOI: 10.1/abc."), ref
# OpenAlex fora do ar / limite: usa o Europe PMC
import urllib.error
calls = []
def fake(url, timeout=25):
    calls.append(url)
    if "openalex" in url:
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)
    return {"hitCount": 1, "resultList": {"result": [{"title": "Dog bite injuries.", "authorList": {"author": [{"fullName": "Long K"}]},
            "pubYear": "2024", "journalInfo": {"journal": {"title": "Animals"}, "volume": "14"}, "pmcid": "PMC1", "source": "MED", "id": "9"}]}}
artigos._get_json = fake
arts, n = artigos.search("dog bite")
assert arts[0].source == "Europe PMC" and arts[0].title == "Dog bite injuries" and arts[0].abnt().startswith("LONG, K. Dog bite injuries. Animals, v. 14, 2024.")
# acento faltando não esconde resultados; versões intercaladas sem repetir
assert artigos.restore_accents("maus tratos em CAES") == "maus tratos em CÃES"
assert artigos.variants("maus tratos em caes") == ["maus tratos em caes", "maus tratos em cães"]
assert artigos.variants("maus-tratos em cães") == ["maus-tratos em cães", "maus tratos em caes"]
_s = artigos.search
artigos.search = lambda q, *a, **k: ([artigos.Article(f"{q} {i}", doi=f"10/{q}{i}") for i in range(2)] +
                                     [artigos.Article("Comum", doi="10/x")], 3)
_out, _n = artigos.search_many(["pt", "en"])
assert [a.title for a in _out] == ["pt 0", "en 0", "pt 1", "en 1", "Comum"] and _n == 6, [a.title for a in _out]
artigos.search = _s
assert artigos.safe_name('Cães: "maus-tratos"/abuso?') == "Cães maus-tratos abuso.pdf"

# --- idioma
assert traducao.detect("The results of this study show that the animals were in poor condition and that it was not possible to treat them in the clinic for the first weeks of the year.") == "en"
assert traducao.detect("Os resultados deste estudo mostram que os animais estavam em más condições e que não foi possível tratá-los na clínica nas primeiras semanas do ano.") == "pt"
assert traducao.pt_br("O utilizador registou um facto crónico na equipa.").startswith("O usuário")

# --- tradução offline (baixa o pacote inglês → português na primeira vez)
if not traducao._installed("en", "pt"):
    traducao.download(("en", "pt"))
out = traducao.translate_paragraphs(["Chronic lesions were observed in 12 dogs (Smith et al. 2020).", "12.5 ± 3.1"], [("en", "pt")], "pt")
print(out)
assert "cães" in out[0] and "Smith et al. 2020" in out[0] and out[1] == "12.5 ± 3.1"

# --- interface: pesquisar, baixar e abrir; faixa "Traduzir"; leitura traduzida; PDF traduzido
from lumenpdf.mainwindow import MainWindow
from lumenpdf import artigos_ui
src = os.path.join(tmp, "artigo.pdf")
d = pymupdf.open(); p = d.new_page()
p.insert_text((60, 70), "Animal cruelty and veterinary forensics", fontsize=16, fontname="hebo")
txt = ("Animal cruelty is a significant indicator of interpersonal violence. Veterinarians should document injuries "
       "carefully and report suspected cases to the authorities. The results of this study show that most cases "
       "involved dogs that were kept in poor conditions for a long time.")
p.insert_textbox(pymupdf.Rect(60, 90, 540, 300), txt, fontsize=11)
d.save(src)
artigos.search = lambda *a, **k: ([artigos.Article("Animal cruelty and veterinary forensics", ["Melissa J. Behr"], 2021, "Vet Path",
                                                   language="en", pdf_urls=["https://x.org/a.pdf"])], 1)
artigos.download = lambda a, dest=None, progress=None, cancel=None: src
cfg.set("articles_english", False); cfg.set("offer_translation", True); cfg.set("translate_to", "pt")
w = MainWindow(); w.show()
dlg = artigos_ui.ArticlesDialog(w); dlg.show()
dlg.q.setText("animal cruelty"); dlg.search()
end = time.time() + 20
while not dlg.results and time.time() < end:
    app.processEvents(); time.sleep(0.02)
assert dlg.list.count() == 1 and "Vet Path" in dlg.list.item(0).text()
dlg.copy_ref(); assert app.clipboard().text().startswith("BEHR, Melissa J.")
dlg.open_selected()
end = time.time() + 20
while w.cur() is None and time.time() < end:
    app.processEvents(); time.sleep(0.02)
t = w.cur()
assert t and t.path == src
assert t.translate_bar.isVisible() and "inglês" in t.translate_bar.text.text()
w.run_tool("translate")
tw = [x for x in w.findChildren(artigos_ui.TranslateWindow)][-1]
end = time.time() + 120
while not tw.save_btn.isEnabled() and time.time() < end:
    app.processEvents(); time.sleep(0.05)
assert tw.pages and tw.save_btn.isEnabled()
html_txt = tw.view.toPlainText()
print(html_txt[:300])
assert "crueldade" in html_txt.lower() and "Página 1" in html_txt
out_fn = os.path.join(tmp, "traduzido.pdf")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_fn, ""))
tw.save_pdf()
tr = pymupdf.open(out_fn)[0].get_text()
print(tr[:300])
assert "crueldade" in tr.lower() and "cruelty is a significant" not in tr
tw.close()
print("artigos e tradução ok")
