"""Operações de documento (sem interface). Todas recebem/retornam pymupdf.Document ou caminhos."""
import difflib
import html
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pymupdf

# ---------------------------------------------------------------- utilidades

def parse_ranges(text, page_count):
    """'1-3, 5, 8-' -> [0,1,2,4,7,...] (base 0). Vazio = todas."""
    text = (text or "").strip()
    if not text:
        return list(range(page_count))
    pages = []
    for part in re.split(r"[,;]", text):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else page_count
            step = 1 if b >= a else -1
            pages.extend(range(a - 1, b - 1 + step, step))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < page_count]


def to_unrot(page, rect):
    """Retângulo em coordenadas de exibição -> coordenadas sem rotação (anotações/conteúdo)."""
    return pymupdf.Rect(rect) * page.derotation_matrix


def to_disp(page, rect):
    return pymupdf.Rect(rect) * page.rotation_matrix


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def open_bytes(data, password=None):
    doc = pymupdf.open(stream=data, filetype="pdf")
    if doc.needs_pass and password:
        doc.authenticate(password)
    return doc

# ---------------------------------------------------------------- organizar

def merge(paths, out_path=None):
    out = pymupdf.open()
    toc = []
    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        start = out.page_count
        if ext == ".pdf":
            with pymupdf.open(path) as src:
                out.insert_pdf(src)
        else:  # imagens e outros formatos suportados pelo MuPDF
            with pymupdf.open(path) as src:
                out.insert_pdf(pymupdf.open("pdf", src.convert_to_pdf()))
        toc.append([1, os.path.splitext(os.path.basename(path))[0], start + 1])
    if toc:
        out.set_toc(toc)
    if out_path:
        out.save(out_path, garbage=3, deflate=True)
    return out


def split(doc, mode, value, out_dir, base_name):
    """mode: 'every' (a cada N páginas), 'ranges' ('1-3;4-9'), 'bookmarks' (marcadores nível 1), 'size' (MB)."""
    os.makedirs(out_dir, exist_ok=True)
    groups = []
    n = doc.page_count
    if mode == "every":
        k = max(1, int(value))
        groups = [list(range(i, min(i + k, n))) for i in range(0, n, k)]
    elif mode == "ranges":
        for part in re.split(r"[;]", value):
            pages = parse_ranges(part, n)
            if pages:
                groups.append(pages)
    elif mode == "bookmarks":
        starts = sorted({e[2] - 1 for e in doc.get_toc() if e[0] == 1 and e[2] > 0})
        if not starts or starts[0] != 0:
            starts = [0] + starts
        starts.append(n)
        groups = [list(range(a, b)) for a, b in zip(starts, starts[1:]) if b > a]
    elif mode == "size":
        limit = float(value) * 1024 * 1024
        cur = []
        for i in range(n):
            trial = cur + [i]
            tmp = pymupdf.open()
            tmp.insert_pdf(doc, from_page=trial[0], to_page=trial[-1])
            if len(tmp.tobytes(garbage=3, deflate=True)) > limit and cur:
                groups.append(cur)
                cur = [i]
            else:
                cur = trial
        if cur:
            groups.append(cur)
    files = []
    for idx, pages in enumerate(groups, 1):
        part = pymupdf.open()
        for p in pages:
            part.insert_pdf(doc, from_page=p, to_page=p)
        fn = os.path.join(out_dir, f"{base_name}_parte{idx:02d}.pdf")
        part.save(fn, garbage=3, deflate=True)
        files.append(fn)
    return files


def extract_pages(doc, pages, out_path):
    out = pymupdf.open()
    for p in pages:
        out.insert_pdf(doc, from_page=p, to_page=p)
    out.save(out_path, garbage=3, deflate=True)
    return out_path


def delete_pages(doc, pages):
    doc.delete_pages(sorted(set(pages)))


def rotate_pages(doc, pages, angle):
    for p in pages:
        page = doc[p]
        page.set_rotation((page.rotation + angle) % 360)


def insert_blank(doc, at, like=None):
    ref = doc[like if like is not None else max(0, min(at - 1, doc.page_count - 1))] if doc.page_count else None
    w, h = (ref.rect.width, ref.rect.height) if ref else pymupdf.paper_size("a4")
    doc.new_page(pno=at, width=w, height=h)


def insert_file(doc, path, at):
    with pymupdf.open(path) as src:
        if not src.is_pdf:
            src = pymupdf.open("pdf", src.convert_to_pdf())
        doc.insert_pdf(src, start_at=at)


def reorder(doc, order):
    doc.select(order)


def crop(doc, pages, disp_rect):
    for p in pages:
        page = doc[p]
        r = to_unrot(page, disp_rect) & page.mediabox
        if not r.is_empty:
            page.set_cropbox(r)


def uncrop(doc, pages):
    for p in pages:
        doc[p].set_cropbox(doc[p].mediabox)

# ---------------------------------------------------------------- converter

def to_images(doc, out_dir, base, fmt="png", dpi=150, pages=None):
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for p in pages if pages is not None else range(doc.page_count):
        pix = doc[p].get_pixmap(dpi=dpi, alpha=False)
        fn = os.path.join(out_dir, f"{base}_p{p + 1:03d}.{fmt}")
        if fmt in ("jpg", "jpeg"):
            pix.save(fn, jpg_quality=90)
        else:
            pix.save(fn)
        files.append(fn)
    return files


