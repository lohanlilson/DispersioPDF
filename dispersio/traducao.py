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
PT_BR = [(r"\belectr", "eletr"), (r"\bacto\b", "ato"), (r"\bactos\b", "atos"), (r"\bcrónic", "crônic"), (r"\bfacto\b", "fato"), (r"\bfactos\b", "fatos"), (r"\bequipa\b", "equipe"),
         (r"\bequipas\b", "equipes"), (r"\butilizador", "usuário"), (r"\butilizar\b", "usar"), (r"\butiliza", "usa"),
         (r"\bregisto", "registro"), (r"\bcontacto", "contato"), (r"\bactual", "atual"), (r"\bactividade", "atividade"),
         (r"\bdirecção\b", "direção"), (r"\bprojecto", "projeto"), (r"\bobjectivo", "objetivo"), (r"\bóptim", "ótim"),
         (r"\bseleccion", "selecion"), (r"\bacção\b", "ação"), (r"\bacções\b", "ações"), (r"\bfactor", "fator"),
         (r"\bgénero", "gênero"), (r"\bfenómeno", "fenômeno"), (r"\bquilómetro", "quilômetro"),
         (r"\bprémio", "prêmio"), (r"\btónus\b", "tônus"), (r"\banónimo", "anônimo"), (r"\bsinónimo", "sinônimo"),
         (r"\beconómic", "econômic"), (r"\bgenómic", "genômic"), (r"\bautónom", "autônom"), (r"\bcomboio", "trem"),
         (r"\btelemóvel", "celular"), (r"\becrã\b", "tela"), (r"\bficheiro", "arquivo"), (r"\bdesporto", "esporte"),
         (r"\bpequeno-almoço", "café da manhã"), (r"\bautocarro", "ônibus"), (r"\bfacturação", "faturamento")]

# acentuação de Portugal em palavras eruditas: génico → gênico, anatómico → anatômico, fenómeno → fenômeno
_PT_ACCENT = [(re.compile(r"(\w)é(nic[oa]s?|nio|nios|nese|neses|mur|mures|nero|neros|nero)\b"), r"\1ê\2"),
              (re.compile(r"(\w)ó(mic[oa]s?|nic[oa]s?|meno|menos|nio|nios|ni[oa]|ni[oa]s|stom[oa]s?)\b"), r"\1ô\2"),
              (re.compile(r"\b(f)acto\b", re.I), r"\1ato"), (re.compile(r"\b(c)ontacto(s?)\b", re.I), r"\1ontato\2"),
              (re.compile(r"\b(a)c(ç|t)(ão|ões|ivo|iva|ivos|ivas|ividade|ividades)\b", re.I), r"\1\2\3"),
              (re.compile(r"\b(e)xcep(ç|t)", re.I), r"\1xce\2")]


def pt_br(t):
    """Troca termos de Portugal pelos do Brasil, mantendo a maiúscula inicial."""
    for a, b in PT_BR:
        t = re.sub(a, lambda m, b=b: b[0].upper() + b[1:] if m.group()[0].isupper() else b, t, flags=re.I)
    for a, b in _PT_ACCENT:
        t = a.sub(b, t)
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
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9(\"“\ue010])", prot)
    return [p.replace("․", ".").strip() for p in parts if p.strip()]


_KEEP = re.compile(r"^[\d\s.,;:()\[\]%±×=<>+\-–/·*]+$")

# ------------------------------------------------------------------ citações: fora da tradução, de volta no lugar
_SUP = ""   # marca de número sobrescrito (nota/citação) dentro do texto:  12,15 
_SUP_END = ""
_SUP_RE = re.compile(_SUP + "([^" + _SUP_END + "]*)" + _SUP_END)
_ITA = "\ue010"        # trecho em itálico (nome científico, termo estrangeiro): não se traduz e volta em itálico
_ITA_END = "\ue011"
_ITA_RE = re.compile(_ITA + "([^" + _ITA_END + "]*)" + _ITA_END)
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
    return _SUP_RE.sub(lambda m: m.group(1).strip().translate(_SUPER), text).replace(_ITA, "").replace(_ITA_END, "")


# Símbolos que o tradutor perde ou troca por outra coisa (≠ virava "7,6%", √ virava "?"): saem da frase como um
# código que ele copia sem mexer (ZQX1, ZQX2…) e voltam depois.
_SAFE_SYMBOLS = set("†‡§¶•→←↔≤≥±×°αβγδελπσωμ′“”‘’–—…%")
_PH = re.compile(r"ZQX(\d+)")


def _unsafe(ch):
    import unicodedata
    if ch in _SAFE_SYMBOLS or ch.isspace():
        return False
    cat = unicodedata.category(ch)
    return cat in ("Sm", "So", "Sk", "Co") or "\u0370" <= ch <= "\u03ff" or ch in "∗µ℃‰″÷"


def _lost_numbers(src, out):
    from collections import Counter
    a = Counter(re.findall(r"\d+", src))
    b = Counter(re.findall(r"\d+", out))
    return any(b[k] < v for k, v in a.items())


