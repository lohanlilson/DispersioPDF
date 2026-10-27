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
assert [a.title for a in _out] == ["pt 0", "en 0", "pt 1", "en 1", "Comum"] and _n == 3, [a.title for a in _out]
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
cards = dlg.inner.findChildren(artigos_ui.ArticleCard)
assert len(cards) == 1 and dlg.results[0].venue == "Vet Path"
dlg.copy_ref(dlg.results[0]); assert app.clipboard().text().startswith("BEHR, Melissa J.")
dlg.open_article(dlg.results[0])
end = time.time() + 20
while w.cur() is None and time.time() < end:
    app.processEvents(); time.sleep(0.02)
t = w.cur()
assert t and t.path == src
assert t.translate_bar.isVisible() and "inglês" in t.translate_bar.text.text()
w.run_tool("translate")
end = time.time() + 120
while (t.tr is None or t.tr["running"]) and time.time() < end:
    app.processEvents(); time.sleep(0.05)
assert t.tr and t.tr["pages"] and t.showing_translation()
t.open_reading()
tw = w.findChildren(artigos_ui.TranslateWindow)[-1]
html_txt = tw.view.toPlainText()
print(html_txt[:300])
assert "crueldade" in html_txt.lower() and "Página 1" in html_txt
out_fn = os.path.join(tmp, "traduzido.pdf")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_fn, ""))
t.save_translation()
tr = pymupdf.open(out_fn)[0].get_text()
print(tr[:300])
assert "crueldade" in tr.lower() and "cruelty is a significant" not in tr
tw.close()

# --- pesquisa dinâmica: filtros, resumo traduzido, parecidos/citado por/referências, voltar, DOI, sugestões, rolagem
def A(i, **k):
    return artigos.Article(f"Artigo {i}", ["Ana Souza"], 2020, "Rev", language="en", doi=f"https://doi.org/10.1/{i}",
                           pdf_urls=["https://x/a.pdf"], id=f"W{1000 + i}", citations=3, related=["W1", "W2"], refs=["W3"],
                           abstract="Animal cruelty is a significant indicator of interpersonal violence.", **k)
calls = []
def fake_search(q, year_from=None, sort="relevance", page=1, api_key="", lang=None, filters=("pdf",)):
    calls.append((q, sort, page, tuple(filters)))
    return [A(page * 100 + i) for i in range(25)], 60
artigos.search = fake_search
artigos.by_ids = lambda ids, key="", filters=(): [A(900 + n) for n, _ in enumerate(ids)]
artigos.citing = lambda wid, page=1, key="", filters=(), sort="citations": ([A(800)], 1)
artigos.by_key = lambda key, api_key="": A(7, title="Pelo DOI") if False else artigos.Article("Pelo DOI", id="W77")
cfg.set("articles_english", False); cfg.set("articles_filters", "pdf")
d2 = artigos_ui.ArticlesDialog(w); d2.resize(900, 700); d2.show()
d2.en.setChecked(False)
d2.q.setText("crueldade animal"); d2.search()
wait = lambda cond: [app.processEvents() or time.sleep(0.02) for _ in iter(lambda: cond() or time.time() > end, True)]
end = time.time() + 20; wait(lambda: len(d2.results) == 25)
assert len(d2.results) == 25 and calls[-1][3] == ("pdf",)
# rolagem contínua carrega a próxima página
for _ in range(30): app.processEvents(); time.sleep(0.01)
assert d2.area.verticalScrollBar().maximum() > 0
d2.area.verticalScrollBar().setValue(d2.area.verticalScrollBar().maximum())
end = time.time() + 20; wait(lambda: len(d2.results) == 50)
assert len(d2.results) == 50 and calls[-1][2] == 2
# filtro em botão refaz a pesquisa
d2.chips["review"].setChecked(True)
end = time.time() + 20; wait(lambda: calls[-1][3] == ("pdf", "review") and len(d2.results) == 25)
assert calls[-1][3] == ("pdf", "review")
d2.sorts.button(1).click()
end = time.time() + 20; wait(lambda: calls[-1][1] == "citations")
assert calls[-1][1] == "citations"
# resumo traduzido
card = d2.inner.findChildren(artigos_ui.ArticleCard)[0]
card.toggle_abstract()
end = time.time() + 60; wait(lambda: "tradução automática" in card.abs.text())
print(card.abs.text()[:200])
assert "crueldade" in card.abs.text().lower()
# navegar: parecidos → voltar; citado por; referências
end = time.time() + 5; wait(lambda: False)
d2.navigate("related", d2.results[0])
end = time.time() + 20; wait(lambda: d2.results and d2.results[0].title == "Artigo 900")
assert [a.title for a in d2.results] == ["Artigo 900", "Artigo 901"] and d2.back.isVisible()
d2.navigate("refs", d2.results[0])
end = time.time() + 20; wait(lambda: len(d2.results) == 1)
d2.go_back(); app.processEvents()
assert [a.title for a in d2.results] == ["Artigo 900", "Artigo 901"]
d2.go_back(); app.processEvents()
assert len(d2.results) == 25 and not d2.back.isVisible()
d2.navigate("citing", d2.results[0])
end = time.time() + 20; wait(lambda: d2.results and d2.results[0].title == "Artigo 800")
# DOI colado vai direto ao artigo
d2.q.setText("https://doi.org/10.1177/0886260508319362"); d2.search()
end = time.time() + 20; wait(lambda: d2.results and d2.results[0].title == "Pelo DOI")
assert d2.results[0].title == "Pelo DOI"
# sugestões enquanto digita
artigos.autocomplete = lambda t, timeout=6: [("tema", "animal cruelty", "", "animal-cruelty"), ("artigo", "Is Animal Cruelty a Red Flag", "", "W2085928795")]
d2.q.setText("animal cru"); d2._suggest()
end = time.time() + 20; wait(lambda: d2._sugg_model.rowCount() > 0)
assert any("animal cruelty" in x for x in d2._sugg_model.stringList())
# artigos sobre o documento aberto
d2.search_open_document()
end = time.time() + 20; wait(lambda: calls[-1][0] != "crueldade animal")
print("consulta do documento:", d2.q.text())
assert "Animal cruelty" in d2.q.text()
d2.close()
print("artigos e tradução ok")