def to_text(doc, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(doc):
            f.write(f"===== Página {i + 1} =====\n")
            f.write(page.get_text("text", sort=True))
            f.write("\n")
    return out_path


def to_docx(pdf_bytes, out_path, pages=None):
    from pdf2docx import Converter
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        src = tmp.name
    try:
        cv = Converter(src)
        cv.convert(out_path, pages=pages)
        cv.close()
    finally:
        os.unlink(src)
    return out_path


def to_xlsx(doc, out_path):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    found = 0
    for i, page in enumerate(doc):
        try:
            tables = page.find_tables().tables
        except Exception:
            tables = []
        for t_idx, tab in enumerate(tables, 1):
            ws = wb.create_sheet(f"P{i + 1}_T{t_idx}"[:31])
            for r_idx, row in enumerate(tab.extract(), 1):
                for c_idx, val in enumerate(row, 1):
                    val = (val or "").replace("\n", " ").strip()
                    ws.cell(r_idx, c_idx, _num(val))
                    if r_idx == 1:
                        ws.cell(r_idx, c_idx).font = Font(bold=True)
            found += 1
    if not found:  # sem tabelas: cada linha de texto vira uma linha, colunas por espaçamento
        ws = wb.create_sheet("Texto")
        r = 1
        for i, page in enumerate(doc):
            lines = {}
            for w in page.get_text("words", sort=True):
                key = (w[5], w[6])
                lines.setdefault(key, []).append(w)
            for words in lines.values():
                cells, last_x, buf = [], None, []
                for w in words:
                    if last_x is not None and w[0] - last_x > 12:
                        cells.append(" ".join(buf))
                        buf = []
                    buf.append(w[4])
                    last_x = w[2]
                cells.append(" ".join(buf))
                for c, v in enumerate(cells, 1):
                    ws.cell(r, c, _num(v))
                r += 1
    wb.save(out_path)
    return out_path, found


def _num(v):
    s = v.replace(".", "").replace(",", ".") if re.fullmatch(r"-?[\d.]+,\d+", v) else v
    try:
        return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else v
    except ValueError:
        return v


def images_to_pdf(paths, out_path, page_size=None):
    out = pymupdf.open()
    for p in paths:
        with pymupdf.open(p) as img:
            pdfbytes = img.convert_to_pdf()
        with pymupdf.open("pdf", pdfbytes) as one:
            if page_size:  # ajusta a imagem a A4
                w, h = pymupdf.paper_size(page_size)
                src = one[0].rect
                if src.width > src.height:
                    w, h = h, w
                page = out.new_page(width=w, height=h)
                page.show_pdf_page(page.rect + (20, 20, -20, -20), one, 0)
            else:
                out.insert_pdf(one)
    out.save(out_path, garbage=3, deflate=True)
    return out_path


def office_to_pdf(path, out_path):
    """Converte DOC/DOCX/XLS/PPT etc. usando o MS Office (Windows) ou LibreOffice."""
    path = os.path.abspath(path)
    out_path = os.path.abspath(out_path)
    ext = os.path.splitext(path)[1].lower()
    if sys.platform == "win32":
        try:
            import win32com.client  # pywin32
            if ext in (".doc", ".docx", ".rtf", ".odt", ".txt"):
                app = win32com.client.Dispatch("Word.Application")
                app.Visible = False
                d = app.Documents.Open(path, ReadOnly=True)
                d.SaveAs(out_path, FileFormat=17)
                d.Close(False)
                app.Quit()
                return out_path
            if ext in (".xls", ".xlsx", ".ods", ".csv"):
                app = win32com.client.Dispatch("Excel.Application")
                app.Visible = False
                wb = app.Workbooks.Open(path, ReadOnly=True)
                wb.ExportAsFixedFormat(0, out_path)
                wb.Close(False)
                app.Quit()
                return out_path
            if ext in (".ppt", ".pptx", ".odp"):
                app = win32com.client.Dispatch("PowerPoint.Application")
                pres = app.Presentations.Open(path, WithWindow=False)
                pres.SaveAs(out_path, 32)
                pres.Close()
                app.Quit()
                return out_path
        except Exception:
            pass  # tenta LibreOffice
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice and sys.platform == "win32":
        for cand in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                     r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
            if os.path.exists(cand):
                soffice = cand
    if not soffice:
        if ext in (".docx", ".xlsx", ".xlsm", ".csv", ".txt"):
            return builtin_office_to_pdf(path, out_path)
        raise RuntimeError("Para converter este formato é preciso ter o Microsoft Office ou o LibreOffice instalado. "
                           "Arquivos .docx, .xlsx, .csv e .txt são convertidos mesmo sem eles.")
    outdir = tempfile.mkdtemp()
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, path],
                   check=True, timeout=180, capture_output=True,
                   creationflags=0x08000000 if sys.platform == "win32" else 0)  # sem janela de console
    produced = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    shutil.move(produced, out_path)
    return out_path


CSS = ("body{font-family:sans-serif;font-size:11pt;line-height:1.35} h1{font-size:18pt} h2{font-size:15pt}"
       "h3{font-size:13pt} table{border-collapse:collapse} td,th{border:1px solid #999;padding:3px 5px;font-size:9pt}"
       "th{background:#eef}")


def html_to_pdf(html, out_path, archive_dir=None, landscape=False):
    """Renderiza HTML em PDF A4 com o motor do MuPDF (não depende de programas externos)."""
    mediabox = pymupdf.paper_rect("a4-l" if landscape else "a4")
    where = mediabox + (50, 50, -50, -50)
    story = pymupdf.Story(html=html, user_css=CSS, archive=pymupdf.Archive(archive_dir) if archive_dir else None)
    writer = pymupdf.DocumentWriter(out_path)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return out_path