def _protect(text, numbers=False, cites=False):
    """Troca por códigos (ZQX1, ZQX2…) o que o tradutor estraga: símbolos frágeis e, com cites=True, as citações
    ([12], (Silva et al., 2020), números sobrescritos) — assim elas ficam no mesmo lugar da frase traduzida.
    Com numbers=True, também os números (usado só quando o tradutor perdeu algum)."""
    kept = []

    def code(value, glue_after=False, glue_before=False):
        kept.append((value, glue_after, glue_before))
        return f" ZQX{len(kept)} "

    def sub(m):
        nxt = text[m.end():m.end() + 1]
        return code(m.group(0), bool(nxt) and not nxt.isspace())
    if cites:
        text = _SUP_RE.sub(lambda m: code(m.group(1).strip().translate(_SUPER), glue_before=True), text)
        # itálico curto (Vulpes vulpes, in vitro, et al.): fica igual, em itálico
        text = _ITA_RE.sub(lambda m: code(_ITA + m.group(1).strip() + _ITA_END) if 0 < len(m.group(1).split()) <= 4
                           and re.search(r"[A-Za-z]{2}", m.group(1)) else m.group(1), text)
        text = _CITE_BRACKET.sub(lambda m: code(m.group(0).strip()), text)
        text = _CITE_AUTHOR.sub(lambda m: code(m.group(0).strip()), text)
        # sequências de DNA/RNA e códigos longos em maiúsculas (o tradutor embaralha)
        text = re.sub(r"\b[ACGTUN]{10,}\b", lambda m: code(m.group(0)), text)
    if numbers:
        def num(m):
            v = m.group(0)
            if re.fullmatch(r"\d+\.\d+", v):
                v = v.replace(".", ",")  # decimal no padrão brasileiro
            nxt = text[m.end():m.end() + 1]
            return code(v, bool(nxt) and not nxt.isspace() and nxt not in ",.;:)")
        text = re.sub(r"(?<!ZQX)\b\d+(?:[.,]\d+)*", num, text)
    out = re.sub(r"[^\sA-Za-z0-9À-ÖØ-öø-ÿ.,;:!?()\[\]'\"/-](?:\s?[^\sA-Za-z0-9À-ÖØ-öø-ÿ.,;:!?()\[\]'\"/-])*",
                 lambda m: sub(m) if any(_unsafe(c) for c in m.group(0)) else m.group(0), text)
    return re.sub(r" {2,}", " ", out).strip(), kept


def _unprotect(text, kept):
    if not kept:
        return text
    used = set()

    def back(m):
        k = int(m.group(1))
        used.add(k)
        if not 0 < k <= len(kept):
            return ""
        val, after, before = kept[k - 1]
        return ("\x01" if before else "") + val + ("\x00" if after else "")
    out = _PH.sub(back, text)
    out = re.sub(r"\x00\s*", "", out)
    out = re.sub(r"\s*\x01", "", out)
    missing = [kept[k - 1] for k in range(1, len(kept) + 1) if k not in used]
    if missing:  # o tradutor descartou o código: devolve no fim da frase, antes do ponto, para não sumir
        m = re.match(r"^(.*?)([.!?:;]*[\"”»)]*)$", out.rstrip(), re.S)
        body, end = (m.group(1), m.group(2)) if m else (out, "")
        for val, _a, before in missing:
            body += val if before else " " + val
        out = body + end
    out = re.sub(r"\s+([.,;:!?)])", r"\1", out)
    return re.sub(r"\(\s+", "(", out)


def translate_paragraphs(paras, path, dst=None, glossary=None):
    """Traduz parágrafos seguindo a rota de pacotes. Citações e números sobrescritos ficam fora da tradução e voltam
    no fim de cada frase; números, fórmulas e referências curtas ficam iguais."""
    out = []
    for para in paras:
        if not para.strip() or _KEEP.match(plain(para)) or len(re.findall(r"[A-Za-zÀ-ÿ]", plain(para))) < 3:
            out.append(plain(para))
            continue
        sents_src = sentences(para)
        pieces = [split_citations(s) for s in sents_src]
        todo = [i for i, (c, _) in enumerate(pieces) if len(re.findall(r"[A-Za-zÀ-ÿ]", c)) >= 2]
        done = {}
        if todo:
            protected = [_protect(sents_src[i], cites=True) for i in todo]
            sents = [p for p, _ in protected]
            for pair in path:
                sents = _engine(pair).run(sents)
            done = {i: _unprotect(t, kept) for i, t, (_p, kept) in zip(todo, sents, protected)}
            # o tradutor às vezes some com um número ("n = 4, 0.27%" → "n = , 0,27%"): refaz essas frases com os
            # números protegidos
            redo = [i for i in todo if _lost_numbers(plain(sents_src[i]), done[i])]
            if redo:
                prot = [_protect(sents_src[i], numbers=True, cites=True) for i in redo]
                ss = [p for p, _ in prot]
                for pair in path:
                    ss = _engine(pair).run(ss)
                for i, t, (_p, kept) in zip(redo, ss, prot):
                    t = _unprotect(t, kept)
                    if not _lost_numbers(plain(sents_src[i]), t):
                        done[i] = t
        res = []
        for i, (clean, cites) in enumerate(pieces):
            res.append(done[i] if i in done else join_citations(clean, cites))
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
    color: int = 0          # cor do texto original (0xRRGGBB)
    serif: bool = False     # letra com serifa (Times, Minion…)
    justify: bool = False   # parágrafo justificado
    center: bool = False    # linhas centralizadas (título, legenda)
    cell: bool = False      # célula de tabela (não cresce para os lados)
    math: float = 0.0       # parte do texto escrita em fonte de fórmula (CMMI, CMSY, Symbol…)
    lead: str = ""          # título em negrito no começo do parágrafo ("Normalization.")
    lead_tr: str = ""
    rich: str = ""          # tradução com as marcas de itálico (para desenhar)
    nlines: int = 1

    @property
    def shown(self):
        return plain(self.text)


_REF_HEAD = re.compile(r"^\s*(?:\d+\.?\s*)?(?:references?(?:\s+list)?|bibliography|literature\s+cited|works\s+cited|"
                       r"refer[êe]ncias(?:\s+bibliogr[áa]ficas)?|bibliografia|referencias|r[ée]f[ée]rences|literatur(?:verzeichnis)?|"
                       r"riferimenti(?:\s+bibliografici)?)\s*:?\s*$", re.I)
