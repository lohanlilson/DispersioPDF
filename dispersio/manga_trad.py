"""Tradução de quadrinhos e mangás nos balões.

1. OCR (Tesseract, o mesmo do “Reconhecer texto”) acha as palavras na página.
2. Palavras próximas viram um balão (uma fala).
3. A fala é traduzida para o português pelo tradutor offline do programa (o mesmo dos artigos).
4. O balão é coberto com a cor do fundo dele e a tradução é escrita centralizada por cima, no maior tamanho que couber.

Inglês funciona na hora; espanhol e japonês baixam o pacote de OCR (≈2–4 MB) na primeira vez.
"""
import os
import re
import statistics
import urllib.request

import pymupdf

from . import ops, traducao

LANGS = {"en": ("eng", "Inglês"), "es": ("spa", "Espanhol"), "ja": ("jpn", "Japonês")}
TESS_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{}.traineddata"


def user_tessdata():
    d = os.path.join(traducao.models_dir(), "..", "ocr")
    d = os.path.abspath(d)
    os.makedirs(d, exist_ok=True)
    return d


def tess_for(lang):
    """Pasta com o idioma do OCR (o que acompanha o programa ou o baixado). None se ainda não tiver."""
    code = LANGS[lang][0]
    bundled = ops.tessdata_dir()
    if bundled and os.path.isfile(os.path.join(bundled, f"{code}.traineddata")):
        return bundled
    u = user_tessdata()
    if os.path.isfile(os.path.join(u, f"{code}.traineddata")):
        return u
    return None