def builtin_office_to_pdf(path, out_path):
    """Conversão embutida (sem Office/LibreOffice) de .docx, .xlsx, .csv e .txt."""
    ext = os.path.splitext(path)[1].lower()
    tmp = tempfile.mkdtemp()
    if ext == ".docx":
        import mammoth
        counter = [0]

        def save_image(image):
            counter[0] += 1
            name = f"img{counter[0]}.{image.content_type.split('/')[-1].replace('jpeg', 'jpg')}"
            with image.open() as src, open(os.path.join(tmp, name), "wb") as dst:
                dst.write(src.read())
            return {"src": name}
        with open(path, "rb") as f:
            body = mammoth.convert_to_html(f, convert_image=mammoth.images.img_element(save_image)).value
        return html_to_pdf(body, out_path, tmp)
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True, read_only=True)
        parts, wide = [], False
        for ws in wb.worksheets:
            rows = [r for r in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in r)]
            if not rows:
                continue
            ncol = max(len(r) for r in rows)
            wide = wide or ncol > 7
            trs = "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{html.escape(_fmt(v))}</{'th' if i == 0 else 'td'}>"
                                           for v in r) + "</tr>" for i, r in enumerate(rows))
            parts.append(f"<h2>{html.escape(ws.title)}</h2><table>{trs}</table>")
        return html_to_pdf("".join(parts) or "<p>(planilha vazia)</p>", out_path, landscape=wide)
    if ext == ".csv":
        import csv
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
            except csv.Error:
                dialect = csv.excel
            rows = list(csv.reader(f, dialect))
        trs = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows)
        return html_to_pdf(f"<table>{trs}</table>", out_path, landscape=max((len(r) for r in rows), default=0) > 7)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return html_to_pdf(f"<pre style='font-family:monospace;font-size:9.5pt;white-space:pre-wrap'>{html.escape(text)}</pre>", out_path)


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    return str(v)


def compress(doc, level="media"):
    """Retorna bytes comprimidos. level: baixa | media | alta (mais compressão = menor qualidade)."""
    cfg = {"baixa": (200, 85), "media": (150, 70), "alta": (96, 50)}[level]
    work = pymupdf.open("pdf", doc.tobytes())
    try:
        work.rewrite_images(dpi_threshold=cfg[0] + 10, dpi_target=cfg[0], quality=cfg[1],
                            lossy=True, lossless=True, bitonal=True, color=True, gray=True,
                            set_to_gray=False)
    except TypeError:
        work.rewrite_images(dpi_threshold=cfg[0] + 10, dpi_target=cfg[0], quality=cfg[1])
    try:
        work.subset_fonts()
    except Exception:
        pass
    data = work.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True, use_objstms=1)
    return data

# ---------------------------------------------------------------- editar

BASE_FONTS = {"Helvetica": "helv", "Helvetica Negrito": "hebo", "Helvetica Itálico": "heit",
              "Times": "tiro", "Times Negrito": "tibo", "Times Itálico": "tiit",
              "Courier": "cour", "Courier Negrito": "cobo"}


ORIGINAL_FONT = "__original__"


def guess_font(span):
    """Fonte padrão (base-14) mais parecida: família, negrito e itálico."""
    name = span.get("font", "").lower()
    flags = span.get("flags", 0)
    bold = bool(flags & 16) or "bold" in name or "black" in name or "heavy" in name
    italic = bool(flags & 2) or "italic" in name or "oblique" in name
    serif = bool(flags & 4) or any(k in name for k in ("times", "georgia", "garamond", "cambria", "book", "serif")) \
        and "sans" not in name
    if "courier" in name or "mono" in name or "consol" in name or flags & 8:
        return {(0, 0): "cour", (0, 1): "coit", (1, 0): "cobo", (1, 1): "cobi"}[(bold, italic)]
    if serif:
        return {(0, 0): "tiro", (0, 1): "tiit", (1, 0): "tibo", (1, 1): "tibi"}[(bold, italic)]
    return {(0, 0): "helv", (0, 1): "heit", (1, 0): "hebo", (1, 1): "hebi"}[(bold, italic)]


def _norm_font(name):
    name = (name or "").split("+")[-1].lower()
    for junk in ("ps", "mt", "regular", "roman", "-", " ", ",", "_"):
        name = name.replace(junk, "") if junk not in ("ps", "mt") else re.sub(rf"{junk}$", "", name)
    return name


_SYSTEM_FONTS = None


def system_fonts():
    """Índice nome-normalizado -> arquivo das fontes instaladas (Windows, usuário, Linux, macOS)."""
    global _SYSTEM_FONTS
    if _SYSTEM_FONTS is not None:
        return _SYSTEM_FONTS
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
            "/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
            "/Library/Fonts", "/System/Library/Fonts"]
    idx = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for base, _, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".ttf", ".otf")):
                    continue
                path = os.path.join(base, fn)
                try:
                    f = pymupdf.Font(fontfile=path)
                    for key in {_norm_font(f.name), _norm_font(os.path.splitext(fn)[0])}:
                        idx.setdefault(key, path)
                except Exception:
                    pass
    _SYSTEM_FONTS = idx
    return idx


def _covers(font, text):
    return all(font.has_glyph(ord(c)) for c in text if not c.isspace())


def resolve_font(page, span, text):
    """Escolhe a fonte para reescrever um trecho mantendo a aparência original.
    Retorna (fontname, fontbuffer|None, fontfile|None, descrição)."""
    want = _norm_font(span.get("font", ""))
    # 1) a própria fonte embutida no PDF, se tiver todos os caracteres do novo texto
    try:
        for xref, ext, ftype, basefont, *_ in page.get_fonts():
            if _norm_font(basefont) != want or ftype == "Type3":
                continue
            _, fext, _, buf = page.parent.extract_font(xref)
            if buf and fext not in ("n/a", ""):
                f = pymupdf.Font(fontbuffer=buf)
                if _covers(f, text):
                    return f"LmnE{xref}", buf, None, f"{span.get('font')} (fonte original do PDF)"
    except Exception:
        pass
    # 2) a mesma fonte instalada no computador (ex.: Arial, Calibri, Segoe UI)
    try:
        path = system_fonts().get(want)
        if path:
            f = pymupdf.Font(fontfile=path)
            if _covers(f, text):
                return f"LmnS{abs(hash(path)) % 10**6}", None, path, f"{f.name} (instalada no computador)"
    except Exception:
        pass
    # 3) fonte padrão parecida
    base = guess_font(span)
    return base, None, None, f"{span.get('font')} aproximada por fonte padrão"


