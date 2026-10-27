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


def _openalex(query, year_from=None, sort="relevance", page=1, api_key="", lang=None):
    flt = ["is_oa:true", "has_pdf_url:true", "type:article|review|preprint"]
    if year_from:
        flt.append(f"publication_year:>{int(year_from) - 1}")
    if lang:
        flt.append(f"language:{lang}")
    params = {"search": query, "filter": ",".join(flt), "per_page": "25", "page": str(page),
              "select": "id,display_name,publication_year,authorships,primary_location,best_oa_location,locations,"
                        "cited_by_count,language,doi,biblio"}
    if sort == "citations":
        params["sort"] = "cited_by_count:desc"
    elif sort == "recent":
        params["sort"] = "publication_date:desc"
    if api_key:
        params["api_key"] = api_key
    data = _get_json(OPENALEX + "?" + urllib.parse.urlencode(params))
    out = []
    for w in data.get("results", []):
        pdfs = []
        for loc in [w.get("best_oa_location") or {}] + (w.get("locations") or []):
            u = (loc or {}).get("pdf_url")
            if u and u not in pdfs and (loc.get("is_oa", True)):
                pdfs.append(u)
        if not pdfs:
            continue
        best = w.get("best_oa_location") or {}
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or \
            ((best.get("source") or {}).get("display_name")) or ""
        b = w.get("biblio") or {}
        pages = "-".join(x for x in (b.get("first_page"), b.get("last_page")) if x)
        out.append(Article(
            title=re.sub(r"<[^>]+>", "", w.get("display_name") or "(sem título)"),
            authors=[(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or []) if a.get("author")],
            year=w.get("publication_year"), venue=venue, citations=w.get("cited_by_count"),
            language=w.get("language") or "", doi=w.get("doi") or "", pdf_urls=pdfs,
            page_url=best.get("landing_page_url") or (w.get("doi") or ""),
            volume=b.get("volume") or "", issue=b.get("issue") or "", pages=pages))
    return out, (data.get("meta") or {}).get("count", len(out))


def _europepmc(query, year_from=None, sort="relevance", page=1):
    q = f"({query}) AND OPEN_ACCESS:Y AND HAS_PDF:Y"
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
        if not pdfs:
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
            source="Europe PMC"))
    return out, data.get("hitCount", len(out))


def search(query, year_from=None, sort="relevance", page=1, api_key="", lang=None):
    """(artigos, total). Usa o OpenAlex; se ele recusar (limite diário) ou falhar, usa o Europe PMC."""
    query = query.strip()
    if not query:
        return [], 0
    try:
        return _openalex(query, year_from, sort, page, api_key, lang)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        first = e
    try:
        return _europepmc(query, year_from, sort, page)
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


def search_many(queries, year_from=None, sort="relevance", page=1, api_key="", seen=None):
    """Pesquisa várias versões (português, sem acento, inglês) e intercala os resultados, sem repetir."""
    seen = set(seen or ())
    lists, total, errors = [], 0, []
    for q in queries:
        try:
            arts, n = search(q, year_from, sort, page, api_key)
            lists.append(arts)
            total += n
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
