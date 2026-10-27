"""Conversão para PDF/A-2b (arquivamento de longo prazo).

O que é feito:
- perfil de cor sRGB como "intenção de saída" e metadados XMP com a identificação PDF/A;
- fontes que não estão dentro do arquivo são embutidas com equivalentes de mesmas medidas
  (Arial/Helvetica → Liberation Sans, Times → Liberation Serif, Courier → Liberation Mono, Calibri → Carlito);
- remove o que o PDF/A proíbe: JavaScript, ações de abrir programas, arquivos anexados, criptografia,
  compressão LZW e "NeedAppearances" de formulários; comentários ficam com aparência e marcados para impressão.

Se sobrar algo que não dá para corrigir (ex.: fonte sem equivalente), a função informa em `problemas`.
"""
import re
import uuid
from datetime import datetime, timezone

import pymupdf

from . import resource

WINANSI = [None] * 256
for _c in range(32, 256):
    try:
        WINANSI[_c] = bytes([_c]).decode("cp1252")
    except UnicodeDecodeError:
        WINANSI[_c] = None

_FAMILIES = [
    (("courier", "mono", "consolas"), "LiberationMono"),
    (("calibri", "carlito"), "Carlito"),
    (("times", "georgia", "garamond", "cambria", "serif", "roman", "bookman", "palatino"), "LiberationSerif"),
    (("helvetica", "arial", "verdana", "tahoma", "sans", "segoe"), "LiberationSans"),
]


def _substitute(basefont):
    """Arquivo TTF equivalente para a fonte (None se não houver)."""
    n = (basefont or "").split("+")[-1].lower()
    if any(k in n for k in ("symbol", "dingbat", "wingding")):
        return None
    fam = next((f for keys, f in _FAMILIES if any(k in n for k in keys)), None)
    if fam is None:
        fam = "LiberationSans"
    bold = any(k in n for k in ("bold", "black", "heavy", "semibold", "demi"))
    italic = any(k in n for k in ("italic", "oblique"))
    style = "BoldItalic" if bold and italic else "Bold" if bold else "Italic" if italic else "Regular"
    return resource("assets", "fontes", f"{fam}-{style}.ttf")