_AFTER_REFS = re.compile(r"^\s*(?:\d+\.?\s*)?(?:appendix|appendices|ap[êe]ndices?|anexos?|supplementary|supporting\s+information|"
                         r"material\s+suplementar)\b", re.I)
_PAGE_NO = re.compile(r"^\s*(?:p(?:age|ágina|ag)?\.?\s*)?\d{1,4}(?:\s*(?:of|de|/)\s*\d{1,4})?\s*$", re.I)


_SERIF = re.compile(r"times|serif|roman|minion|georgia|cambria|garamond|palatino|book|charter|nimbusrom|cmr|lmroman|"
                    r"stix|mathpazo|utopia|baskerville|caslon|liberationserif|dejavuserif|warnock|adv[a-z]*tim", re.I)


# negrito pelo nome da fonte (muitos PDFs de revista não marcam o negrito: "…AdvTT.B", "Arial,Bold", "CMBX10")
_BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi|[.,-]b$|-bd|bd$|cmbx|medi", re.I)


_MATH_FONT = re.compile(r"cmmi|cmsy|cmex|cmbsy|msam|msbm|math|symbol|eusm|rsfs|stixgeneral-italic|mtmi|mtsy|"
                        r"lmmath|txsy|txmi|pxmi|cambria.?math|euclid", re.I)
_SERIF_CACHE = {}


_GLYPH_CACHE = {}


def _glyph_rows(page, name):
    """Largura (em pixels) de cada linha do desenho da letra "l" (ou "I") da fonte, em tamanho 100.
    Serve para descobrir serifa e negrito quando o nome da fonte vem embaralhado ("TvjcpxAdvTT86d…")."""
    key = (id(page.parent), name)
    if key in _GLYPH_CACHE:
        return _GLYPH_CACHE[key]
    rows = None
    try:
        import pymupdf
        xref = next((f[0] for f in page.get_fonts() if f[3].split("+")[-1] == name or f[3] == name), None)
        if xref:
            _n, _e, _t, buf = page.parent.extract_font(xref)
            if buf:
                font = pymupdf.Font(fontbuffer=buf)
                for ch in "lI":
                    if not font.has_glyph(ord(ch)):
                        continue
                    tmp = pymupdf.open()
                    pg = tmp.new_page(width=120, height=140)
                    tw = pymupdf.TextWriter(pg.rect)
                    tw.append((20, 110), ch, font=font, fontsize=100)
                    tw.write_text(pg)
                    pix = pg.get_pixmap(alpha=False)
                    rr = [n for n in (sum(1 for x in range(pix.width) if pix.pixel(x, y)[0] < 128)
                                      for y in range(pix.height)) if n]
                    if len(rr) > 20:
                        rows = rr
                        break
    except Exception:
        rows = None
    _GLYPH_CACHE[key] = rows
    return rows


