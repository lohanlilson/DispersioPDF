"""Busca de artigos científicos de acesso aberto (OpenAlex; Europe PMC como reserva) e download do PDF.

Só aparecem artigos com PDF gratuito e legal (versão publicada ou aceita, disponibilizada pela revista ou repositório).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 LumenPDF"
OPENALEX = "https://api.openalex.org/works"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


@dataclass
class Article:
    title: str
    authors: list = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    citations: int | None = None
    language: str = ""
    doi: str = ""
    pdf_urls: list = field(default_factory=list)
    page_url: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    source: str = "OpenAlex"
    abstract: str = ""
    id: str = ""                                  # W123… no OpenAlex
    kind: str = ""                                # article, review, preprint…
    related: list = field(default_factory=list)   # ids de trabalhos parecidos
    refs: list = field(default_factory=list)      # ids das referências deste artigo

    @property
    def has_pdf(self):
        return bool(self.pdf_urls)

    @property
    def authors_short(self):
        if not self.authors:
            return ""
        return ", ".join(self.authors[:3]) + (" et al." if len(self.authors) > 3 else "")

    def abnt(self):
        """Referência no formato ABNT (NBR 6023)."""
        def autor(n):
            parts = n.replace(",", " ").split()
            if len(parts) < 2:
                return n.upper()
            if re.fullmatch(r"[A-Z]{1,3}", parts[-1]):          # "Long K" (sobrenome + iniciais)
                return f"{' '.join(parts[:-1]).upper()}, {'. '.join(parts[-1])}."
            return f"{parts[-1].upper()}, {' '.join(parts[:-1])}"
        if len(self.authors) > 3:
            aut = autor(self.authors[0]) + " et al."
        else:
            aut = "; ".join(autor(a) for a in self.authors)
        ref = (aut.rstrip(".") + ". " if aut else "") + self.title.rstrip(".") + ". "
        if self.venue:
            ref += f"{self.venue}"
            if self.volume:
                ref += f", v. {self.volume}"
            if self.issue:
                ref += f", n. {self.issue}"
            if self.pages:
                ref += f", p. {self.pages}"
            ref += ", "
        ref += f"{self.year or 's.d.'}."
        if self.doi:
            ref += f" DOI: {self.doi.replace('https://doi.org/', '')}."
        link = self.page_url or (self.pdf_urls[0] if self.pdf_urls else "")
        if link:
            from datetime import date
            meses = ["jan.", "fev.", "mar.", "abr.", "maio", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez."]
            h = date.today()
            ref += f" Disponível em: {link}. Acesso em: {h.day} {meses[h.month - 1]} {h.year}."
        return ref


class SearchError(Exception):
    pass


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


import datetime as _dt

_Y = _dt.date.today().year
# filtros rápidos: chave → (rótulo, filtro do OpenAlex, trecho da consulta do Europe PMC)
FILTERS = {
    "pdf": ("Só com PDF grátis", "is_oa:true,has_pdf_url:true", " AND OPEN_ACCESS:Y AND HAS_PDF:Y"),
    "recent": ("Últimos 5 anos", f"publication_year:>{_Y - 6}", f" AND PUB_YEAR:[{_Y - 5} TO 3000]"),
    "review": ("Revisões", "type:review", ' AND PUB_TYPE:"review"'),
    "br": ("Brasil", "authorships.countries:BR", ' AND AFF:"Brazil"'),
    "pt": ("Em português", "language:pt", ' AND LANG:"por"'),
    "abstract": ("Com resumo", "has_abstract:true", " AND HAS_ABSTRACT:Y"),
}
SELECT = ("id,display_name,publication_year,authorships,primary_location,best_oa_location,locations,cited_by_count,"
          "language,doi,biblio,type,abstract_inverted_index,related_works,referenced_works")


def abstract_text(inv):
    """O OpenAlex guarda o resumo como índice invertido (palavra → posições): remonta o texto."""
    if not inv:
        return ""
    pos = {}
    for w, ps in inv.items():
        for p in ps:
            pos[p] = w
    return " ".join(pos[i] for i in sorted(pos))


def _short_id(u):
    return (u or "").rsplit("/", 1)[-1]


def parse_work(w):
    pdfs = []
    for loc in [w.get("best_oa_location") or {}] + (w.get("locations") or []):
        u = (loc or {}).get("pdf_url")
        if u and u not in pdfs and (loc.get("is_oa", True)):
            pdfs.append(u)
    best = w.get("best_oa_location") or {}
    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or \
        ((best.get("source") or {}).get("display_name")) or ""
    b = w.get("biblio") or {}
    pages = "-".join(x for x in (b.get("first_page"), b.get("last_page")) if x)
    land = best.get("landing_page_url") or ((w.get("primary_location") or {}).get("landing_page_url")) or (w.get("doi") or "")
    return Article(
        title=re.sub(r"<[^>]+>", "", w.get("display_name") or "(sem título)"),
        authors=[(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or []) if a.get("author")],
        year=w.get("publication_year"), venue=venue, citations=w.get("cited_by_count"),
        language=w.get("language") or "", doi=w.get("doi") or "", pdf_urls=pdfs, page_url=land,
        volume=b.get("volume") or "", issue=b.get("issue") or "", pages=pages,
        abstract=abstract_text(w.get("abstract_inverted_index")), id=_short_id(w.get("id")), kind=w.get("type") or "",
        related=[_short_id(x) for x in (w.get("related_works") or [])],
        refs=[_short_id(x) for x in (w.get("referenced_works") or [])])


def _flt(filters, extra=None):
    flt = [] if "review" in filters else ["type:article|review|preprint"]
    flt += [FILTERS[k][1] for k in filters if k in FILTERS]
    flt += extra or []
    return ",".join(flt)


def _oa_list(params, api_key=""):
    params = dict(params, select=SELECT)
    if api_key:
        params["api_key"] = api_key
    data = _get_json(OPENALEX + "?" + urllib.parse.urlencode(params))
    return [parse_work(w) for w in data.get("results", [])], (data.get("meta") or {}).get("count", 0)


def _sort(sort):
    return {"citations": "cited_by_count:desc", "recent": "publication_date:desc"}.get(sort)


def _openalex(query, year_from=None, sort="relevance", page=1, api_key="", lang=None, filters=("pdf",)):
    extra = []
    if year_from:
        extra.append(f"publication_year:>{int(year_from) - 1}")
    if lang:
        extra.append(f"language:{lang}")
    params = {"search": query, "filter": _flt(filters, extra), "per_page": "25", "page": str(page)}
    if _sort(sort):
        params["sort"] = _sort(sort)
    arts, n = _oa_list(params, api_key)
    if "pdf" in filters:
        arts = [a for a in arts if a.has_pdf]
    return arts, n


def by_ids(ids, api_key="", filters=()):
    """Trabalhos pelo id do OpenAlex (parecidos, referências), mantendo a ordem pedida."""
    out = []
    ids = [i for i in ids if i][:100]
    for k in range(0, len(ids), 50):
        chunk = ids[k:k + 50]
        arts, _ = _oa_list({"filter": _flt(filters, ["openalex_id:" + "|".join(chunk)]) if filters else
                            "openalex_id:" + "|".join(chunk), "per_page": "50"}, api_key)
        order = {i: n for n, i in enumerate(chunk)}
        out += sorted(arts, key=lambda a: order.get(a.id, 999))
    return out


def citing(work_id, page=1, api_key="", filters=(), sort="citations"):
    """Quem citou este trabalho."""
    params = {"filter": _flt(filters, [f"cites:{work_id}"]) if filters else f"cites:{work_id}", "per_page": "25",
              "page": str(page)}
    if _sort(sort):
        params["sort"] = _sort(sort)
    return _oa_list(params, api_key)


DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
OAID_RE = re.compile(r"\b(W\d{5,})\b")


def parse_link(text):
    """DOI, link de DOI/revista com DOI, arXiv ou id do OpenAlex colado na pesquisa → identificador para buscar direto."""
    t = text.strip()
    m = ARXIV_RE.search(t)
    if m:
        return "doi:10.48550/arXiv." + m.group(1)
    m = DOI_RE.search(t)
    if m:
        return "doi:" + m.group(1).rstrip(".,;)").removesuffix(".pdf")
    m = OAID_RE.search(t)
    if m and (" " not in t or "openalex" in t):
        return m.group(1)
    return None


def by_key(key, api_key=""):
    """Um trabalho pelo DOI ("doi:10…") ou id do OpenAlex."""
    url = OPENALEX + "/" + urllib.parse.quote(key, safe=":/") + "?select=" + SELECT + (f"&api_key={api_key}" if api_key else "")
    return parse_work(_get_json(url))


def autocomplete(text, timeout=6):
    """Sugestões enquanto digita: temas (palavras-chave) e artigos. [(tipo, rótulo, dica, id)]. Gratuito no OpenAlex."""
    out = []
    q = urllib.parse.quote(text.strip())
    for kind, path in (("tema", "keywords"), ("artigo", "works")):
        try:
            data = _get_json(f"https://api.openalex.org/autocomplete/{path}?q={q}", timeout=timeout)
        except Exception:
            continue
        for r in (data.get("results") or [])[:6 if kind == "tema" else 5]:
            out.append((kind, r.get("display_name") or "", r.get("hint") or "", _short_id(r.get("id"))))
    return out


def _europepmc(query, year_from=None, sort="relevance", page=1, filters=("pdf",)):
    q = f"({query})" + "".join(FILTERS[k][2] for k in filters if k in FILTERS)
    if year_from:
        q += f" AND PUB_YEAR:[{int(year_from)} TO 3000]"
    params = {"query": q, "format": "json", "resultType": "core", "pageSize": "25", "page": str(page)}
    if sort == "citations":
        params["sort"] = "CITED desc"
    elif sort == "recent":
        params["sort"] = "P_PDATE_D desc"
    data = _get_json(EUROPEPMC + "?" + urllib.parse.urlencode(params))
    out = []
    for r in (data.get("resultList") or {}).get("result", []):
        pdfs = []
        for u in ((r.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
            if u.get("documentStyle") == "pdf" and u.get("availabilityCode") in ("OA", "F"):
                pdfs.append(u.get("url"))
        if r.get("pmcid"):
            pdfs.append(f"https://europepmc.org/articles/{r['pmcid']}?pdf=render")
        pdfs = list(dict.fromkeys(pdfs))
        if not pdfs and "pdf" in filters:
            continue
        authors = [a.get("fullName", "") for a in ((r.get("authorList") or {}).get("author") or [])]
        ji = r.get("journalInfo") or {}
        out.append(Article(
            title=r.get("title", "").rstrip("."), authors=authors,
            year=int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
            venue=((ji.get("journal") or {}).get("title")) or "", citations=r.get("citedByCount"),
            language=(r.get("language") or "")[:2], doi=("https://doi.org/" + r["doi"]) if r.get("doi") else "",
            pdf_urls=pdfs, page_url=f"https://europepmc.org/article/{r.get('source', 'MED')}/{r.get('id', '')}",
            volume=ji.get("volume") or "", issue=ji.get("issue") or "", pages=r.get("pageInfo") or "",
            source="Europe PMC", abstract=re.sub(r"<[^>]+>", "", r.get("abstractText") or ""),
            kind="review" if "review" in str(r.get("pubTypeList", "")).lower() else "article"))
    return out, data.get("hitCount", len(out))


def search(query, year_from=None, sort="relevance", page=1, api_key="", lang=None, filters=("pdf",)):
    """(artigos, total). Usa o OpenAlex; se ele recusar (limite diário) ou falhar, usa o Europe PMC."""
    query = query.strip()
    if not query:
        return [], 0
    try:
        return _openalex(query, year_from, sort, page, api_key, lang, filters)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        first = e
    try:
        return _europepmc(query, year_from, sort, page, filters)
    except Exception as e:
        raise SearchError(f"Não foi possível pesquisar agora ({first}; {e}). Verifique a internet.") from e


def strip_accents(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_ACC = None


def restore_accents(q):
    """Recoloca acentos em palavras comuns digitadas sem eles (caes → cães), mantendo maiúsculas."""
    global _ACC
    if _ACC is None:
        _ACC = {}
        try:
            from . import resource
            with open(resource("assets", "dados", "acentos.txt"), encoding="utf-8") as f:
                for ln in f:
                    if "=" in ln and not ln.startswith("#"):
                        a, b = ln.strip().split("=", 1)
                        _ACC[a] = b
        except Exception:
            pass

    def fix(m):
        w = m.group()
        b = _ACC.get(w.lower())
        if not b:
            return w
        return b.upper() if w.isupper() and len(w) > 1 else (b[0].upper() + b[1:] if w[0].isupper() else b)
    return re.sub(r"[A-Za-z]+", fix, q)


def variants(q):
    """A pesquisa como foi digitada e uma versão corrigida: com os acentos que faltaram ou, se já tinha acentos,
    sem acentos e hífens. Acento faltando ou trocado não pode esconder resultados."""
    out = []
    fixed = restore_accents(q)
    for v in (q, fixed if fixed != q else strip_accents(q).replace("-", " ")):
        v = " ".join(v.split())
        if v and v.lower() not in [x.lower() for x in out]:
            out.append(v)
    return out


def norm_key(a):
    t = re.sub(r"[^a-z0-9]+", " ", strip_accents(a.title).lower()).strip()
    return (a.doi or "").lower() or t


def search_many(queries, year_from=None, sort="relevance", page=1, api_key="", seen=None, filters=("pdf",)):
    """Pesquisa várias versões (português, sem acento, inglês) e intercala os resultados, sem repetir."""
    seen = set(seen or ())
    lists, total, errors = [], 0, []
    for q in queries:
        try:
            arts, n = search(q, year_from, sort, page, api_key, filters=filters)
            lists.append(arts)
            total = max(total, n)
        except SearchError as e:
            errors.append(e)
    if not lists and errors:
        raise errors[0]
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:          # um de cada lista por vez: os em inglês aparecem junto dos em português
            if i < len(lst):
                k = norm_key(lst[i])
                if k not in seen:
                    seen.add(k)
                    out.append(lst[i])
    return out, total


_STOPW = set("""a o as os de da do das dos e em no na nos nas um uma uns umas para por com sem que se ao aos à às como mais
menos entre sobre sob seu sua seus suas ou é são foi ser ter the of and in on for with to a an is are was were by from as at
be this that these those or not its their our we they it which using use study analysis case cases results et al""".split())


def query_from_document(doc):
    """Pesquisa para "artigos sobre este documento": o título (metadados ou a maior letra da 1ª página)
    e, se faltar, os termos mais frequentes das primeiras páginas."""
    from collections import Counter
    title = (doc.metadata or {}).get("title") or ""
    if len(title.split()) < 3 or re.search(r"(?i)microsoft word|untitled|\.docx?$|\.pdf$", title):
        best, size = "", 0
        try:
            for b in doc[0].get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    t = "".join(sp["text"] for sp in ln["spans"]).strip()
                    sz = max((sp["size"] for sp in ln["spans"]), default=0)
                    if len(t) > 12 and sz > size + 0.5:
                        best, size = t, sz
                    elif len(t) > 3 and abs(sz - size) <= 0.5 and best and len(best) < 160:
                        best += " " + t
        except Exception:
            pass
        title = best
    words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-]{3,}", " ".join(doc[p].get_text() for p in range(min(3, doc.page_count))))
    freq = Counter(w.lower() for w in words if w.lower() not in _STOPW)
    terms = [w for w, _ in freq.most_common(6)]
    title = " ".join(title.split()[:14])
    return title if len(title.split()) >= 3 else " ".join(terms[:5])


def safe_name(title, maxlen=90):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", title).strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:maxlen].rstrip(" .") or "Artigo") + ".pdf"


def articles_dir():
    base = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(base):
        base = os.path.expanduser("~")
    d = os.path.join(base, "Lumen PDF", "Artigos")
    os.makedirs(d, exist_ok=True)
    return d


def download(article, dest_dir=None, progress=None, cancel=lambda: False):
    """Baixa o primeiro link que de fato entrega um PDF. Devolve o caminho do arquivo ou None."""
    dest_dir = dest_dir or articles_dir()
    fn = os.path.join(dest_dir, safe_name(article.title))
    for url in article.pdf_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
            with urllib.request.urlopen(req, timeout=40) as r:
                total = int(r.headers.get("Content-Length") or 0)
                head = r.read(1024)
                if b"%PDF" not in head[:1024]:
                    continue          # página da revista (HTML, captcha...), não o PDF
                buf, got = [head], len(head)
                while True:
                    if cancel():
                        return None
                    b = r.read(1 << 16)
                    if not b:
                        break
                    buf.append(b)
                    got += len(b)
                    if progress:
                        progress(got, total)
            with open(fn, "wb") as f:
                f.write(b"".join(buf))
            return fn
        except Exception:
            continue
    return None
