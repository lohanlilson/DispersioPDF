"""Quadrinhos e livros: CBZ (ordem natural, mangá pelo ComicInfo), CBR que é ZIP, EPUB, modos, capítulos, posição."""
import os, sys, io, zipfile, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio import quadrinhos as hq
from dispersio.config import cfg

root = tempfile.mkdtemp()
serie = os.path.join(root, "Minha Serie"); os.makedirs(serie)

def img(w, h, color, fmt="JPEG"):
    b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, fmt); return b.getvalue()

def cbz(path, pages, manga=False, fmt="JPEG"):
    with zipfile.ZipFile(path, "w") as z:
        for i, (w, h) in enumerate(pages, 1):
            z.writestr(f"pag{i}.{ 'jpg' if fmt == 'JPEG' else fmt.lower()}", img(w, h, (i * 20 % 255, 80, 120), fmt))
        z.writestr("__MACOSX/._lixo.jpg", b"x")
        if manga:
            z.writestr("ComicInfo.xml", "<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>")

for n in (1, 2, 10):
    cbz(os.path.join(serie, f"Capitulo {n}.cbz"), [(800, 1200)] * 3 + [(800, 1200)] * (n == 2) * 9, manga=True)
web = os.path.join(root, "webtoon.cbz"); cbz(web, [(720, 3000)] * 4)
webp = os.path.join(root, "webp.cbz"); cbz(webp, [(600, 900)] * 2, fmt="WEBP")
cbr = os.path.join(root, "disfarçado.cbr"); cbz(cbr, [(600, 900)] * 2)

# ordem natural e conversão sem recomprimir
assert [os.path.basename(p) for p in hq.siblings(os.path.join(serie, "Capitulo 2.cbz"))] == ["Capitulo 1.cbz", "Capitulo 2.cbz", "Capitulo 10.cbz"]
assert hq.neighbor(os.path.join(serie, "Capitulo 2.cbz"), 1).endswith("Capitulo 10.cbz")
data, info = hq.comic_to_pdf(os.path.join(serie, "Capitulo 2.cbz"))
d = pymupdf.open(stream=data, filetype="pdf")
assert d.page_count == 12 and info["rtl"] and not info["webtoon"], info
assert d[0].get_images()[0][8] == "DCTDecode", "JPEG entra como está"
assert hq.comic_to_pdf(web)[1]["webtoon"]
assert pymupdf.open(stream=hq.comic_to_pdf(webp)[0], filetype="pdf").page_count == 2, "WebP"
assert hq.is_comic(cbr) and hq.comic_to_pdf(cbr)[1]["pages"] == 2, "CBR que é ZIP"

# CBT (tar): passa pelo mesmo caminho do CBR/RAR no Windows (tar.exe/libarchive)
import tarfile
cbt = os.path.join(root, "capitulo.cbt")
with tarfile.open(cbt, "w") as tf:
    for i in (1, 2, 10):
        b = img(500, 700, (i, i, i)); ti = tarfile.TarInfo(f"p{i}.jpg"); ti.size = len(b); tf.addfile(ti, io.BytesIO(b))
cd, ci = hq.comic_to_pdf(cbt)
assert ci["pages"] == 3