def _xmp(title, author, created, modified, doc_id):
    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
    xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/">
   <pdfaid:part>2</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
   <dc:format>application/pdf</dc:format>
{f'   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{esc(title)}</rdf:li></rdf:Alt></dc:title>' + chr(10) if title else ""}{f'   <dc:creator><rdf:Seq><rdf:li>{esc(author)}</rdf:li></rdf:Seq></dc:creator>' + chr(10) if author else ""}   <xmp:CreateDate>{created}</xmp:CreateDate>
   <xmp:ModifyDate>{modified}</xmp:ModifyDate>
   <xmp:MetadataDate>{modified}</xmp:MetadataDate>
   <xmp:CreatorTool>Dispersio PDF</xmp:CreatorTool>
   <pdf:Producer>Dispersio PDF</pdf:Producer>
   <xmpMM:DocumentID>uuid:{doc_id}</xmpMM:DocumentID>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def _pdf_date(dt):
    off = dt.utcoffset() or 0
    mins = int(off.total_seconds() // 60) if off else 0
    sign = "+" if mins >= 0 else "-"
    return dt.strftime("D:%Y%m%d%H%M%S") + (f"{sign}{abs(mins) // 60:02d}'{abs(mins) % 60:02d}'" if dt.tzinfo else "")


def _embed_font(doc, fxref, problems):
    """Embute uma fonte simples que não está no arquivo. Devolve True se conseguiu."""
    t, sub = doc.xref_get_key(fxref, "Subtype")
    base = doc.xref_get_key(fxref, "BaseFont")[1].lstrip("/")
    if sub not in ("/Type1", "/TrueType", "/MMType1"):
        problems.append(f"fonte “{base}” ({sub}) não está no arquivo e não pôde ser embutida")
        return False
    path = _substitute(base)
    if not path:
        problems.append(f"fonte de símbolos “{base}” não está no arquivo e não tem equivalente")
        return False
    with open(path, "rb") as f:
        data = f.read()
    font = pymupdf.Font(fontbuffer=data)
    enc_t, enc = doc.xref_get_key(fxref, "Encoding")
    if enc_t == "null" or enc in ("/StandardEncoding",):
        doc.xref_set_key(fxref, "Encoding", "/WinAnsiEncoding")
    # larguras: se o PDF já tem /Widths (fonte TrueType referenciada), elas valem; senão, as da fonte equivalente
    has_widths = doc.xref_get_key(fxref, "Widths")[0] != "null"
    if not has_widths:
        ws = []
        for c in range(32, 256):
            ch = WINANSI[c]
            ws.append(round(font.glyph_advance(ord(ch)) * 1000) if ch and font.has_glyph(ord(ch)) else 0)
        doc.xref_set_key(fxref, "FirstChar", "32")
        doc.xref_set_key(fxref, "LastChar", "255")
        doc.xref_set_key(fxref, "Widths", "[" + " ".join(map(str, ws)) + "]")
    ff = doc.get_new_xref()
    doc.update_object(ff, "<<>>")
    doc.update_stream(ff, data)
    doc.xref_set_key(ff, "Length1", str(len(data)))
    name = base.split("+")[-1]
    fd_t, fd = doc.xref_get_key(fxref, "FontDescriptor")
    if fd_t == "xref":
        fdx = int(fd.split()[0])
    else:
        fdx = doc.get_new_xref()
        bbox = font.bbox
        flags = 32 | (64 if "italic" in name.lower() or "oblique" in name.lower() else 0)
        doc.update_object(fdx, f"<</Type/FontDescriptor/FontName/{name}/Flags {flags}"
                               f"/FontBBox[{int(bbox.x0 * 1000)} {int(bbox.y0 * 1000)} {int(bbox.x1 * 1000)} {int(bbox.y1 * 1000)}]"
                               f"/ItalicAngle 0/Ascent {int(font.ascender * 1000)}/Descent {int(font.descender * 1000)}"
                               f"/CapHeight 700/StemV 80>>")
        doc.xref_set_key(fxref, "FontDescriptor", f"{fdx} 0 R")
    doc.xref_set_key(fdx, "FontFile2", f"{ff} 0 R")
    for k in ("FontFile", "FontFile3"):
        if doc.xref_get_key(fdx, k)[0] != "null":
            doc.xref_set_key(fdx, k, "null")
    # Flags: fonte "simbólica" (4) não combina com WinAnsiEncoding no PDF/A — usa "não simbólica" (32)
    ft, fl = doc.xref_get_key(fdx, "Flags")
    try:
        flv = int(fl)
    except ValueError:
        flv = 32
    doc.xref_set_key(fdx, "Flags", str((flv & ~4) | 32))
    doc.xref_set_key(fxref, "Subtype", "/TrueType")
    return True


def _top_entries(d):
    """Pares (nome, valor) do primeiro nível de um dicionário PDF em texto."""
    body = d.strip()[2:-2]
    out, i, n = [], 0, len(body)
    while i < n:
        if body[i] != "/":
            i += 1
            continue
        j = i + 1
        while j < n and body[j] not in " /<[(\n\r\t>":
            j += 1
        key = body[i + 1:j]
        while j < n and body[j] in " \n\r\t":
            j += 1
        k = j
        if body.startswith("<<", k):
            depth = 0
            while k < n:
                if body.startswith("<<", k):
                    depth += 1; k += 2; continue
                if body.startswith(">>", k):
                    depth -= 1; k += 2
                    if depth == 0:
                        break
                    continue
                k += 1
        else:
            m = re.match(r"\d+\s+\d+\s+R|/[^\s/<>\[\]()]+|[^\s/<>\[\]()]+", body[k:])
            k += m.end() if m else 1
        out.append((key, body[j:k].strip()))
        i = k
    return out


def _indirect_fonts(doc):
    """Fontes escritas direto dentro de /Resources/Font (comum em aparências de campos e comentários)
    viram objetos próprios, para poderem ser conferidas e embutidas."""
    paths = ("Resources/Font", "DR/Font")
    for x in range(1, doc.xref_length()):
        for path in paths:
            try:
                t, v = doc.xref_get_key(x, path)
            except Exception:
                continue
            if t != "dict":
                continue
            changed = False
            parts = []
            for name, val in _top_entries(v):
                if val.startswith("<<"):
                    nx = doc.get_new_xref()
                    doc.update_object(nx, val)
                    val = f"{nx} 0 R"
                    changed = True
                parts.append(f"/{name} {val}")
            if changed:
                doc.xref_set_key(x, path, "<<" + " ".join(parts) + ">>")


def convert(data, title=None, author=None):
    """Converte bytes de um PDF em PDF/A-2b. Devolve (bytes, problemas: lista de textos)."""
    problems = []
    src = pymupdf.open("pdf", data)
    if src.needs_pass:
        raise ValueError("Remova a senha do documento antes de converter para PDF/A.")
    doc = pymupdf.open("pdf", src.tobytes())   # sem criptografia
    # anexos
    if doc.embfile_count():
        for name in list(doc.embfile_names()):
            doc.embfile_del(name)
        problems.append("os arquivos anexados foram removidos (não são permitidos no PDF/A-2b)")
    cat = doc.pdf_catalog()
    for key in ("OpenAction", "AA", "Names/JavaScript"):
        if doc.xref_get_key(cat, key)[0] != "null" and key != "OpenAction":
            doc.xref_set_key(cat, key, "null")
    t, oa = doc.xref_get_key(cat, "OpenAction")
    if t != "null" and "JavaScript" in (doc.xref_object(int(oa.split()[0])) if t == "xref" else oa):
        doc.xref_set_key(cat, "OpenAction", "null")
    af_t, af = doc.xref_get_key(cat, "AcroForm")
    if af_t != "null":
        if af_t == "xref":
            doc.xref_set_key(int(af.split()[0]), "NeedAppearances", "null")
        else:
            doc.xref_set_key(cat, "AcroForm/NeedAppearances", "null")
    # comentários: com aparência e marcados para impressão (antes das fontes: atualizar a aparência cria fontes novas)
    for page in doc:
        for a in page.annots() or []:
            try:
                flags = a.flags
                a.set_flags((flags | pymupdf.PDF_ANNOT_IS_PRINT) & ~(pymupdf.PDF_ANNOT_IS_HIDDEN | pymupdf.PDF_ANNOT_IS_INVISIBLE | pymupdf.PDF_ANNOT_IS_NO_VIEW))
                a.update()
            except Exception:
                pass
    _indirect_fonts(doc)
    # objetos: LZW, ações proibidas, fontes não embutidas
    embedded_done = set()
    for x in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(x, compressed=False)
        except Exception:
            continue
        if doc.xref_is_stream(x) and "/LZWDecode" in obj:
            doc.update_stream(x, doc.xref_stream(x))
        if re.search(r"/S\s*/(JavaScript|Launch|ImportData|Hide|SetOCGState|Rendition|Trans|GoTo3DView|Sound|Movie|ResetForm|SubmitForm)\b", obj):
            if "/Type /Annot" not in obj and "/Type/Annot" not in obj:
                doc.update_object(x, "<</S/GoTo/D[0 /Fit]>>" if "/S /JavaScript" not in obj else "<<>>")
        if re.search(r"/Type\s*/Font\b(?!Descriptor)", obj):
            sub = doc.xref_get_key(x, "Subtype")[1]
            if sub == "/CIDFontType2" and doc.xref_get_key(x, "CIDToGIDMap")[0] == "null":
                doc.xref_set_key(x, "CIDToGIDMap", "/Identity")
            if sub in ("/Type0", "/Type3", "/CIDFontType0", "/CIDFontType2"):
                continue
            fd_t, fd = doc.xref_get_key(x, "FontDescriptor")
            embedded = False
            if fd_t == "xref":
                fdx = int(fd.split()[0])
                embedded = any(doc.xref_get_key(fdx, k)[0] != "null" for k in ("FontFile", "FontFile2", "FontFile3"))
            if not embedded and x not in embedded_done:
                if _embed_font(doc, x, problems):
                    embedded_done.add(x)
    # perfil de cor e metadados
    with open(resource("assets", "pdfa", "sRGB.icc"), "rb") as f:
        icc = f.read()
    ix = doc.get_new_xref()
    doc.update_object(ix, "<</N 3>>")
    doc.update_stream(ix, icc)
    oi = doc.get_new_xref()
    doc.update_object(oi, f"<</Type/OutputIntent/S/GTS_PDFA1/OutputConditionIdentifier(sRGB IEC61966-2.1)"
                          f"/Info(sRGB IEC61966-2.1)/DestOutputProfile {ix} 0 R>>")
    doc.xref_set_key(cat, "OutputIntents", f"[{oi} 0 R]")
    now = datetime.now(timezone.utc).astimezone()
    meta = doc.metadata or {}
    title = title or meta.get("title") or ""
    author = author or meta.get("author") or ""
    created = now
    iso = now.isoformat(timespec="seconds")
    md = {"creator": "Dispersio PDF", "producer": "Dispersio PDF", "creationDate": _pdf_date(created), "modDate": _pdf_date(now)}
    if title:
        md["title"] = title
    if author:
        md["author"] = author
    doc.set_metadata(md)
    doc.set_xml_metadata(_xmp(title, author, iso, iso, uuid.uuid4()))
    out = doc.tobytes(garbage=3, deflate=True, no_new_id=False)
    return out, problems
