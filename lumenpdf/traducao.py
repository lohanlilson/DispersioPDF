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
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LumenPDF"

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


def translate_paragraphs(paras, path, dst=None, glossary=None):
    """Traduz uma lista de parágrafos seguindo a rota de pacotes. Números, fórmulas e referências curtas ficam iguais."""
    out = []
    for para in paras:
        if not para.strip() or _KEEP.match(para) or len(re.findall(r"[A-Za-zÀ-ÿ]", para)) < 3:
            out.append(para)
            continue
        sents = sentences(para)
        for pair in path:
            sents = _engine(pair).run(sents)
        t = " ".join(sents)
        if (dst or path[-1][1]) == "pt":
            t = pt_br(t)
        for k, v in (glossary or {}).items():
            t = re.sub(r"\b" + re.escape(k) + r"\b", v, t, flags=re.I)
        out.append(t)
    return out


# ------------------------------------------------------------------ texto das páginas
def page_paragraphs(page):
    """[(retângulo, parágrafo, tamanho da letra, negrito)] da página, com hifenização desfeita e linhas unidas."""
    import pymupdf
    out = []
    d = page.get_text("dict", flags=pymupdf.TEXT_DEHYPHENATE)
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        lines = []
        for ln in b["lines"]:
            s = "".join(sp["text"] for sp in ln["spans"]).strip()
            if s:
                lines.append(s)
        if not lines:
            continue
        txt = " ".join(lines)
        txt = re.sub(r"\s+", " ", txt).strip()
        spans = [sp for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
        size = max((sp["size"] for sp in spans), default=10)
        chars = sum(len(sp["text"]) for sp in spans) or 1
        bold = sum(len(sp["text"]) for sp in spans if sp["flags"] & 16 or "bold" in sp["font"].lower()) > chars / 2
        out.append((pymupdf.Rect(b["bbox"]), txt, size, bold))
    return out


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
