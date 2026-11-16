"""Dicionário ao dar duplo clique numa palavra.

Português: significado pelo Wikcionário (pt.wiktionary.org), seguindo a forma básica (“casas” → “casa”, “correu” → “correr”).
Outros idiomas: tradução para o português pelo tradutor offline do programa + significado (en.wiktionary.org).
Tudo que já foi consultado fica guardado e funciona sem internet.
"""
import html
import json
import os
import re
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

UA = "DispersioPDF/1.0 (https://github.com/lohanlilson/DispersioPDF)"
_mem = {}
_lock = threading.Lock()


def _cache_file():
    from . import traducao
    d = os.path.abspath(os.path.join(traducao.models_dir(), ".."))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "dicionario.json")


def _load_cache():
    if not _mem:
        try:
            _mem.update(json.load(open(_cache_file(), encoding="utf-8")))
        except Exception:
            pass
    return _mem


def _save_cache():
    try:
        with _lock:
            items = dict(list(_mem.items())[-3000:])
            json.dump(items, open(_cache_file(), "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def clean_word(w):
    w = w.strip().strip(".,;:!?\"'“”‘’()[]{}«»…—–-*").strip()
    return w


def _get(url, timeout=8):
    import time
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 2:        # limite de acessos do Wikimedia: espera e tenta de novo
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 1:
                continue
            raise


def _wikitext(page):
    url = ("https://pt.wiktionary.org/w/api.php?action=parse&prop=wikitext&format=json&formatversion=2&redirects=1&page="
           + urllib.parse.quote(page))
    try:
        return json.loads(_get(url))["parse"]["wikitext"]
    except Exception:
        return None


def _strip_wiki(t):
    t = re.sub(r"\{\{escopo2?\|[^|}]*\|([^}]*)\}\}", lambda m: "(" + m.group(1).replace("|", ", ") + ") ", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"'''?|<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t).strip(" ;:")


_POS = re.compile(r"^==+\s*([^=]+?)\s*==+\s*$")
_LEMMA = re.compile(r"(?:plural|feminino|masculino|forma|flexão|conjugação|pretérito|presente|futuro|particípio|gerúndio|"
                    r"infinitivo|imperativo|singular|diminutivo|aumentativo)[^#\n]*?\[\[([^\]|#]+)", re.I)


def _pt_defs(wikitext):
    """[(classe, definição)] da seção de português, e a forma básica se a palavra for flexão."""
    m = re.search(r"^=\{\{-pt-\}\}=\s*$(.*?)(?=^=\{\{-[a-z]+-\}\}=|\Z)", wikitext, re.M | re.S)
    if not m:
        return [], None
    pos, out, lemma, flex = "", [], None, 0
    for line in m.group(1).splitlines():
        h = _POS.match(line)
        if h and not h.group(1).startswith("{{"):
            pos = h.group(1)
            continue
        if line.startswith("# ") or (line.startswith("#") and not line.startswith(("#*", "#:", "##"))):
            raw = line.lstrip("#").strip()
            lm = _LEMMA.search(raw)
            if lm:
                flex += 1
                lemma = lemma or lm.group(1).strip()
            d = _strip_wiki(raw)
            if d:
                out.append((pos, d))
    # só segue para a forma básica se a palavra for principalmente flexão (“casas”, “correu”)
    return out, (lemma if out and flex * 2 >= len(out) else None)


def portuguese(word):
    """Significados em português ou None (sem internet / não achou)."""
    for page in dict.fromkeys([word, word.lower()]):
        wt = _wikitext(page)
        if not wt:
            continue
        defs, lemma = _pt_defs(wt)
        if not defs:
            continue
        base = None
        if lemma and lemma.lower() != page.lower():
            wt2 = _wikitext(lemma)
            if wt2:
                d2, _ = _pt_defs(wt2)
                if d2:
                    base = (lemma, d2)
        return {"word": page, "defs": defs[:6], "base": base}
    return None


def english(word):
    """Significados no dicionário em inglês (para palavras de outros idiomas): {idioma: [(classe, definição)]}."""
    try:
        data = json.loads(_get("https://en.wiktionary.org/api/rest_v1/page/definition/" + urllib.parse.quote(word)))
    except Exception:
        try:
            data = json.loads(_get("https://en.wiktionary.org/api/rest_v1/page/definition/" + urllib.parse.quote(word.lower())))
        except Exception:
            return {}
    out = {}
    for lang, entries in data.items():
        items = []
        for e in entries:
            for d in e.get("definitions", [])[:3]:
                txt = re.sub(r"<[^>]+>", "", html.unescape(d.get("definition", ""))).strip()
                if txt:
                    items.append((e.get("partOfSpeech", ""), txt))
        if items:
            out[lang] = items[:5]
    return out


def lookup(word, lang="pt"):
    """{'word', 'lang', 'defs': [(classe, texto)], 'base': (lema, defs) | None, 'translation': str | None, 'source'}."""
    w = clean_word(word)
    if not w or len(w) > 60:
        return None
    key = f"{lang}:{w.lower()}"
    cache = _load_cache()
    if key in cache:
        return cache[key]
    res = None
    if lang == "pt":
        p = portuguese(w)
        if p:
            res = {"word": p["word"], "lang": "pt", "defs": p["defs"], "base": p["base"], "translation": None, "source": "Wikcionário"}
    if res is None:
        tr = None
        if lang != "pt":
            try:
                from . import traducao
                path = traducao.route(lang, "pt")
                if path and not traducao.missing(path):
                    tr = traducao.pt_br(traducao.translate_paragraphs([w], path, dst="pt")[0])
            except Exception:
                tr = None
        en = english(w)
        defs = en.get(lang) or next(iter(en.values()), [])
        if defs or tr:
            res = {"word": w, "lang": lang, "defs": defs, "base": None, "translation": tr,
                   "source": "Wiktionary (inglês)" if defs else "tradutor offline"}
    if res:
        cache[key] = res
        _save_cache()
    return res


def word_language(text):
    """Idioma do texto em volta (para saber se traduz ou explica)."""
    try:
        from . import traducao
        return traducao.detect(text) or "pt"
    except Exception:
        return "pt"


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
