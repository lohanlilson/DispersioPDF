"""Tradução offline e gratuita (modelos abertos do Argos Translate, rodando com CTranslate2).

O pacote de cada idioma (~60 MB) é baixado uma vez, na primeira tradução, e fica na pasta do programa.
Sem pacote direto (ex.: francês → português), traduz passando pelo inglês.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import urllib.request
import zipfile

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DispersioPDF"

NAMES = {"pt": "português", "en": "inglês", "es": "espanhol", "fr": "francês", "de": "alemão", "it": "italiano",
         "zh": "chinês", "ja": "japonês", "ru": "russo", "nl": "holandês", "pl": "polonês", "ko": "coreano",
         "ar": "árabe", "tr": "turco", "sv": "sueco", "uk": "ucraniano", "ca": "catalão"}

# o modelo aberto de português usa grafia de Portugal em alguns termos: ajusta para o Brasil
PT_BR = [(r"\bcrónic", "crônic"), (r"\bfacto\b", "fato"), (r"\bfactos\b", "fatos"), (r"\bequipa\b", "equipe"),
         (r"\bequipas\b", "equipes"), (r"\butilizador", "usuário"), (r"\butilizar\b", "usar"), (r"\butiliza", "usa"),
         (r"\bregisto", "registro"), (r"\bcontacto", "contato"), (r"\bactual", "atual"), (r"\bactividade", "atividade"),
         (r"\bdirecção\b", "direção"), (r"\bprojecto", "projeto"), (r"\bobjectivo", "objetivo"), (r"\bóptim", "ótim"),
         (r"\bseleccion", "selecion"), (r"\bacção\b", "ação"), (r"\bacções\b", "ações"), (r"\bfactor", "fator"),
         (r"\bgénero", "gênero"), (r"\bfenómeno", "fenômeno"), (r"\bquilómetro", "quilômetro"),
         (r"\bprémio", "prêmio"), (r"\btónus\b", "tônus"), (r"\banónimo", "anônimo"), (r"\bsinónimo", "sinônimo"),
         (r"\beconómic", "econômic"), (r"\bgenómic", "genômic"), (r"\bautónom", "autônom"), (r"\bcomboio", "trem"),
         (r"\btelemóvel", "celular"), (r"\becrã\b", "tela"), (r"\bficheiro", "arquivo"), (r"\bdesporto", "esporte"),
         (r"\bpequeno-almoço", "café da manhã"), (r"\bautocarro", "ônibus"), (r"\bfacturação", "faturamento")]

def pt_br(t):
    """Troca termos de Portugal pelos do Brasil, mantendo a maiúscula inicial."""
    for a, b in PT_BR:
        t = re.sub(a, lambda m, b=b: b[0].upper() + b[1:] if m.group()[0].isupper() else b, t, flags=re.I)
    return t


_STOP = {
    "en": "the of and to in is that for with as are was on by this be from which an or were at have has not but".split(),
    "pt": "de que e o a os as do da dos das em para com não uma um por se no na é ao como mais foi são".split(),
    "es": "de la que el en y los las del se por un una para con no es al lo como más fue son".split(),
    "fr": "de la le et les des en un une du est que pour dans qui par sur pas au avec sont ce".split(),
    "de": "der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch".split(),
    "it": "di e il la che in per un una del della le non con è sono si da al gli".split(),
}


def detect(text: str) -> str | None:
    """Idioma do texto (palavras mais comuns); None se não der para saber."""
    if len(re.findall(r"[一-鿿]", text)) > 30:
        return "zh"
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    if len(words) < 12:
        return None
    score = {k: sum(1 for w in words if w in set(v)) for k, v in _STOP.items()}
    best = max(score, key=score.get)
    second = sorted(score.values())[-2]
    return best if score[best] >= max(3, len(words) * 0.08) and score[best] > second * 1.3 else None


def system_language() -> str:
    try:
        from PySide6.QtCore import QLocale
        code = QLocale.system().name()[:2].lower()
    except Exception:
        code = "pt"
    return code if code in NAMES else "pt"


# ------------------------------------------------------------------ modelos
def models_dir() -> str:
    try:
        from PySide6.QtCore import QStandardPaths
        d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    except Exception:
        d = ""
    return os.path.join(d or os.path.expanduser("~"), "tradutor")


def _installed(src, dst):
    d = os.path.join(models_dir(), f"{src}_{dst}")
    return d if os.path.isfile(os.path.join(d, "model", "model.bin")) else None


_index_cache = None


def index():
    global _index_cache
    if _index_cache is None:
        req = urllib.request.Request(INDEX_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            _index_cache = json.load(r)
    return _index_cache


def _pairs_available():
    try:
        return {(e["from_code"], e["to_code"]): e for e in index()}
    except Exception:
        return {}


def route(src, dst):
    """Sequência de pacotes para traduzir src → dst: direto ou passando pelo inglês. None se não houver."""
    if src == dst:
        return []
    have = lambda a, b: _installed(a, b) or (a, b) in _pairs_available()  # noqa: E731
    if have(src, dst):
        return [(src, dst)]
    if src != "en" and dst != "en" and have(src, "en") and have("en", dst):
        return [(src, "en"), ("en", dst)]
    return None


def missing(path):
    return [p for p in path if not _installed(*p)]


def download(pair, progress=None, cancel=lambda: False):
    """Baixa e instala o pacote src→dst. progress(baixado, total)."""
    src, dst = pair
    e = _pairs_available().get(pair)
    if not e:
        raise RuntimeError(f"Não há pacote de tradução {NAMES.get(src, src)} → {NAMES.get(dst, dst)}.")
    url = next(u for u in e["links"] if u.startswith("http"))
    os.makedirs(models_dir(), exist_ok=True)
    tmp = os.path.join(models_dir(), f"{src}_{dst}.download")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            if cancel():
                raise RuntimeError("cancelado")
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
            got += len(b)
            if progress:
                progress(got, total)
    out = os.path.join(models_dir(), f"{src}_{dst}")
    work = out + ".tmp"
    shutil.rmtree(work, ignore_errors=True)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(work)
    os.remove(tmp)
    inner = next((os.path.join(work, x) for x in os.listdir(work) if os.path.isdir(os.path.join(work, x, "model"))), work)
    shutil.rmtree(out, ignore_errors=True)
    shutil.move(inner, out)
    shutil.rmtree(work, ignore_errors=True)
    return out


# ------------------------------------------------------------------ tradução
_engines = {}
_lock = threading.Lock()


class _Engine:
    def __init__(self, d):
        import ctranslate2
        import sentencepiece as spm
        threads = max(1, min(4, (os.cpu_count() or 2) - 1))
        self.tr = ctranslate2.Translator(os.path.join(d, "model"), device="cpu", compute_type="int8",
                                         inter_threads=1, intra_threads=threads)
        self.sp = spm.SentencePieceProcessor(model_file=os.path.join(d, "sentencepiece.model"))

    def run(self, sentences):
        toks = [self.sp.encode(s, out_type=str) for s in sentences]
        res = self.tr.translate_batch(toks, beam_size=2, max_batch_size=16, max_decoding_length=512)
        return ["".join(r.hypotheses[0]).replace("▁", " ").strip() for r in res]


def release():
    """Libera os tradutores antes de o Python encerrar (no Windows, destruí-los no fim do processo pode travar)."""
    import sys
    dt = sys.modules.get("dispersio.doctab")
    if dt is not None:
        dt.stop_background()          # primeiro termina as traduções em andamento
    with _lock:
        for e in _engines.values():
            try:
                e.tr.unload_model()
            except Exception:
                pass
        _engines.clear()


import atexit as _atexit
_atexit.register(release)


def _engine(pair):
    with _lock:
        if pair not in _engines:
            d = _installed(*pair)
            if not d:
                raise RuntimeError("Pacote de tradução não instalado.")
            _engines[pair] = _Engine(d)
        return _engines[pair]


_ABBR = r"\b(?:et al|e\.g|i\.e|Fig|Figs|Eq|Eqs|Ref|Refs|vs|approx|ca|cf|Dr|Mr|Mrs|Ms|Prof|No|Vol|pp|Sr|Sra|Jr|St|Inc|Ltd|sp|spp)"


def sentences(text):
    """Divide em frases sem quebrar em abreviações (et al., Fig., e.g.)."""
    prot = re.sub(_ABBR + r"\.", lambda m: m.group().replace(".", "․"), text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9(\"“])", prot)
    return [p.replace("․", ".").strip() for p in parts if p.strip()]


_KEEP = re.compile(r"^[\d\s.,;:()\[\]%±×=<>+\-–/·*]+$")

# ------------------------------------------------------------------ citações: fora da tradução, de volta no lugar
_SUP = ""   # marca de número sobrescrito (nota/citação) dentro do texto:  12,15 
_SUP_END = ""
_SUP_RE = re.compile(_SUP + "([^" + _SUP_END + "]*)" + _SUP_END)
_SUPER = str.maketrans("0123456789,-–", "⁰¹²³⁴⁵⁶⁷⁸⁹˒⁻⁻")
_CITE_BRACKET = re.compile(r"\s?\[\s*\d+[a-z]?(?:\s*[-–,;]\s*\d+[a-z]?)*\s*\]")
_CITE_AUTHOR = re.compile(r"\s?\((?=[^()]*\b(?:19|20)\d{2}[a-z]?\b)"
                          r"(?=[^()]*[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\-]+(?:\s+et\s+al\.?|\s+(?:and|&|e|y)\s+[A-ZÀ-Ý]|,|\s+(?:19|20)\d{2}))"
                          r"[^()]{3,240}\)")


def split_citations(sentence):
    """Tira citações ([12], (Silva et al., 2020), números sobrescritos) da frase. Devolve (frase limpa, citações)."""
    cites = []

    def take(m):
        cites.append(m.group().strip())
        return " "
    s = _SUP_RE.sub(lambda m: (cites.append(_SUP + m.group(1) + _SUP_END), " ")[1], sentence)
    s = _CITE_BRACKET.sub(take, s)
    s = _CITE_AUTHOR.sub(take, s)
    s = re.sub(r"\s+([.,;:!?)])", r"\1", re.sub(r"\s{2,}", " ", s)).strip()
    return s, cites


def join_citations(text, cites):
    """Devolve as citações no fim da frase traduzida, antes do ponto final."""
    if not cites:
        return text
    m = re.match(r"^(.*?)([.!?:;]*[\"”»)]*)$", text.rstrip(), re.S)
    body, end = (m.group(1), m.group(2)) if m else (text, "")
    out = body
    for c in cites:
        if c.startswith(_SUP):
            out += c[1:-1].strip().translate(_SUPER)
        else:
            out += " " + c
    return out + end


def plain(text):
    """Texto para exibir: sobrescritos como ¹², sem as marcas internas."""
    return _SUP_RE.sub(lambda m: m.group(1).strip().translate(_SUPER), text)


def translate_paragraphs(paras, path, dst=None, glossary=None):
    """Traduz parágrafos seguindo a rota de pacotes. Citações e números sobrescritos ficam fora da tradução e voltam
    no fim de cada frase; números, fórmulas e referências curtas ficam iguais."""
    out = []
    for para in paras:
        if not para.strip() or _KEEP.match(plain(para)) or len(re.findall(r"[A-Za-zÀ-ÿ]", plain(para))) < 3:
            out.append(plain(para))
            continue
        pieces = [split_citations(s) for s in sentences(para)]
        todo = [i for i, (c, _) in enumerate(pieces) if len(re.findall(r"[A-Za-zÀ-ÿ]", c)) >= 2]
        done = {}
        if todo:
            sents = [pieces[i][0] for i in todo]
            for pair in path:
                sents = _engine(pair).run(sents)
            done = dict(zip(todo, sents))
        res = []
        for i, (clean, cites) in enumerate(pieces):
            res.append(join_citations(done.get(i, clean), cites))
        t = " ".join(r for r in res if r)
        if (dst or path[-1][1]) == "pt":
            t = pt_br(t)
        for k, v in (glossary or {}).items():
            t = re.sub(r"\b" + re.escape(k) + r"\b", v, t, flags=re.I)
        out.append(t)
    return out


# ------------------------------------------------------------------ leitura do documento: ordem, cabeçalhos, referências
from dataclasses import dataclass, field as _field


@dataclass
class Block:
    page: int
    rect: object
    text: str               # com as marcas de sobrescrito
    size: float = 10.0
    bold: bool = False
    keep: bool = False      # não traduzir (referências, cabeçalho/rodapé, números)
    cont: bool = False      # continua o parágrafo anterior (outra coluna ou página)
    why: str = ""

    @property
    def shown(self):
        return plain(self.text)


_REF_HEAD = re.compile(r"^\s*(?:\d+\.?\s*)?(?:references?(?:\s+list)?|bibliography|literature\s+cited|works\s+cited|"
                       r"refer[êe]ncias(?:\s+bibliogr[áa]ficas)?|bibliografia|referencias|r[ée]f[ée]rences|literatur(?:verzeichnis)?|"
                       r"riferimenti(?:\s+bibliografici)?)\s*:?\s*$", re.I)
_AFTER_REFS = re.compile(r"^\s*(?:\d+\.?\s*)?(?:appendix|appendices|ap[êe]ndices?|anexos?|supplementary|supporting\s+information|"
                         r"material\s+suplementar)\b", re.I)
_PAGE_NO = re.compile(r"^\s*(?:p(?:age|ágina|ag)?\.?\s*)?\d{1,4}(?:\s*(?:of|de|/)\s*\d{1,4})?\s*$", re.I)


def _raw_blocks(page, pno):
    import pymupdf
    out = []
    d = page.get_text("dict", flags=pymupdf.TEXT_DEHYPHENATE)
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        lines = []
        spans_all = []
        for ln in b["lines"]:
            spans = [sp for sp in ln["spans"] if sp["text"]]
            if not spans:
                continue
            big = max(sp["size"] for sp in spans)
            parts = []
            for sp in spans:
                t = sp["text"]
                sup = (sp["flags"] & 1 or sp["size"] < big * 0.78) and re.fullmatch(r"\s*[\d,;\-–*†‡§]{1,15}\s*", t) \
                    and re.search(r"\d", t)
                if sup:
                    parts.append(_SUP + t.strip() + _SUP_END)
                else:
                    parts.append(t)
                    spans_all.append(sp)
            s = "".join(parts).strip()
            if s:
                lines.append(s)
        if not lines:
            continue
        txt = ""
        for ln in lines:
            if txt.endswith("-") and ln[:1].islower():
                txt = txt[:-1] + ln
            else:
                txt = (txt + " " + ln) if txt else ln
        txt = re.sub(r"[ \t]+", " ", txt).strip()
        size = max((sp["size"] for sp in spans_all), default=10)
        chars = sum(len(sp["text"]) for sp in spans_all) or 1
        bold = sum(len(sp["text"]) for sp in spans_all if sp["flags"] & 16 or "bold" in sp["font"].lower()) > chars / 2
        out.append(Block(pno, pymupdf.Rect(b["bbox"]), txt, size, bold))
    return out


def _reading_order(blocks, width, height=None):
    """Ordem de leitura em páginas de duas colunas: o que ocupa a largura toda separa faixas; em cada faixa,
    primeiro a coluna da esquerda, depois a da direita."""
    mid = width / 2

    def side(b):
        x0, x1 = b.rect.x0, b.rect.x1
        if height and (b.rect.y1 < height * 0.085 or b.rect.y0 > height * 0.915):
            return "F"                                   # cabeçalho / rodapé
        if x0 < mid - width * 0.04 and x1 > mid + width * 0.04:
            return "F"                                   # ocupa a largura toda
        cx = (x0 + x1) / 2
        if abs(cx - mid) < width * 0.03:
            return "F"                                   # centralizado (título, número da página)
        return "L" if cx < mid else "R"
    if sum(side(b) == "L" for b in blocks) < 2 or sum(side(b) == "R" for b in blocks) < 2:
        return sorted(blocks, key=lambda b: (round(b.rect.y0), b.rect.x0))
    out, band = [], []
    for b in sorted(blocks, key=lambda b: (b.rect.y0, b.rect.x0)):
        if side(b) == "F":
            out += sorted([x for x in band if side(x) == "L"], key=lambda x: x.rect.y0)
            out += sorted([x for x in band if side(x) == "R"], key=lambda x: x.rect.y0)
            band = []
            out.append(b)
        else:
            band.append(b)
    out += sorted([x for x in band if side(x) == "L"], key=lambda x: x.rect.y0)
    out += sorted([x for x in band if side(x) == "R"], key=lambda x: x.rect.y0)
    return out


def analyze(doc, pages=None):
    """{página: [Block]} na ordem de leitura, marcando o que não se traduz e o que continua o parágrafo anterior."""
    pages = list(pages) if pages is not None else list(range(doc.page_count))
    per = {}
    for p in pages:
        pg = doc[p]
        per[p] = _reading_order(_raw_blocks(pg, p), pg.rect.width, pg.rect.height)
    # cabeçalho e rodapé que se repetem (nome da revista, DOI, número da página)
    from collections import Counter
    key = lambda b: re.sub(r"\d+", "#", plain(b.text).lower()).strip()  # noqa: E731
    edge = lambda b: b.rect.y1 < doc[b.page].rect.height * 0.085 or b.rect.y0 > doc[b.page].rect.height * 0.915  # noqa: E731
    cnt = Counter(key(b) for bl in per.values() for b in bl if edge(b))
    rep = max(2, int(len(pages) * 0.3 + 0.5))
    for bl in per.values():
        for b in bl:
            t = plain(b.text)
            if _PAGE_NO.match(t):
                b.keep, b.why = True, "número da página"
            elif edge(b) and len(pages) >= 2 and cnt[key(b)] >= rep:
                b.keep, b.why = True, "cabeçalho/rodapé"
            elif _KEEP.match(t) or len(re.findall(r"[A-Za-zÀ-ÿ]", t)) < 3:
                b.keep, b.why = True, "números"
    # lista de referências: do título "References" em diante (até um apêndice)
    in_refs = False
    for p in pages:
        for b in per[p]:
            t = plain(b.text)
            if _REF_HEAD.match(t):
                in_refs = True
                continue
            if in_refs and _AFTER_REFS.match(t) and len(t) < 80:
                in_refs = False
                continue
            if in_refs and not b.keep:
                b.keep, b.why = True, "referências"
    # parágrafo que continua na outra coluna ou na página seguinte
    prev = None
    for p in pages:
        for b in per[p]:
            if b.keep:
                continue
            t = plain(b.text)
            if prev is not None and not re.search(r"[.!?:”\"»)]\s*$", plain(prev.text)) and t[:1].islower() \
                    and abs(prev.size - b.size) < 1.5 and not prev.bold:
                b.cont = True
            prev = b
    return per


def _split_like(text, parts):
    """Divide a tradução de um parágrafo que atravessa blocos, na proporção do original, sempre num espaço."""
    if len(parts) == 1:
        return [text]
    lens = [max(1, len(plain(x))) for x in parts]
    total = sum(lens)
    cuts, acc, last = [], 0, 0
    for n in lens[:-1]:
        acc += n
        pos = int(len(text) * acc / total)
        sp = text.rfind(" ", last + 1, pos + 1)
        if sp <= last:
            sp = text.find(" ", pos)
        if sp <= last:
            sp = max(last, min(pos, len(text)))
        cuts.append(sp)
        last = sp
    out, prev = [], 0
    for c in cuts + [len(text)]:
        out.append(text[prev:c].strip())
        prev = c
    return out


def translate_document(doc, path, dst, on_page, pages=None, cancel=lambda: False, glossary=None):
    """Traduz o documento em ordem de leitura e chama on_page(página, [(Block, tradução ou None)]) quando cada página
    termina. Parágrafos que atravessam colunas/páginas são traduzidos inteiros e redivididos."""
    per = analyze(doc, pages)
    order = [b for p in sorted(per) for b in per[p]]
    units, cur = [], None
    for b in order:
        if b.keep:
            continue
        if b.cont and cur:
            cur.append(b)
        else:
            cur = [b]
            units.append(cur)
    left = {p: sum(1 for u in units if any(b.page == p for b in u)) for p in per}
    result = {}

    def flush():
        for p in sorted(per):
            if p in done_pages:
                continue
            if left[p] > 0:
                break
            done_pages.add(p)
            on_page(p, [(b, result.get(id(b))) for b in per[p]])
    done_pages = set()
    flush()
    for u in units:
        if cancel():
            return
        text = ""
        for b in u:
            t = b.text
            if text.endswith("-") and t[:1].islower():
                text = text[:-1] + t
            else:
                text = (text + " " + t) if text else t
        tr = translate_paragraphs([text], path, dst, glossary)[0]
        for b, t in zip(u, _split_like(tr, [b.text for b in u])):
            result[id(b)] = t
        for p in {b.page for b in u}:
            left[p] -= 1
        flush()


def overlay_page(page, items):
    """Escreve a tradução por cima do texto original da página (imagens e desenhos ficam). items: [(Block, tradução)]."""
    import pymupdf
    todo = [(b, t) for b, t in items if t and not b.keep]
    if not todo:
        return
    for b, _t in todo:
        page.add_redact_annot(b.rect, fill=None)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    others = [b.rect for b, _ in items]
    for b, t in todo:
        r = pymupdf.Rect(b.rect)
        if r.height < b.size * 2:      # uma linha só (título): pode crescer para a direita até a margem ou o próximo bloco
            limit = page.rect.width - 36
            for o in others:
                if o is not b.rect and o.x0 > r.x1 and o.y0 < r.y1 and o.y1 > r.y0:
                    limit = min(limit, o.x0 - 4)
            r.x1 = max(r.x1, limit)
        html = "<p>" + (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")) + "</p>"
        css = ("body, p {margin: 0; padding: 0;} "
               f"p {{font-family: sans-serif; font-size: {max(5.0, b.size * 0.95):.1f}px; line-height: 1.15;"
               f"{' font-weight: bold;' if b.bold else ''}}}")
        try:
            page.insert_htmlbox(r, html, css=css, scale_low=0.4)
        except Exception:
            page.insert_textbox(r, t, fontsize=max(5.0, b.size * 0.85))


def page_paragraphs(page):
    """[(retângulo, parágrafo, tamanho da letra, negrito)] da página (compatibilidade)."""
    return [(b.rect, b.shown, b.size, b.bold)
            for b in _reading_order(_raw_blocks(page, page.number), page.rect.width, page.rect.height)]


def translated_pdf(doc, pages_tr, progress=None):
    """PDF com o texto traduzido no lugar do original (imagens e desenhos ficam).
    pages_tr: {página: [(rect, tradução, tamanho, negrito)]}."""
    import pymupdf
    out = pymupdf.open()
    out.insert_pdf(doc)
    for k, (pno, blocks) in enumerate(sorted(pages_tr.items())):
        if progress:
            progress(k, len(pages_tr))
        page = out[pno]
        for rect, *_ in blocks:
            page.add_redact_annot(rect, fill=None)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        others = [b[0] for b in blocks]
        for rect, t, size, bold in blocks:
            r = pymupdf.Rect(rect)
            if r.height < size * 2:      # uma linha só (título): pode crescer para a direita até a margem ou o próximo bloco
                limit = page.rect.width - 36
                for o in others:
                    if o is not rect and o.x0 > r.x1 and o.y0 < r.y1 and o.y1 > r.y0:
                        limit = min(limit, o.x0 - 4)
                r.x1 = max(r.x1, limit)
            html = "<p>" + (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")) + "</p>"
            css = ("body, p {margin: 0; padding: 0;} "
                   f"p {{font-family: sans-serif; font-size: {max(5.0, size * 0.95):.1f}px; line-height: 1.15;"
                   f"{' font-weight: bold;' if bold else ''}}}")
            try:
                page.insert_htmlbox(r, html, css=css, scale_low=0.4)
            except Exception:
                page.insert_textbox(r, t, fontsize=max(5.0, size * 0.85))
    return out