def span_at(page, disp_point):
    """Retorna o span de texto sob o ponto (coordenadas de exibição)."""
    pt = pymupdf.Point(disp_point) * page.derotation_matrix
    d = page.get_text("dict")
    for b in d["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                if pymupdf.Rect(s["bbox"]).contains(pt) and s["text"].strip():
                    s = dict(s)
                    s["dir"] = line["dir"]
                    return s
    return None


def replace_span(page, span, new_text, fontsize=None, color=None, fontname=None):
    """Substitui um trecho de texto. fontname=ORIGINAL_FONT (padrão) tenta manter a fonte do documento.
    Retorna a descrição da fonte usada."""
    rect = pymupdf.Rect(span["bbox"])
    page.add_redact_annot(rect, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    fs = fontsize or span["size"]
    col = color if color is not None else pymupdf.sRGB_to_pdf(span["color"])
    origin = pymupdf.Point(span["origin"])
    used = fontname
    if not new_text:
        return used
    if fontname in (None, ORIGINAL_FONT):
        fn, buf, path, used = resolve_font(page, span, new_text)
        if buf or path:
            page.insert_font(fontname=fn, fontbuffer=buf, fontfile=path)
        page.insert_text(origin, new_text, fontsize=fs, fontname=fn, color=col, rotate=page.rotation)
    else:
        page.insert_text(origin, new_text, fontsize=fs, fontname=fontname, color=col, rotate=page.rotation)
    return used


def add_text(page, disp_point, text, fontsize=12, fontname="helv", color=(0, 0, 0)):
    pt = pymupdf.Point(disp_point) * page.derotation_matrix
    lh = fontsize * 1.2
    for i, line in enumerate(text.splitlines() or [""]):
        off = pymupdf.Point(0, fontsize + i * lh) * pymupdf.Matrix(-page.rotation) if page.rotation else pymupdf.Point(0, fontsize + i * lh)
        page.insert_text(pt + off, line, fontsize=fontsize, fontname=fontname, color=color, rotate=page.rotation)


def add_image(page, disp_rect, image_path_or_bytes, keep_proportion=True, overlay=True):
    r = to_unrot(page, disp_rect)
    kw = {"stream": image_path_or_bytes} if isinstance(image_path_or_bytes, (bytes, bytearray)) else {"filename": image_path_or_bytes}
    page.insert_image(r, keep_proportion=keep_proportion, overlay=overlay, rotate=page.rotation, **kw)


def watermark(doc, text, pages=None, fontsize=60, angle=45, opacity=0.18, color="#d7373f", image=None):
    col = hex_to_rgb(color)
    for p in pages if pages is not None else range(doc.page_count):
        page = doc[p]
        r = page.rect
        if image:
            w = r.width * 0.5
            box = pymupdf.Rect(r.width / 2 - w / 2, r.height / 2 - w / 2, r.width / 2 + w / 2, r.height / 2 + w / 2)
            page.insert_image(to_unrot(page, box), filename=image, overlay=True, keep_proportion=True)
            continue
        font = pymupdf.Font("hebo")
        tw = font.text_length(text, fontsize)
        center = pymupdf.Point(r.width / 2, r.height / 2) * page.derotation_matrix
        start = pymupdf.Point(center.x - tw / 2, center.y + fontsize / 3)
        mat = pymupdf.Matrix(-angle - page.rotation)
        page.insert_text(start, text, fontsize=fontsize, fontname="hebo", color=col,
                         fill_opacity=opacity, stroke_opacity=opacity, morph=(center, mat), overlay=True)


def page_numbers(doc, fmt="Página {n} de {total}", position="inferior-centro", fontsize=10,
                 start=1, pages=None, margin=24, color="#000000", header_text="", footer_text=""):
    col = hex_to_rgb(color)
    pages = list(pages) if pages is not None else list(range(doc.page_count))
    total = len(pages) + start - 1
    font = pymupdf.Font("helv")
    for k, p in enumerate(pages):
        page = doc[p]
        r = page.rect
        items = []
        if fmt:
            items.append((position, fmt.format(n=k + start, total=total)))
        if header_text:
            items.append(("superior-centro", header_text.format(n=k + start, total=total)))
        if footer_text:
            items.append(("inferior-esquerda", footer_text.format(n=k + start, total=total)))
        for pos, txt in items:
            tw = font.text_length(txt, fontsize)
            vert, horiz = pos.split("-")
            y = margin + fontsize if vert == "superior" else r.height - margin
            x = {"esquerda": margin, "centro": (r.width - tw) / 2, "direita": r.width - margin - tw}[horiz]
            pt = pymupdf.Point(x, y) * page.derotation_matrix
            page.insert_text(pt, txt, fontsize=fontsize, fontname="helv", color=col, rotate=page.rotation)


def set_background(doc, color, pages=None):
    col = hex_to_rgb(color)
    for p in pages if pages is not None else range(doc.page_count):
        page = doc[p]
        page.draw_rect(page.mediabox, color=None, fill=col, overlay=False)

# ---------------------------------------------------------------- ocultar / proteger

def redact_search(doc, needle, regex=False, case=False, pages=None):
    count = 0
    for p in pages if pages is not None else range(doc.page_count):
        page = doc[p]
        rects = []
        if regex:
            flags = 0 if case else re.I
            words = page.get_text("words")
            text_rects = []
            for w in words:
                if re.search(needle, w[4], flags):
                    text_rects.append(pymupdf.Rect(w[:4]))
            rects.extend(text_rects)
        else:
            rects.extend(page.search_for(needle))
        for r in rects:
            page.add_redact_annot(r, fill=(0, 0, 0))
            count += 1
    return count


PATTERNS = {
    "CPF": r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}",
    "CNPJ": r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}",
    "E-mail": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "Telefone": r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}",
}