# EPUB mínimo
ep = os.path.join(root, "livro.epub")
with zipfile.ZipFile(ep, "w") as z:
    z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/c.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    z.writestr("OEBPS/c.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Livro</dc:title><dc:identifier id="id">1</dc:identifier></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>')
    z.writestr("OEBPS/c1.xhtml", '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Capítulo um</h1>' + "<p>Era uma vez um leitor de PDF.</p>" * 200 + "</body></html>")
bd = pymupdf.open(stream=hq.book_to_pdf(ep), filetype="pdf")
assert bd.page_count > 3 and "Capítulo um" in bd[0].get_text()

# na janela
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
from dispersio.mainwindow import MainWindow
w = MainWindow(); w.resize(1200, 800); w.show()
ch2 = os.path.join(serie, "Capitulo 2.cbz")
cfg.qs.remove(hq.pos_key(ch2)); cfg.qs.remove("hq_modo/" + os.path.normcase(serie))
w.open_path(ch2)
for _ in range(10): app.processEvents()
t = w.cur()
assert t.source_path == os.path.abspath(ch2) and not t.modified and t.path is None
assert t.comic_mode == "manga" and t.view.rtl, "ComicInfo diz mangá"
t.view.goto(7)
for _ in range(5): app.processEvents()
from dispersio.quadrinhos_ui import set_mode
set_mode(t, "webtoon")
assert t.view.page_gap == 0 and t.view.zoom_mode == "fit_width"
assert t.view.current_page() == 7, "trocar de modo mantém a página"
# próximo capítulo: abre o 10 no mesmo modo e fecha o 2
t.comic_bar.chapter(1)
for _ in range(10): app.processEvents()
t2 = w.cur()
assert t2.source_path.endswith("Capitulo 10.cbz") and t2.comic_mode == "webtoon", (t2.source_path, t2.comic_mode)
assert t not in w.tab_widgets, "o capítulo anterior fecha"
# reabrir o 2: volta na página 8 e no modo da série (webtoon)
w.open_path(ch2)
for _ in range(10): app.processEvents()
t3 = w.cur()
assert t3.view.current_page() == 7 and t3.comic_mode == "webtoon", (t3.view.current_page(), t3.comic_mode)
w.open_path(ep)
for _ in range(5): app.processEvents()
assert w.cur().source_path.endswith("livro.epub") and not hasattr(w.cur(), "comic_bar")
# biblioteca
from dispersio import biblioteca as bib
ser = bib.scan(root)
names = [n for _i, n, _c in ser]
assert "Minha Serie" in names, names
sid_, _n, chs = next(x for x in ser if x[1] == "Minha Serie")
assert [os.path.basename(c) for c in chs] == ["Capitulo 1.cbz", "Capitulo 2.cbz", "Capitulo 10.cbz"]
assert bib.chapter_progress(chs[1]) is not None and bib.resume_index(chs) == 0
bib.mark_read(chs[0])
assert bib.chapter_progress(chs[0]) == 1.0 and bib.resume_index(chs) == 1
assert bib.tag(sid_, chs) == "lendo"
assert bib.cover_bytes(chs[0])[:2] == b"\xff\xd8", "capa = primeira imagem (JPEG)"
cfg.qs.setValue("biblioteca/pasta", root)
dlg = w.tool_library()
for _ in range(20): app.processEvents()
assert dlg.grid.count() >= 4
it = next(dlg.grid.item(i) for i in range(dlg.grid.count()) if dlg.grid.item(i).data(0x0100) == sid_)
dlg._open_series(sid_)
assert dlg.chapters.count() == 3 and dlg.cont.text().startswith("Continuar: Capitulo 2")
dlg._continue()
for _ in range(10): app.processEvents()
assert w.cur().source_path.endswith("Capitulo 2.cbz")
dlg.close()
while len(w.tab_widgets) > 1:
    w.close_tab(len(w.tab_widgets) - 1)
print("quadrinhos ok")

# tradução nos balões (OCR em inglês acompanha o programa; o pacote de tradução só se já estiver instalado)
from PIL import ImageDraw, ImageFont
from dispersio import manga_trad as mt, traducao
assert mt.dialog_br("Onde foste ontem à noite?") == "Onde você foi ontem à noite?"
assert mt.dialog_br("Não mintas para mim!") == "Não minta para mim!"
font = None
for cand in ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
    if os.path.exists(cand):
        font = ImageFont.truetype(cand, 26)
if font:
    im = Image.new("RGB", (900, 1300), (170, 170, 180)); dr = ImageDraw.Draw(im)
    def balao(x, y, w_, h_, lines):
        dr.ellipse((x, y, x + w_, y + h_), fill="white", outline="black", width=3)
        ty = y + h_ / 2 - len(lines) * 17
        for l in lines:
            tw = dr.textlength(l, font=font); dr.text((x + w_ / 2 - tw / 2, ty), l, font=font, fill="black"); ty += 34
    balao(60, 80, 420, 240, ["WHERE DID", "YOU GO LAST", "NIGHT?"])
    balao(430, 520, 400, 220, ["I WAS AT", "THE LIBRARY."])
    b = io.BytesIO(); im.save(b, "JPEG", quality=90)
    md = pymupdf.open(); pg = md.new_page(width=900, height=1300); pg.insert_image(pg.rect, stream=b.getvalue())
    bl = mt.balloons(mt._words(pg, "en"))
    assert len(bl) == 2 and "NIGHT" in bl[0][1].upper() and "LIBRARY" in bl[1][1].upper(), bl
    if traducao._installed("en", "pt"):
        assert mt.translate_page(md, 0, "en", [("en", "pt")]) == 2
        txt = md[0].get_text().lower()
        assert "biblioteca" in txt and "você" in txt, txt
print("tradução nos balões ok")
