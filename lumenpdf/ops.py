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
        raise RuntimeError("Instale o Microsoft Office ou o LibreOffice para converter arquivos do Office.")
    outdir = tempfile.mkdtemp()
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, path],
                   check=True, timeout=180, capture_output=True)
    produced = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    shutil.move(produced, out_path)
    return out_path


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

BASE_FONTS = {"Helvetica": "helv", "Helvetica Negrito": "hebo", "Times": "tiro",
              "Times Negrito": "tibo", "Courier": "cour", "Courier Negrito": "cobo"}


def guess_font(span):
    name = span.get("font", "").lower()
    bold = bool(span.get("flags", 0) & 16) or "bold" in name
    if "times" in name or "serif" in name and "sans" not in name:
        return "tibo" if bold else "tiro"
    if "courier" in name or "mono" in name:
        return "cobo" if bold else "cour"
    return "hebo" if bold else "helv"


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
    rect = pymupdf.Rect(span["bbox"])
    page.add_redact_annot(rect, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    fs = fontsize or span["size"]
    col = color if color is not None else pymupdf.sRGB_to_pdf(span["color"])
    fn = fontname or guess_font(span)
    origin = pymupdf.Point(span["origin"])
    if new_text:
        page.insert_text(origin, new_text, fontsize=fs, fontname=fn, color=col,
                         rotate=page.rotation)


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
        raise RuntimeError("Tesseract OCR não encontrado. Instale-o e o idioma 'por'.")
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