def redact_pattern(doc, pattern):
    count = 0
    rx = re.compile(pattern)
    for page in doc:
        text_words = page.get_text("words")
        for line_key in {(w[5], w[6]) for w in text_words}:
            line = [w for w in text_words if (w[5], w[6]) == line_key]
            s = " ".join(w[4] for w in line)
            for m in rx.finditer(s):
                for r in page.search_for(m.group(0)):
                    page.add_redact_annot(r, fill=(0, 0, 0))
                    count += 1
    return count


def apply_redactions(doc):
    n = 0
    for page in doc:
        if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots() or []):
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
            n += 1
    return n


def sanitize(doc):
    """Remove informações ocultas: metadados, XMP, anexos, JavaScript, comentários, links."""
    doc.scrub(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=True,
              javascript=True, metadata=True, redactions=True, remove_links=False,
              reset_fields=False, reset_responses=True, thumbnails=True, xml_metadata=True)


PERM_LABELS = {
    "print": ("Imprimir", pymupdf.PDF_PERM_PRINT),
    "modify": ("Alterar o documento", pymupdf.PDF_PERM_MODIFY),
    "copy": ("Copiar conteúdo", pymupdf.PDF_PERM_COPY),
    "annotate": ("Comentar / preencher", pymupdf.PDF_PERM_ANNOTATE),
    "form": ("Preencher formulários", pymupdf.PDF_PERM_FORM),
    "assemble": ("Organizar páginas", pymupdf.PDF_PERM_ASSEMBLE),
    "print_hq": ("Impressão em alta qualidade", pymupdf.PDF_PERM_PRINT_HQ),
}


def encrypted_bytes(doc, user_pw, owner_pw, perms):
    perm_val = 0
    for k in perms:
        perm_val |= PERM_LABELS[k][1]
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=user_pw or "",
                       owner_pw=owner_pw or user_pw or "", permissions=perm_val, garbage=3, deflate=True)


def decrypted_bytes(doc):
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True)

# ---------------------------------------------------------------- OCR

def tessdata_dir():
    """Usa primeiro os idiomas que acompanham o programa (português e inglês), depois o Tesseract instalado."""
    from . import resource
    bundled = resource("assets", "tessdata")
    if os.path.isfile(os.path.join(bundled, "por.traineddata")):
        return bundled
    env = os.environ.get("TESSDATA_PREFIX")
    if env and os.path.isdir(env):
        return env
    cands = [r"C:\Program Files\Tesseract-OCR\tessdata", r"C:\Program Files (x86)\Tesseract-OCR\tessdata"]
    for c in cands:
        if os.path.isdir(c):
            return c
    try:
        return pymupdf.get_tessdata()
    except Exception:
        return None


def ocr_languages():
    d = tessdata_dir()
    if not d:
        return []
    return sorted(f[:-12] for f in os.listdir(d) if f.endswith(".traineddata") and f != "osd.traineddata")


def ocr(doc, pages=None, language="por", dpi=300, progress=None, skip_text_pages=True):
    """Adiciona uma camada de texto invisível e pesquisável sobre páginas digitalizadas."""
    tess = tessdata_dir()
    if not tess:
        raise RuntimeError("Dados de idioma do OCR não encontrados (assets/tessdata).")
    pages = list(pages) if pages is not None else list(range(doc.page_count))
    done = 0
    for k, p in enumerate(pages):
        if progress and progress(k, len(pages)) is False:
            break
        page = doc[p]
        if skip_text_pages and len(page.get_text("text").strip()) > 20:
            continue
        tp = page.get_textpage_ocr(language=language, dpi=dpi, full=True, tessdata=tess)
        words = page.get_text("words", textpage=tp)
        font = pymupdf.Font("helv")
        tw = pymupdf.TextWriter(page.rect)
        for w in words:
            r = pymupdf.Rect(w[:4])
            if r.is_empty or not w[4].strip():
                continue
            fs = max(r.height * 0.95, 1)
            length = font.text_length(w[4], fs)
            if length > 0:
                fs = fs * min(1.0, r.width / length) if length > r.width else fs
            tw.append((r.x0, r.y1 - r.height * 0.2), w[4], font=font, fontsize=fs)
        tw.write_text(page, render_mode=3, overlay=True)
        done += 1
    if progress:
        progress(len(pages), len(pages))
    return done

# ---------------------------------------------------------------- formulários

FIELD_TYPES = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: "Texto", pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "Caixa de seleção",
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "Lista suspensa", pymupdf.PDF_WIDGET_TYPE_LISTBOX: "Lista",
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "Botão de opção", pymupdf.PDF_WIDGET_TYPE_SIGNATURE: "Assinatura",
    pymupdf.PDF_WIDGET_TYPE_BUTTON: "Botão",
}


def list_fields(doc):
    out = []
    for p, page in enumerate(doc):
        for w in page.widgets() or []:
            out.append(dict(page=p, xref=w.xref, name=w.field_name, type=w.field_type,
                            type_name=FIELD_TYPES.get(w.field_type, "?"), value=w.field_value,
                            choices=w.choice_values, on=w.on_state() if w.field_type in (
                                pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON) else None))
    return out


def set_field(doc, page_no, xref, value):
    page = doc[page_no]
    for w in page.widgets():
        if w.xref == xref:
            if w.field_type in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                w.field_value = w.on_state() if value else "Off"
            else:
                w.field_value = value
            w.update()
            return True
    return False