def download_ocr(lang, progress=None):
    code = LANGS[lang][0]
    dst = os.path.join(user_tessdata(), f"{code}.traineddata")
    tmp = dst + ".part"
    req = urllib.request.Request(TESS_URL.format(code), headers={"User-Agent": "DispersioPDF"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            b = r.read(65536)
            if not b:
                break
            f.write(b)
            got += len(b)
            if progress:
                progress(got, total)
    os.replace(tmp, dst)
    return os.path.dirname(dst)


# ------------------------------------------------------------------ português do Brasil nos diálogos
# o tradutor offline usa “tu” (Portugal): nas falas vira “você” com o verbo na 3ª pessoa
_TU_VERBS = {
    "foste": "foi", "estás": "está", "tens": "tem", "és": "é", "vais": "vai", "podes": "pode", "queres": "quer",
    "sabes": "sabe", "fazes": "faz", "dizes": "diz", "vens": "vem", "viste": "viu", "fizeste": "fez", "disseste": "disse",
    "tiveste": "teve", "estiveste": "esteve", "estavas": "estava", "eras": "era", "tinhas": "tinha", "ias": "ia",
    "podias": "podia", "querias": "queria", "sabias": "sabia", "precisas": "precisa", "achas": "acha", "pensas": "pensa",
    "gostas": "gosta", "falas": "fala", "olhas": "olha", "ouves": "ouve", "entendes": "entende", "lembras": "lembra",
    "conheces": "conhece", "acreditas": "acredita", "deves": "deve", "ficas": "fica", "fazias": "fazia", "serás": "será",
    "terás": "terá", "irás": "irá", "farás": "fará", "chegaste": "chegou", "deixaste": "deixou", "mataste": "matou",
    "voltaste": "voltou", "salvaste": "salvou", "encontraste": "encontrou", "perdeste": "perdeu", "comeste": "comeu",
}
_TU_SUBJ = {"mintas": "minta", "faças": "faça", "digas": "diga", "vás": "vá", "sejas": "seja", "tenhas": "tenha",
            "estejas": "esteja", "venhas": "venha", "morras": "morra", "fujas": "fuja", "toques": "toque", "olhes": "olhe",
            "te preocupes": "se preocupe", "te mexas": "se mexa", "chores": "chore", "desistas": "desista", "pares": "pare",
            "esqueças": "esqueça", "saias": "saia", "entres": "entre", "fales": "fale", "brinques": "brinque"}
_TU_WORDS = [(r"\bcontigo\b", "com você"), (r"\bteu\b", "seu"), (r"\btua\b", "sua"), (r"\bteus\b", "seus"),
             (r"\btuas\b", "suas"), (r"\ba ti\b", "a você"), (r"\bpara ti\b", "para você"), (r"\bde ti\b", "de você"),
             (r"\bem ti\b", "em você"), (r"\bpor ti\b", "por você")]


def _case(src, dst):
    return dst[0].upper() + dst[1:] if src[:1].isupper() else dst


def dialog_br(t):
    t = traducao.pt_br(t)
    t = re.sub(r"\b[Tt]u\b", lambda m: _case(m.group(), "você"), t)
    for a, b in _TU_SUBJ.items():
        t = re.sub(r"\b" + a + r"\b", lambda m, b=b: _case(m.group(), b), t, flags=re.I)
    for a, b in _TU_VERBS.items():
        # “você foste” (já trocou o tu) → “você foi”; sem sujeito: “Onde foste” → “Onde você foi”
        t = re.sub(r"\b(você\s+)?" + a + r"\b",
                   lambda m, b=b: (m.group(1) + b) if m.group(1) else _case(m.group(), "você " + b), t, flags=re.I)
    for a, b in _TU_WORDS:
        t = re.sub(a, lambda m, b=b: _case(m.group(), b), t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------ balões
def _words(page, lang, dpi=150):
    tess = tess_for(lang)
    if not tess:
        raise RuntimeError(f"Falta o pacote de OCR de {LANGS[lang][1].lower()}.")
    tp = page.get_textpage_ocr(language=LANGS[lang][0], dpi=dpi, full=True, tessdata=tess)
    out = []
    for w in page.get_text("words", textpage=tp):
        t = w[4].strip()
        if not t:
            continue
        r = pymupdf.Rect(w[:4])
        if r.is_empty or r.width < 2 or r.height < 4:
            continue
        out.append((r, t))
    return out


def _letters(t):
    return len(re.findall(r"[A-Za-zÀ-ÿ぀-ヿ一-鿿]", t))


def balloons(words):
    """Agrupa palavras em falas: mesma linha (vizinhas) e linhas logo abaixo, alinhadas ao centro do balão."""
    if not words:
        return []
    hs = sorted(r.height for r, _ in words)
    h = hs[len(hs) // 2]
    groups = []          # [rect, [(r, t)]]
    for r, t in sorted(words, key=lambda x: (x[0].y0, x[0].x0)):
        best = None
        for g in groups:
            gr = g[0]
            near_x = r.x0 <= gr.x1 + 1.6 * h and r.x1 >= gr.x0 - 1.6 * h
            near_y = r.y0 <= gr.y1 + 0.9 * h and r.y1 >= gr.y0 - 0.5 * h
            if near_x and near_y:
                best = g
                break
        if best is None:
            groups.append([pymupdf.Rect(r), [(r, t)]])
        else:
            best[0] |= r
            best[1].append((r, t))
    # junta grupos que se encostam (balões quebrados em dois pelo OCR)
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i][0], groups[j][0]
                if (a + (-0.6 * h, -0.6 * h, 0.6 * h, 0.6 * h)).intersects(b):
                    groups[i][0] = a | b
                    groups[i][1] += groups[j][1]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    out = []
    for rect, ws in groups:
        lines = {}
        for r, t in ws:
            key = round(r.y0 / max(h * 0.7, 1))
            lines.setdefault(key, []).append((r, t))
        text = " ".join(" ".join(t for _r, t in sorted(l, key=lambda x: x[0].x0)) for _k, l in sorted(lines.items()))
        text = re.sub(r"(\w)- (\w)", r"\1\2", text)           # palavra quebrada com hífen no fim da linha
        text = re.sub(r"(^|\s)[|l1](?=\s+[A-Z'’])", r"\1I", text)  # “| WAS” → “I WAS” (o OCR confunde o I maiúsculo)
        if _letters(text) < 2 or len(ws) == 1 and len(text) <= 2:
            continue                                           # ruído, onomatopeia de uma letra
        out.append((rect, text))
    return out


def _bg_color(pix, rect, page_rect):
    """Cor de fundo do balão: a mais comum na borda da área (normalmente branco)."""
    sx = pix.width / page_rect.width
    sy = pix.height / page_rect.height
    x0, y0 = max(0, int(rect.x0 * sx)), max(0, int(rect.y0 * sy))
    x1, y1 = min(pix.width - 1, int(rect.x1 * sx)), min(pix.height - 1, int(rect.y1 * sy))
    pts = []
    for x in range(x0, x1 + 1, max(1, (x1 - x0) // 12)):
        pts += [pix.pixel(x, y0), pix.pixel(x, y1)]
    for y in range(y0, y1 + 1, max(1, (y1 - y0) // 12)):
        pts += [pix.pixel(x0, y), pix.pixel(x1, y)]
    if not pts:
        return (1, 1, 1)
    bins = [tuple(v // 24 for v in p[:3]) for p in pts]
    try:
        top = statistics.mode(bins)
    except statistics.StatisticsError:
        top = bins[0]
    same = [p[:3] for p, b in zip(pts, bins) if b == top]
    return tuple(sum(p[i] for p in same) / len(same) / 255 for i in range(3))


def _balloon_box(pix, rect, page_rect, bg, tol=40):
    """Área livre do balão em volta do texto: a partir do centro, anda para os lados e para cima/baixo enquanto a
    cor é a do fundo do balão; usa 75% disso (o balão costuma ser oval). Nunca menor que a área do texto."""
    sx = pix.width / page_rect.width
    sy = pix.height / page_rect.height
    target = [int(v * 255) for v in bg]

    def same(x, y):
        if not (0 <= x < pix.width and 0 <= y < pix.height):
            return False
        p = pix.pixel(x, y)
        return sum(abs(p[i] - target[i]) for i in range(3)) <= tol

    cx, cy = int((rect.x0 + rect.x1) / 2 * sx), int((rect.y0 + rect.y1) / 2 * sy)

    def run(dx, dy, x, y):
        n = 0
        while same(x + dx, y + dy) and n < 2000:
            x += dx
            y += dy
            n += 1
        return x, y

    # parte da borda da área do texto (o miolo foi coberto, então é tudo fundo)
    left = run(-1, 0, int(rect.x0 * sx), cy)[0]
    right = run(1, 0, int(rect.x1 * sx), cy)[0]
    top = run(0, -1, cx, int(rect.y0 * sy))[1]
    bottom = run(0, 1, cx, int(rect.y1 * sy))[1]
    free = pymupdf.Rect(left / sx, top / sy, right / sx, bottom / sy)
    w, h = free.width * 0.66, free.height * 0.66      # retângulo que cabe dentro de um balão oval
    c = ((free.x0 + free.x1) / 2, (free.y0 + free.y1) / 2)
    box = pymupdf.Rect(c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)
    if box.width < rect.width or box.height < rect.height or box.width > page_rect.width * 0.7:
        return pymupdf.Rect(rect)
    return box | rect


def _fit_text(page, rect, text, color):
    """Escreve a tradução centralizada (na horizontal e na vertical), no maior tamanho que couber."""
    css = ("* {font-family: sans-serif; font-weight: bold; text-align: center; line-height: 1.15;"
           f" color: rgb({int(color[0] * 255)},{int(color[1] * 255)},{int(color[2] * 255)});}}")
    html = "<p>" + (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")) + "</p>"
    scratch = pymupdf.open()
    sp = scratch.new_page(width=page.rect.width, height=page.rect.height)
    big = max(6, min(26, int(rect.height / 2.2)))
    for size in range(big, 4, -1):
        c = css.replace("line-height", f"font-size:{size}px; line-height")
        rc = sp.insert_htmlbox(rect, html, css=c, scale_low=1)
        if rc[0] >= 0:
            off = rc[0] / 2
            page.insert_htmlbox(pymupdf.Rect(rect.x0, rect.y0 + off, rect.x1, rect.y1 + off), html, css=c, scale_low=1)
            return True
        sp.clean_contents()
    page.insert_htmlbox(rect, html, css=css, scale_low=0.3)
    return False


def translate_page(doc, pno, lang, path, progress=None):
    """Traduz os balões de uma página (altera o documento). Devolve quantos balões traduziu."""
    page = doc[pno]
    words = _words(page, lang)
    bl = balloons(words)
    if not bl:
        return 0
    texts = [t for _r, t in bl]
    out = traducao.translate_paragraphs(texts, path, dst="pt")
    pix = page.get_pixmap(dpi=72)
    n = 0
    for (rect, src), dst in zip(bl, out):
        dst = dialog_br((dst or "").strip())
        if not dst or dst == src:
            continue
        cover = (rect + (-3, -2, 3, 2)) & page.rect
        bg = _bg_color(pix, cover + (-2, -2, 2, 2), page.rect)
        lum = 0.3 * bg[0] + 0.59 * bg[1] + 0.11 * bg[2]
        fg = (0, 0, 0) if lum > 0.5 else (1, 1, 1)
        page.draw_rect(cover, color=None, fill=bg, overlay=True)
        # usa mais espaço do balão: vai até onde a cor do fundo continua (sem passar da borda desenhada)
        box = _balloon_box(pix, cover, page.rect, bg)
        # texto vertical (japonês): área estreita e alta — alarga para caber a frase na horizontal
        if box.height > 2.2 * box.width:
            c = (box.x0 + box.x1) / 2
            w = min(page.rect.width * 0.4, box.height * 0.8)
            box = pymupdf.Rect(c - w / 2, box.y0, c + w / 2, box.y1) & page.rect
        _fit_text(page, box + (1, 1, -1, -1), dst, fg)
        n += 1
        if progress:
            progress(n, len(bl))
    return n