def _font_is_serif(page, name):
    """Serifa pelo nome; se o nome for embaralhado, pelo desenho do "l": com serifa, a base é bem mais larga."""
    if _SERIF.search(name):
        return True
    if re.search(r"sans|helvet|arial|myriad|frutiger|calibri|verdana|segoe|roboto|open|lato|source|gothic|univers|"
                 r"futura|gill|tahoma|liberationsans|dejavusans|cmss", name, re.I):
        return False
    rows = _glyph_rows(page, name)
    return bool(rows) and max(rows[-4:]) > sorted(rows)[len(rows) // 2] * 1.8


def _font_is_bold(page, name):
    """Negrito pelo nome; se não der, pela grossura da haste do "l" (negrito ≥ 11 px em tamanho 100)."""
    if _BOLD_FONT.search(name):
        return True
    if re.search(r"regular|roman|book|light|-lt$|regu|medium?$", name, re.I) or re.search(r"\.i$|ital|oblique", name, re.I):
        return False
    rows = _glyph_rows(page, name)
    return bool(rows) and sorted(rows)[len(rows) // 2] >= 11


def _family(spans):
    """Família da fonte da linha, sem prefixo de subconjunto nem estilo ("ABCDEF+MinionPro-Bold" → "minionpro")."""
    if not spans:
        return ""
    name = max(spans, key=lambda sp: len(sp["text"].strip()))["font"].split("+")[-1].lower()  # fonte da maior parte
    return re.sub(r"\d+$", "", re.split(r"[-,.]", name)[0].replace("bold", "").replace("italic", ""))


def _merge_italic(t):
    """Junta trechos em itálico vizinhos ("Vulpes" + " " + "vulpes" → um trecho só)."""
    return re.sub(_ITA_END + r"(\s*)" + _ITA, r"\1", t)


def _line_info(ln, page=None):
    """(texto com marcas de sobrescrito, tamanho, negrito?, spans de texto normal) de uma linha do PyMuPDF."""
    spans = [sp for sp in ln["spans"] if sp["text"]]
    if not spans:
        return None
    big = max(sp["size"] for sp in spans)
    parts, normal = [], []
    for sp in spans:
        t = sp["text"].replace("\u02da", "°")  # anel sobrescrito usado como grau (50.5˚C)
        sup = (sp["flags"] & 1 or sp["size"] < big * 0.78) and re.fullmatch(r"\s*[\d,;\-–*†‡§]{1,15}\s*", t) \
            and re.search(r"\d", t)
        if sup:
            parts.append(_SUP + t.strip() + _SUP_END)
        else:
            ital = (sp["flags"] & 2 or re.search(r"italic|oblique|-it$|\.i$|ital$|-ti$", sp["font"], re.I)) and \
                not _MATH_FONT.search(sp["font"]) and re.search(r"[A-Za-z]{2}", t)
            if ital:
                lead_sp = t[:len(t) - len(t.lstrip())]
                trail = t[len(t.rstrip()):]
                parts.append(lead_sp + _ITA + t.strip() + _ITA_END + trail)
            else:
                parts.append(t)
            normal.append(sp)
    text = _merge_italic("".join(parts).strip())
    if not text or not normal:
        return None
    chars = sum(len(sp["text"].strip()) for sp in normal) or 1
    bold = sum(len(sp["text"].strip()) for sp in normal
               if sp["flags"] & 16 or (_font_is_bold(page, sp["font"]) if page is not None else _BOLD_FONT.search(sp["font"]))) \
        > chars * 0.7
    size = max(sp["size"] for sp in normal)
    return text, size, bold, normal


def _rows(lines):
    """Junta as "linhas" do PyMuPDF que estão na mesma altura. Em texto justificado o espaço entre palavras fica
    largo e o PyMuPDF quebra uma linha em vários pedaços; aqui eles voltam a ser uma linha só, na ordem da esquerda
    para a direita e com o espaço entre as palavras."""
    rows = []
    for ln in lines:
        b = ln["bbox"]
        if ln.get("dir", (1, 0))[0] < 0.9:
            rows.append(dict(ln))
            continue
        hit = None
        for r in rows[-3:]:
            rb = r["bbox"]
            if r.get("dir", (1, 0))[0] < 0.9:
                continue
            h = min(b[3] - b[1], rb[3] - rb[1])
            if h > 0 and min(b[3], rb[3]) - max(b[1], rb[1]) > h * 0.5:
                hit = r
                break
        if hit is None:
            rows.append({"bbox": tuple(b), "spans": list(ln["spans"]), "dir": ln.get("dir", (1, 0))})
        else:
            hb = hit["bbox"]
            hit["bbox"] = (min(hb[0], b[0]), min(hb[1], b[1]), max(hb[2], b[2]), max(hb[3], b[3]))
            hit["spans"] = hit["spans"] + list(ln["spans"])
    out = []
    for r in rows:
        sps = sorted(r["spans"], key=lambda sp: sp["bbox"][0])
        merged = []
        for sp in sps:
            if merged:
                pv = merged[-1]
                gap = sp["bbox"][0] - pv["bbox"][2]
                if gap > sp["size"] * 0.18 and not pv["text"].endswith(" ") and not sp["text"].startswith(" "):
                    merged.append(dict(pv, text=" ", bbox=(pv["bbox"][2], pv["bbox"][1], sp["bbox"][0], pv["bbox"][3])))
            merged.append(sp)
        out.append({"bbox": r["bbox"], "spans": merged, "dir": r["dir"]})
    return out


def _centered(g, rect, page_w):
    """Linhas centralizadas: com várias linhas, os centros coincidem e as margens esquerdas variam; com uma linha só,
    o texto está no meio da página."""
    rs = [r for _li, r in g]
    cx = (rect.x0 + rect.x1) / 2
    if len(rs) >= 2:
        return all(abs((r.x0 + r.x1) / 2 - cx) < rect.width * 0.03 for r in rs) and \
            max(r.x0 for r in rs) - min(r.x0 for r in rs) > rect.width * 0.04 and \
            max(r.x1 for r in rs) - min(r.x1 for r in rs) > rect.width * 0.04
    return abs(cx - page_w / 2) < page_w * 0.02 and rect.width < page_w * 0.8


def _raw_blocks(page, pno):
    """Parágrafos da página. Um bloco do PyMuPDF pode ter título + texto, ou vários parágrafos: separa pelas mudanças
    de tamanho/negrito da letra, pelo espaço entre linhas e pela linha curta que termina a frase."""
    import pymupdf
    from collections import Counter
    out = []
    d = page.get_text("dict")
    # tabelas: cada célula vira um bloco próprio (sem isso, a linha inteira da tabela vira um parágrafo só)
    trects = []
    try:
        # sem linhas desenhadas na página não há tabela com grade (e a busca é a parte lenta da análise)
        if sum(1 for dr in page.get_drawings() for it in dr["items"] if it[0] in ("l", "re")) < 3:
            raise StopIteration
        # pelas linhas da tabela (sem falso positivo em texto corrido); a busca pelo texto completa a área
        # quando a tabela só tem linhas horizontais (estilo de revista)
        def find(**kw):
            try:
                return page.find_tables(use_layout=False, **kw).tables  # mesmo resultado com ou sem pymupdf-layout
            except TypeError:
                return page.find_tables(**kw).tables
        # tabela de verdade: larga (caixinhas de diagrama também viram "tabela") e com texto em várias células
        ruled = [pymupdf.Rect(t.bbox) for t in find() if t.row_count >= 2 and t.col_count >= 2
                 and t.bbox[2] - t.bbox[0] > page.rect.width * 0.25
                 and len(page.get_text("words", clip=t.bbox)) >= 6]
        if ruled:
            textual = [pymupdf.Rect(t.bbox) for t in find(strategy="text")]
            for r in ruled:
                for x in textual:
                    if (r & x).get_area() > r.get_area() * 0.5:
                        r.x0, r.x1 = min(r.x0, x.x0), max(r.x1, x.x1)   # só alarga; a altura é a das linhas da tabela
                trects.append(r)
    except Exception:
        trects = []

    def in_table(r):
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        return any(c in tr for tr in trects)
    # dentro da tabela, cada pedaço de texto separado por um vão largo é uma célula
    allspans = [sp for blk in d["blocks"] if blk.get("type") == 0 for ln in blk["lines"] for sp in ln["spans"]
                if sp["text"].strip()]
    centers = [((sp["bbox"][0] + sp["bbox"][2]) / 2, (sp["bbox"][1] + sp["bbox"][3]) / 2, sp) for sp in allspans]
    for tr in trects:
        words = sorted(page.get_text("words", clip=tr), key=lambda w: (w[1] + w[3]) / 2)
        rows = []                                    # linhas da tabela pela altura (não pelo bloco do PyMuPDF)
        for w in words:
            cy, h = (w[1] + w[3]) / 2, w[3] - w[1]
            if rows and abs(rows[-1][0] - cy) < h * 0.45:
                rows[-1][1].append(w)
            else:
                rows.append([cy, [w]])
        for _cy, ws in rows:
            ws.sort(key=lambda w: w[0])
            seg = [ws[0]]
            segs = []
            for w in ws[1:]:
                if w[0] - seg[-1][2] > (w[3] - w[1]) * 0.5:
                    segs.append(seg)
                    seg = []
                seg.append(w)
            segs.append(seg)
            for k, sg in enumerate(segs):
                r = pymupdf.Rect(sg[0][:4])
                for w in sg[1:]:
                    r |= pymupdf.Rect(w[:4])
                # a célula vai até a próxima coluna (o português é mais comprido)
                r.x1 = max(r.x1, (segs[k + 1][0][0] - 4) if k + 1 < len(segs) else tr.x1)
                inner = pymupdf.Rect(sg[0][:4])
                for w in sg[1:]:
                    inner |= pymupdf.Rect(w[:4])
                ix0, iy0, ix1, iy1 = inner.x0 - 1, inner.y0 - 1, inner.x1 + 1, inner.y1 + 1
                sps = [sp for (cx, cy, sp) in centers if ix0 <= cx <= ix1 and iy0 <= cy <= iy1]
                if not sps:
                    continue
                txt = " ".join(w[4] for w in sg)
                n_all = sum(len(sp["text"].strip()) for sp in sps) or 1
                italic = sum(len(sp["text"].strip()) for sp in sps
                             if sp["flags"] & 2 or re.search(r"italic|oblique|\.i$|-it$", sp["font"], re.I)) >= n_all * 0.7
                bold = all(sp["flags"] & 16 or _BOLD_FONT.search(sp["font"]) for sp in sps)
                blk = Block(pno, r, txt, max(sp["size"] for sp in sps), bold, color=sps[0]["color"],
                            serif=_font_is_serif(page, sps[0]["font"]), nlines=1, cell=True)
                if italic:
                    blk.keep, blk.why = True, "nome científico"   # itálico na tabela: espécie, gênero
                out.append(blk)
    # o PyMuPDF às vezes quebra um parágrafo no meio de uma linha (fórmula no meio do texto): junta de volta o bloco
    # que começa na mesma altura em que o anterior terminou, à direita dele e na mesma coluna
    tblocks = []
    for blk in d["blocks"]:
        if blk.get("type") != 0 or not blk.get("lines"):
            continue
        if tblocks:
            pl = tblocks[-1]["lines"][-1]["bbox"]
            fl = blk["lines"][0]["bbox"]
            h = min(pl[3] - pl[1], fl[3] - fl[1])
            ov = min(pl[3], fl[3]) - max(pl[1], fl[1])
            pb, cb = tblocks[-1]["bbox"], blk["bbox"]
            if h > 0 and ov > h * 0.4 and fl[0] > pl[0] + (pl[2] - pl[0]) * 0.6 and min(pb[2], cb[2]) - max(pb[0], cb[0]) > (cb[2] - cb[0]) * 0.5:
                tblocks[-1] = {"type": 0, "lines": tblocks[-1]["lines"] + blk["lines"],
                               "bbox": (min(pb[0], cb[0]), min(pb[1], cb[1]), max(pb[2], cb[2]), max(pb[3], cb[3]))}
                continue
        tblocks.append(blk)
    for blk in tblocks:
        lines = []
        for ln in _rows(blk["lines"]):
            if ln.get("dir", (1, 0))[0] < 0.9:  # texto vertical/inclinado (marca d'água, rótulo de eixo) fica
                continue
            if trects and in_table(pymupdf.Rect(ln["bbox"])):
                continue
            li = _line_info(ln, page)
            if li:
                lines.append((li, pymupdf.Rect(ln["bbox"])))
        if not lines:
            continue
        width = max(r.x1 for _, r in lines) - min(r.x0 for _, r in lines)
        # distância normal entre linhas deste bloco (o espaço entre parágrafos é medido contra ela)
        pitches = sorted(b2.y0 - b1.y0 for (_l1, b1), (_l2, b2) in zip(lines, lines[1:]) if b2.y0 - b1.y0 > b1.height * 0.5)
        pitch = pitches[len(pitches) // 2] if pitches else None
        groups, cur = [], []
        last = None  # última linha "de verdade" (índices de fórmula como "truth"/"pred" não contam)
        med = sorted(li[1] for li, _r in lines)[len(lines) // 2]
        for (li, r) in lines:
            tiny = len(plain(li[0])) <= 12 and li[1] < med * 0.85
            if tiny and cur:
                cur.append((li, r))           # sobrescrito/subscrito numa linha própria: fica no mesmo parágrafo
                continue
            if cur and last is not None:
                (pt, psz, pbold, _), pr = last
                text, size, bold, _ = li
                lh = max(pr.height, 1)
                same_row = r.y0 < pr.y1 - lh * 0.5  # spans lado a lado na mesma linha
                new = False
                if not same_row:
                    if abs(size - psz) > max(psz, size) * 0.15 or bold != pbold:
                        new = True                                       # título / rótulo × texto
                    elif _family(li[3]) != _family(cur[-1][0][3]) and (len(cur) == 1 or len(plain(text).split()) <= 8):
                        new = True                                       # outra fonte (título "3. Results" × "3.1 …")
                    elif pitch and r.y0 - pr.y0 > pitch + lh * 0.45:
                        new = True                                       # espaço entre parágrafos
                    elif re.search(r"[.!?:]\s*$", plain(pt)) and pr.width < width * 0.72 and text[:1].isupper():
                        new = True                                       # linha curta no fim da frase
                    elif len(cur) == 1 and pr.width < width * 0.45 and len(plain(pt).split()) <= 6 \
                            and not re.search(r"[.,;:]\s*$", plain(pt)) and pt[:1].isupper():
                        new = True                                       # título curto numa linha só
                if new:
                    groups.append(cur)
                    cur = []
            cur.append((li, r))
            if not tiny:
                last = (li, r)
        groups.append(cur)
        for g in groups:
            txt = ""
            for (t, *_), _r in g:
                if txt.endswith("-") and t[:1].islower():
                    # hifenização do fim da linha some ("de-" + "scription"); hífen de palavra composta fica
                    # ("person-to-" + "person", "COVID-" + "19")
                    last = txt.rsplit(" ", 1)[-1]
                    txt = (txt + t) if "-" in last[:-1] else (txt[:-1] + t)
                else:
                    txt = (txt + " " + t) if txt else t
            txt = _merge_italic(re.sub(r"[ \t]+", " ", txt).strip())
            spans = [sp for (li, _r) in g for sp in li[3]]
            rect = pymupdf.Rect(g[0][1])
            for _li, r in g[1:]:
                rect |= r
            size = max(li[1] for li, _r in g)
            bold = sum(li[2] for li, _r in g) > len(g) / 2
            colors = Counter()
            fonts = Counter()
            mathc = 0
            for sp in spans:
                colors[sp["color"]] += len(sp["text"])
                if _MATH_FONT.search(sp["font"]):
                    mathc += len(sp["text"].strip())
                fonts[_font_is_serif(page, sp["font"])] += len(sp["text"])
            rows = sorted({round(r.y0) for _li, r in g})
            full = sum(1 for _li, r in g[:-1] if r.width > rect.width * 0.92)
            lead = ""
            if not bold:
                acc = ""
                for sp in g[0][0][3]:
                    if not sp["text"].strip():
                        acc += sp["text"]
                        continue
                    if sp["flags"] & 16 or _font_is_bold(page, sp["font"]):
                        acc += sp["text"]
                    else:
                        break
                acc = acc.strip()
                if acc and re.search(r"[.:]$", acc) and 1 <= len(acc.split()) <= 8 and txt.startswith(acc) and \
                        len(txt) > len(acc) + 10:
                    lead = acc
            out.append(Block(pno, rect, txt, size, bold, color=colors.most_common(1)[0][0] if colors else 0, lead=lead,
                             serif=fonts[True] > fonts[False], justify=len(rows) >= 3 and full >= (len(g) - 1) * 0.6,
                             center=_centered(g, rect, page.rect.width),
                             math=mathc / max(1, sum(len(sp["text"].strip()) for sp in spans)),
                             nlines=len(rows)))
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


_EMAIL_URL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?://\S+|www\.\S+|doi\.org/\S+")


_EN_STOP = {"the", "of", "and", "to", "in", "is", "are", "for", "with", "that", "this", "we", "as", "by", "on", "be", "from",
         "an", "which", "our", "it", "at", "was", "were", "has", "have", "can", "not", "or", "where", "when", "if", "then"}
_CAPTION = re.compile(r"^\s*(fig(?:ure|ura)?s?|tab(?:le|ela)?|chart|gr[áa]fico|quadro|scheme|algorithm|algoritmo)\.?\s*"
                      r"[A-Z]?\d+", re.I)


def _authors(text, words):
    """Linha de autores: nomes com iniciais maiúsculas, vírgulas e números de afiliação sobrescritos."""
    sups = text.count(_SUP)
    if sups < 2 or "," not in text or not words:
        return False
    caps = sum(1 for w in words if w[0].isupper() or w.lower() in ("and", "e", "y", "de", "da", "do", "dos", "das", "van", "von"))
    return caps >= len(words) * 0.8 and not re.search(r"[.!?]\s+[a-z]", plain(text))


def analyze(doc, pages=None):
    """{página: [Block]} na ordem de leitura, marcando o que não se traduz e o que continua o parágrafo anterior."""
    import pymupdf
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
    images, figures = {}, {}
    for p in per:
        try:
            images[p] = [pymupdf.Rect(i["bbox"]) for i in doc[p].get_image_info()]
        except Exception:
            images[p] = []
        try:  # gráficos e diagramas desenhados em vetor (rótulos de eixo e legendas internas ficam no original)
            area = doc[p].rect.get_area()
            figures[p] = [r for r in doc[p].cluster_drawings() if r.get_area() > area * 0.02 and r.height > 40]
            # moldura com texto dentro (caixa do resumo) não é figura
            figures[p] = [r for r in figures[p] if not any(b.nlines >= 3 and (b.rect & r).get_area() > b.rect.get_area() * 0.8
                                                          for b in per[p])]
        except Exception:
            figures[p] = []
    for bl in per.values():
        for b in bl:
            t = plain(b.text)
            h = doc[b.page].rect.height
            words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’-]*", t)
            if _PAGE_NO.match(t):
                b.keep, b.why = True, "número da página"
            elif edge(b) and len(pages) >= 2 and cnt[key(b)] >= rep:
                b.keep, b.why = True, "cabeçalho/rodapé"
            elif _KEEP.match(t) or len(re.findall(r"[A-Za-zÀ-ÿ]", t)) < 3 or not any(len(w) >= 3 for w in words):
                b.keep, b.why = True, "números"
            elif (b.rect.y1 < h * 0.075 or b.rect.y0 > h * 0.94) and len(words) <= 20:
                b.keep, b.why = True, "cabeçalho/rodapé"          # nome da revista, logotipo, DOI
            elif any((b.rect & r).get_area() > b.rect.get_area() * 0.5 for r in images.get(b.page, [])):
                b.keep, b.why = True, "dentro de imagem"          # selos e logotipos ("Check for updates")
            elif _authors(b.text, words):
                b.keep, b.why = True, "autores"
            elif b.math > 0.3 or (len(re.findall(r"[=+×∗∑∫≤≥<>^_|]", t)) >= 2 and sum(len(w) >= 3 for w in words) < 4) or \
                    (re.search(r"[=∗×|^]", t) and len(words) <= 14 and not any(w.lower() in _EN_STOP for w in words)):
                b.keep, b.why = True, "fórmula"
            elif not b.cell and len(words) <= 8 and b.nlines <= 2 and \
                    any((b.rect & r).get_area() > b.rect.get_area() * 0.6 for r in figures.get(b.page, [])):
                b.keep, b.why = True, "dentro de figura"           # rótulos de eixo, legendas do gráfico
            elif len(_EMAIL_URL.sub(" ", t).split()) <= 6 and _EMAIL_URL.search(t):
                b.keep, b.why = True, "e-mail/endereço"            # o tradutor inventa endereços
            elif (_SUP in b.text or re.search(r"[∗*†‡§]", t)) and 1 < len(words) <= 5 and all(w[0].isupper() for w in words):
                b.keep, b.why = True, "nome"                       # "Llion Jones*", "Illia Polosukhin* ‡"
    for p, bl in per.items():
        # pedaços que caem dentro de outro bloco (índices de fórmula, "truth/pred"): ficam no original
        for b in bl:
            if b.keep or b.cell:
                continue
            for o in bl:
                if o is not b and not o.cell and o.rect.get_area() > b.rect.get_area() * 1.5 and \
                        (b.rect & o.rect).get_area() > b.rect.get_area() * 0.5:
                    b.keep, b.why = True, "sobreposto"
                    break
    if 0 in per:
        # primeira página: nomes e instituições entre o título e o "Abstract" (o tradutor estraga nomes próprios)
        bl = per[0]
        head = next((b.rect.y0 for b in bl if re.match(r"^\s*(abstract|resumo|summary|a\s*b\s*s\s*t\s*r\s*a\s*c\s*t)\b",
                                                      plain(b.text), re.I)), None)
        title = max((b for b in bl if not b.keep), key=lambda b: b.size, default=None)
        if head is not None:
            for b in bl:
                if b.keep or b is title or b.rect.y1 > head:
                    continue
                ws = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’.-]*", plain(b.text))
                if ws and len(ws) <= 12 and all(w[0].isupper() for w in ws) and not re.search(r"[.!?]\s*$", plain(b.text)) \
                        and not re.search(r"\b(article|research|review|access|original|letter|report|communication|"
                                          r"paper|study|case)\b", plain(b.text), re.I):
                    b.keep, b.why = True, "nomes"
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
    # parágrafo que continua na outra coluna ou página: o anterior é o último bloco de texto corrido (do tamanho
    # do corpo do texto), pulando notas de rodapé, legendas e figuras que ficam no meio
    from statistics import median
    sizes = [b.size for bl in per.values() for b in bl if not b.keep and not b.bold and not b.cell and b.nlines >= 2]
    body = median(sizes) if sizes else None
    prev = None
    for p in pages:
        for b in per[p]:
            if b.keep or b.cell:
                continue
            if b.bold:
                prev = None                          # título: começa outro assunto
                continue
            t = plain(b.text)
            if body is not None and abs(b.size - body) >= 1.5 or _CAPTION.match(t):
                continue                             # nota, legenda: não interrompe o parágrafo do corpo
            if prev is not None and not re.search(r"[.!?:”\"»)]\s*$", plain(prev.text)) and t[:1].islower():
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
        parts = [b.text for b in u]
        lead = u[0].lead if u[0].lead and u[0].text.startswith(u[0].lead) else ""
        if lead:                         # título no começo do parágrafo ("Normalization.", "Background:"): à parte
            parts[0] = u[0].text[len(lead):].lstrip()
            u[0].lead_tr = re.sub(r"(\w)- (\w)", r"\1-\2", translate_paragraphs([lead], path, dst, glossary)[0])
        for t in parts:
            if text.endswith("-") and t[:1].islower():
                last = text.rsplit(" ", 1)[-1]
                text = (text + t) if "-" in last[:-1] else (text[:-1] + t)
            else:
                text = (text + " " + t) if text else t
        tr = translate_paragraphs([text], path, dst, glossary)[0] if text.strip() else ""
        for k, (b, t) in enumerate(zip(u, _split_like(tr, parts))):
            t = (u[0].lead_tr + " " + t).strip() if k == 0 and lead else t
            b.rich = t
            result[id(b)] = t.replace(_ITA, "").replace(_ITA_END, "")
        for p in {b.page for b in u}:
            left[p] -= 1
        flush()


def _bg_colors(page, rects):
    """Cor de fundo de cada retângulo (a mais comum entre os pixels), para cobrir o original mesmo quando o PDF não
    deixa apagar o texto (texto dentro de formulários XObject, por exemplo)."""
    import pymupdf
    from collections import Counter
    z = 1.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False, colorspace=pymupdf.csRGB)
    out = []
    for r in rects:
        x0, y0 = max(0, int(r.x0 * z)), max(0, int(r.y0 * z))
        x1, y1 = min(pix.width - 1, int(r.x1 * z)), min(pix.height - 1, int(r.y1 * z))
        c = Counter()
        step = max(1, int(min(x1 - x0, y1 - y0) / 12) or 1)
        for yy in range(y0, y1 + 1, step):
            for xx in range(x0, x1 + 1, step):
                px = pix.pixel(xx, yy)
                c[tuple(min(255, (v + 4) // 8 * 8) for v in px[:3])] += 1
        rgb = c.most_common(1)[0][0] if c else (255, 255, 255)
        out.append(tuple(v / 255 for v in rgb))
    return out


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(v * 255) for v in rgb)


def _fit_scale(rect, html, css):
    """Maior escala (≤ 1) em que o texto cabe no retângulo."""
    import pymupdf
    try:
        st = pymupdf.Story(html, user_css=css)
        # fit_scale aumenta o retângulo até caber: a letra precisa diminuir na mesma proporção
        res = st.fit_scale(rect, scale_min=1.0, scale_max=4.0)
        return max(0.25, 1.0 / res.parameter) if res.big_enough else 0.25
    except Exception:
        return 1.0


def overlay_page(page, items):
    """Escreve a tradução no lugar do texto original (imagens e desenhos ficam). items: [(Block, tradução)].
    O original é apagado e, onde o PDF não deixa apagar, coberto com a cor de fundo da própria página; a letra segue
    o tamanho, a cor, a serifa e o alinhamento do original, com o mesmo tamanho para o texto corrido da página."""
    import pymupdf
    from statistics import median
    todo = [(b, t) for b, t in items if t and not b.keep]
    if not todo:
        return
    bgs = _bg_colors(page, [b.rect for b, _ in todo])
    for b, _t in todo:
        page.add_redact_annot(b.rect, fill=None)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    try:
        obstacles = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    except Exception:
        obstacles = []
    others = [b.rect for b, _ in items]
    bottom = page.rect.height * 0.94
    plans = []
    for (b, t), bg in zip(todo, bgs):
        r = pymupdf.Rect(b.rect)
        if b.cell:
            pass                 # célula de tabela: fica dentro dela
        elif b.nlines <= 1 and b.center:  # título centralizado: cresce igual para os dois lados
            grow = min(r.x0 - 36, page.rect.width - 36 - r.x1)
            if grow > 0:
                r.x0 -= grow
                r.x1 += grow
        elif b.nlines <= 1:    # uma linha só (título): pode crescer para a direita até a margem ou o próximo bloco
            limit = page.rect.width - 36
            for o in others:
                if o is not b.rect and o.x0 > r.x1 and o.y0 < r.y1 and o.y1 > r.y0:
                    limit = min(limit, o.x0 - 4)
            r.x1 = max(r.x1, limit)
        # e para baixo, até o próximo bloco/imagem (o português costuma ser ~20% mais longo)
        below = [o.y0 for o in others + obstacles if o is not b.rect and o.y0 >= b.rect.y1 - 1
                 and o.x0 < r.x1 - 2 and o.x1 > r.x0 + 2]
        if not b.cell and b.nlines >= 2:   # título de uma linha não cresce para baixo (encostaria no texto)
            r.y1 = max(r.y1, min(below + [bottom]) - 2) if b.rect.y1 < bottom else r.y1
        r.y1 = min(r.y1, b.rect.y1 + max(b.rect.height * 0.6, b.size * 3))
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        col = ((b.color >> 16) & 255, (b.color >> 8) & 255, b.color & 255)
        col = tuple(v / 255 for v in col)
        clum = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
        if abs(clum - lum) < 0.35:                         # pouco contraste: preto ou branco conforme o fundo
            col = (0.0, 0.0, 0.0) if lum > 0.5 else (1.0, 1.0, 1.0)
        t = t.replace("∗", "*")  # o asterisco matemático não existe nas fontes comuns
        esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
        rich = b.rich.replace("∗", "*") if b.rich and b.rich.replace(_ITA, "").replace(_ITA_END, "") == t else t
        body = esc(rich).replace(_ITA, "<i>").replace(_ITA_END, "</i>")
        if b.lead_tr and t.startswith(b.lead_tr):
            body = "<b>" + esc(b.lead_tr) + "</b>" + body[len(esc(b.lead_tr)):]
        html = "<p>" + body + "</p>"
        fam = "serif" if b.serif else "sans-serif"
        css0 = (f"body, p {{margin: 0; padding: 0;}} p {{font-family: {fam}; font-size: {b.size:.2f}px; "
                f"line-height: 1.12;{' font-weight: bold;' if b.bold else ''}"
                f"{' text-align: justify;' if b.justify else ' text-align: center;' if b.center else ''}}}")
        plans.append([b, t, r, bg, col, html, fam, _fit_scale(r, html, css0)])
    # mesmo tamanho de letra para o texto corrido da página (o menor necessário entre os parágrafos parecidos)
    body = [pl for pl in plans if not pl[0].bold and not pl[0].center and not pl[0].cell]
    if body:
        ref = median(pl[0].size for pl in body)
        similar = [pl for pl in body if abs(pl[0].size - ref) <= ref * 0.12]
        if similar:
            common = sorted(pl[7] for pl in similar)[max(0, len(similar) // 5)]   # tolera 1 em 5 mais apertado
            for pl in similar:
                pl[7] = min(pl[7], common)
    for b, t, r, bg, col, html, fam, sc in plans:  # primeiro cobre todos os originais, depois escreve
        page.draw_rect(b.rect + (-1, -0.8, 1, 0.8), color=None, fill=bg, overlay=True)
    for b, t, r, bg, col, html, fam, sc in plans:
        css = (f"body, p {{margin: 0; padding: 0;}} p {{font-family: {fam}; font-size: {b.size * sc:.2f}px; "
               f"line-height: 1.12; color: {_hex(col)};{' font-weight: bold;' if b.bold else ''}"
               f"{' text-align: justify;' if b.justify else ' text-align: center;' if b.center else ''}}}")
        try:
            page.insert_htmlbox(r, html, css=css, scale_low=0.25)
        except Exception:
            page.insert_textbox(r, t, fontsize=max(4.0, b.size * sc * 0.9), color=col)


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