def add_field(page, disp_rect, kind, name, choices=None):
    w = pymupdf.Widget()
    w.rect = to_unrot(page, disp_rect)
    w.field_name = name
    w.field_type = {"text": pymupdf.PDF_WIDGET_TYPE_TEXT, "check": pymupdf.PDF_WIDGET_TYPE_CHECKBOX,
                    "combo": pymupdf.PDF_WIDGET_TYPE_COMBOBOX}[kind]
    if kind == "combo":
        w.choice_values = choices or ["Opção 1", "Opção 2"]
        w.field_value = w.choice_values[0]
    if kind == "text":
        w.text_fontsize = 0
    w.border_color = (0.3, 0.45, 0.8)
    w.fill_color = (0.93, 0.95, 1)
    page.add_widget(w)


# ---------------------------------------------------------------- detecção automática de formulário

SIG_WORDS = re.compile(r"assinatura|cedente|cession[aá]ri|contratante|contratad|testemunha|devedor|credor|avalista|"
                       r"fiador|locador|locat[aá]ri|comprador|vendedor|outorgante|outorgad|promitente|signat[aá]ri|"
                       r"respons[aá]vel|representante|declarante|requerente|interveniente|anuente|emitente|s[oó]cio",
                       re.I)
FILL_RUN = re.compile(r"_{3,}|\.{6,}|…{2,}")
BOX_RUN = re.compile(r"[\(\[]\s{0,3}[\)\]]|[☐□❑❒▢]")


def _lines_with_chars(page):
    """Linhas de texto com o retângulo de cada caractere (para localizar ____ e ( ) com precisão)."""
    out = []
    raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    for b in raw.get("blocks", []):
        for ln in b.get("lines", []):
            chars, size = [], 0
            for sp in ln.get("spans", []):
                size = max(size, sp.get("size", 0))
                for ch in sp.get("chars", []):
                    chars.append((ch["c"], pymupdf.Rect(ch["bbox"])))
            if chars:
                out.append((chars, size or 10))
    return out


def _label_left(words, rect, max_words=5):
    """Texto à esquerda do campo, na mesma linha (o rótulo, ex.: "Nome completo:")."""
    cy = (rect.y0 + rect.y1) / 2
    same = [w for w in words if w[3] < rect.y1 + 3 and w[1] > rect.y0 - 6 and w[2] <= rect.x0 + 1
            and abs((w[1] + w[3]) / 2 - cy) < max(8, rect.height)]
    same.sort(key=lambda w: w[0])
    lab = []
    for w in reversed(same):
        if lab and FILL_RUN.search(w[4]):
            break
        lab.insert(0, w[4])
        if len(lab) >= max_words or (len(lab) > 1 and w[4].endswith((".", ";"))):
            break
    txt = " ".join(lab)
    txt = FILL_RUN.sub("", txt)
    return re.sub(r"[:\s]+$", "", txt).strip(" ._-")


def _label_right(words, r, size=10):
    cy = (r.y0 + r.y1) / 2
    nxt = [w for w in words if w[0] >= r.x1 - 1 and abs((w[1] + w[3]) / 2 - cy) < max(size, 6)]
    nxt.sort(key=lambda w: w[0])
    lab, last_x = [], r.x1
    for w in nxt:
        if len(lab) >= 5 or w[0] - last_x > (40 if not lab else 12) or BOX_RUN.search(w[4]) or w[4] in ("(", ")", "[", "]"):
            break
        lab.append(w[4])
        last_x = w[2]
    return " ".join(lab)


def _label_above(words, r):
    up = [w for w in words if r.y0 - 18 <= w[3] <= r.y0 + 1 and w[0] < r.x0 + r.width * 0.5 and w[2] > r.x0 - 4]
    up.sort(key=lambda w: (round(w[1]), w[0]))
    txt = " ".join(w[4] for w in up[:5])
    return re.sub(r"[:\s]+$", "", txt).strip(" ._-")


def _label_below(words, rect):
    below = [w for w in words if rect.y1 - 1 <= w[1] <= rect.y1 + 16 and w[0] < rect.x1 and w[2] > rect.x0]
    below.sort(key=lambda w: (round(w[1]), w[0]))
    return " ".join(w[4] for w in below[:6]).strip()


def detect_fields(page):
    """Procura campos para preencher: linhas ____ / ....., linhas desenhadas vazias, caixas vazias e ( ) / ☐.
    Linhas com "Assinatura", "Cedente", "Testemunha"… logo abaixo viram campos de assinatura.
    Retorna [(tipo, retângulo sem rotação, rótulo)] com tipo em text | check | signature."""
    words = page.get_text("words", sort=True)
    found = []

    def has_text(r):
        return any(pymupdf.Rect(w[:4]).intersects(r) and not FILL_RUN.fullmatch(w[4]) and w[4].strip() for w in words)

    def add(kind, r, label):
        r = pymupdf.Rect(r).normalize()
        if r.is_empty or r.width < 4:
            return
        for k2, r2, _ in found:  # descarta duplicados (ex.: ____ desenhado e também como linha)
            inter = pymupdf.Rect(r) & r2
            if not inter.is_empty and inter.get_area() > 0.4 * min(r.get_area(), r2.get_area()):
                return
        found.append((kind, r, label))

    # 1) sequências de sublinhado / pontilhado e ( ) [ ] ☐ no texto
    for chars, size in _lines_with_chars(page):
        s = "".join(c for c, _ in chars)
        for m in FILL_RUN.finditer(s):
            seg = [r for _, r in chars[m.start():m.end()]]
            r = pymupdf.Rect(seg[0])
            for x in seg[1:]:
                r |= x
            h = max(size * 1.3, 11)
            fr = pymupdf.Rect(r.x0, r.y1 - h, r.x1, r.y1 + 1)
            below = _label_below(words, pymupdf.Rect(r.x0, r.y1, r.x1, r.y1))
            if SIG_WORDS.search(below) and r.width > 90:
                add("signature", pymupdf.Rect(r.x0, r.y1 - 34, r.x1, r.y1), below)
            else:
                add("text", fr, _label_left(words, fr))
        for m in BOX_RUN.finditer(s):
            seg = [r for _, r in chars[m.start():m.end()]]
            r = pymupdf.Rect(seg[0])
            for x in seg[1:]:
                r |= x
            side = max(min(r.height, size) * 0.8, 7)
            cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            box = pymupdf.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
            add("check", box, _label_right(words, r, size))

    # 2) linhas desenhadas (ou retângulos finos) sem texto logo acima; 3) caixas vazias
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    hlines, boxes = [], []
    for d in drawings:
        for it in d.get("items", []):
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 0.8 and abs(p2.x - p1.x) >= 36:
                    hlines.append(pymupdf.Rect(min(p1.x, p2.x), p1.y, max(p1.x, p2.x), p1.y))
            elif it[0] == "re":
                r = pymupdf.Rect(it[1]).normalize()
                if r.height <= 1.6 and r.width >= 36:
                    hlines.append(pymupdf.Rect(r.x0, r.y1, r.x1, r.y1))
                elif 5.5 <= r.width <= 18 and 5.5 <= r.height <= 18 and abs(r.width - r.height) < 2.5:
                    boxes.append(("check", r))
                elif r.width >= 40 and 12 <= r.height <= 60:
                    boxes.append(("text", r))
    pw = page.rect.width
    for ln in hlines:
        if ln.width > pw * 0.8:  # linha divisória da página inteira
            continue
        above = pymupdf.Rect(ln.x0 + 1, ln.y0 - 13, ln.x1 - 1, ln.y0 - 0.8)
        if has_text(above):
            continue
        below = _label_below(words, ln)
        if SIG_WORDS.search(below) and ln.width > 90:
            add("signature", pymupdf.Rect(ln.x0, ln.y0 - 34, ln.x1, ln.y0), below)
        else:
            add("text", pymupdf.Rect(ln.x0, ln.y0 - 14, ln.x1, ln.y0 + 1), _label_left(words, pymupdf.Rect(ln.x0, ln.y0 - 14, ln.x1, ln.y0)))
    for kind, r in boxes:
        inner = r + (1.5, 1.5, -1.5, -1.5)
        if has_text(inner):
            continue
        if kind == "text":
            add(kind, inner, _label_left(words, r) or _label_above(words, r))
        else:
            add(kind, r, _label_right(words, r))

    # descarta o que já é campo
    existing = [w.rect for w in (page.widgets() or [])]
    out = []
    for kind, r, label in found:
        if any((r & e).get_area() > 0.3 * r.get_area() for e in existing if not (r & e).is_empty):
            continue
        out.append((kind, r, label))
    return out


def _field_name(label, kind, used, page_no):
    base = re.sub(r"\s+", " ", re.sub(r"[^\w\s/º°ª-]", "", label or "")).strip()[:40]
    if not base:
        base = {"text": "Campo", "check": "Opção", "signature": "Assinatura"}[kind] + f" pág {page_no + 1}"
    elif kind == "signature" and not base.lower().startswith("assinatura"):
        base = f"Assinatura {base}"
    name, n = base, 2
    while name in used:
        name, n = f"{base} {n}", n + 1
    used.add(name)
    return name


def create_detected_fields(doc, pages=None):
    """Cria os campos detectados (sem borda nem fundo: o documento continua igual na impressão).
    Retorna {"text": n, "check": n, "signature": n}."""
    used = set()
    for pg in doc:
        for w in pg.widgets() or []:
            used.add(w.field_name)
    count = {"text": 0, "check": 0, "signature": 0}
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        for kind, r, label in detect_fields(page):
            w = pymupdf.Widget()
            w.rect = r
            w.field_name = _field_name(label, kind, used, pno)
            w.field_label = label or w.field_name
            w.field_type = {"text": pymupdf.PDF_WIDGET_TYPE_TEXT, "check": pymupdf.PDF_WIDGET_TYPE_CHECKBOX,
                            "signature": pymupdf.PDF_WIDGET_TYPE_SIGNATURE}[kind]
            if kind == "text":
                w.text_fontsize = 0
                w.text_font = "Helv"
            if kind == "check":
                w.field_value = False
            w.border_color = None
            w.border_width = 0
            w.fill_color = None
            page.add_widget(w)
            if kind == "signature":
                _blank_appearance(doc, w.xref)
            count[kind] += 1
    return count


def _empty_sig_widgets(page):
    return [w for w in (page.widgets(types=[pymupdf.PDF_WIDGET_TYPE_SIGNATURE]) or [])
            if not getattr(w, "is_signed", False)]


def has_empty_signature_fields(doc):
    try:
        return bool(doc.is_form_pdf) and any(_empty_sig_widgets(p) for p in doc)
    except Exception:
        return False


def remove_empty_signature_fields(doc):
    for page in doc:
        for w in _empty_sig_widgets(page):
            try:
                page.delete_widget(w)
            except Exception:
                pass


def _blank_appearance(doc, xref):
    """Tira a etiqueta "SIGN" que o MuPDF desenha no campo de assinatura vazio (não deve sair na impressão)."""
    try:
        t, v = doc.xref_get_key(xref, "AP/N")
        if t == "xref":
            doc.update_stream(int(v.split()[0]), b" ")
    except Exception:
        pass


def flatten(doc):
    doc.bake(annots=True, widgets=True)

# ---------------------------------------------------------------- comparar

def compare(doc_a, doc_b, name_a="Original", name_b="Revisado"):
    """Gera relatório HTML com diferenças de texto página a página."""
    n = max(doc_a.page_count, doc_b.page_count)
    parts, changed = [], 0
    for i in range(n):
        ta = doc_a[i].get_text("text", sort=True).split() if i < doc_a.page_count else []
        tb = doc_b[i].get_text("text", sort=True).split() if i < doc_b.page_count else []
        if ta == tb:
            continue
        changed += 1
        sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
        out = []
        ins = dele = 0
        for op, a0, a1, b0, b1 in sm.get_opcodes():
            if op == "equal":
                seg = ta[a0:a1]
                if len(seg) > 24:
                    seg = seg[:10] + ["…"] + seg[-10:]
                out.append(html.escape(" ".join(seg)))
            if op in ("delete", "replace"):
                dele += a1 - a0
                out.append(f'<span style="background:#ffd7d9;text-decoration:line-through">{html.escape(" ".join(ta[a0:a1]))}</span>')
            if op in ("insert", "replace"):
                ins += b1 - b0
                out.append(f'<span style="background:#c9f2d4">{html.escape(" ".join(tb[b0:b1]))}</span>')
        parts.append(f"<h3>Página {i + 1} — {ins} palavra(s) inserida(s), {dele} removida(s)</h3><p>{' '.join(out)}</p>")
    head = (f"<h2>Comparação de arquivos</h2><p><b>{html.escape(name_a)}</b> ({doc_a.page_count} pág.) × "
            f"<b>{html.escape(name_b)}</b> ({doc_b.page_count} pág.)</p>")
    if not parts:
        return head + "<p>Nenhuma diferença de texto encontrada.</p>", 0
    return head + f"<p>{changed} página(s) com diferenças.</p>" + "".join(parts), changed

def _doc_words(doc):
    """Palavras do documento em ordem de leitura: (texto, página, retângulo na exibição, chave da linha)."""
    out = []
    for pno in range(doc.page_count):
        pg = doc[pno]
        m = pg.rotation_matrix
        # o carimbo visível das assinaturas não é conteúdo do documento
        skip = [w.rect for w in (pg.widgets() or []) if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE]
        for x0, y0, x1, y1, w, b, ln, _ in pg.get_text("words", sort=True):
            r = pymupdf.Rect(x0, y0, x1, y1)
            if skip and any(sr.contains((r.tl + r.br) / 2) for sr in skip):
                continue
            out.append((w, pno, r * m, (pno, b, ln)))
    return out


def _line_rects(words):
    """Une palavras vizinhas da mesma linha num único retângulo (destaque contínuo)."""
    out = {}
    cur_key, cur = None, None
    for _, pno, r, key in words:
        if key == cur_key and cur is not None:
            cur |= r
        else:
            if cur is not None:
                out.setdefault(cur_key[0], []).append(cur)
            cur_key, cur = key, pymupdf.Rect(r)
    if cur is not None:
        out.setdefault(cur_key[0], []).append(cur)
    return out


def compare_docs(doc_a, doc_b, max_words=120000):
    """Compara o texto de dois documentos palavra a palavra (o texto pode mudar de página entre as versões).
    Retorna a lista de alterações com as páginas/retângulos em cada documento, para destacar e navegar."""
    wa, wb = _doc_words(doc_a), _doc_words(doc_b)
    if len(wa) + len(wb) > max_words:  # documentos enormes: compara página a página (mais rápido)
        blocks = []
        for p in range(max(doc_a.page_count, doc_b.page_count)):
            blocks.append(([w for w in wa if w[1] == p], [w for w in wb if w[1] == p]))
    else:
        blocks = [(wa, wb)]
    changes = []
    for A, B in blocks:
        sm = difflib.SequenceMatcher(None, [w[0] for w in A], [w[0] for w in B], autojunk=False)
        for op, a0, a1, b0, b1 in sm.get_opcodes():
            if op == "equal":
                continue
            ra, rb = A[a0:a1], B[b0:b1]
            # posição de referência no outro documento (onde o trecho entraria/sairia)
            anchor_a = (A[a0] if a0 < len(A) else (A[-1] if A else None))
            anchor_b = (B[b0] if b0 < len(B) else (B[-1] if B else None))
            kind = {"replace": "alterado", "delete": "removido", "insert": "inserido"}[op]
            changes.append(dict(
                kind=kind,
                text_a=" ".join(w[0] for w in ra), text_b=" ".join(w[0] for w in rb),
                page_a=ra[0][1] if ra else (anchor_a[1] if anchor_a else 0),
                page_b=rb[0][1] if rb else (anchor_b[1] if anchor_b else 0),
                rects_a=_line_rects(ra), rects_b=_line_rects(rb),
                anchor_a=(anchor_a[1], anchor_a[2]) if anchor_a and not ra else None,
                anchor_b=(anchor_b[1], anchor_b[2]) if anchor_b and not rb else None))
    return dict(changes=changes, pages_a=doc_a.page_count, pages_b=doc_b.page_count,
                words_a=len(wa), words_b=len(wb))


def annots_summary(doc):
    """Contagem de comentários e campos preenchidos (para mostrar o que mudou depois de uma assinatura)."""
    n_annots, fields = 0, {}
    for pg in doc:
        for a in pg.annots() or []:
            if a.type[0] not in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_WIDGET):
                n_annots += 1
        for w in pg.widgets() or []:
            fields[w.field_name] = (w.field_type, str(w.field_value or ""))
    return n_annots, fields


# ---------------------------------------------------------------- anexos

def attachments(doc):
    out = []
    for n in doc.embfile_names():
        info = dict(doc.embfile_info(n))
        info["name"] = n
        out.append(info)
    return out


def add_attachment(doc, path):
    with open(path, "rb") as f:
        doc.embfile_add(os.path.basename(path), f.read(), filename=os.path.basename(path))


def save_attachment(doc, name, out_path):
    with open(out_path, "wb") as f:
        f.write(doc.embfile_get(name))
