"""Proteção contra PDFs de golpe: links enganosos e conteúdo perigoso escondido no arquivo.

- link_risk(): avalia um link antes de abrir (texto mostra um site e o link vai para outro, encurtador,
  endereço só com números, domínio com letras disfarçadas, nome de banco em domínio que não é do banco,
  arquivo de programa para baixar...).
- scan(): procura no documento JavaScript, ações automáticas, abrir programas, envio de formulário para a
  internet, anexos executáveis, links suspeitos e o "botão falso" (imagem com um link cobrindo a página).
"""
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit, unquote

DANGER, WARN, INFO = 2, 1, 0

SHORTENERS = {
    "bit.ly", "bitly.com", "tinyurl.com", "t.co", "goo.gl", "is.gd", "ow.ly", "buff.ly", "cutt.ly", "rb.gy",
    "shorturl.at", "tiny.cc", "rebrand.ly", "s.id", "t.ly", "v.gd", "encurtador.com.br", "abre.ai", "l1nk.dev",
    "short.io", "bl.ink", "lnkd.in", "trib.al", "u.to", "x.gd", "shre.ink", "encurta.net", "migre.me", "qrco.de",
    "linktr.ee", "tinu.be", "1url.com.br", "curt.link", "bit.do", "urlz.fr",
}

# marca -> domínios oficiais (o domínio registrado precisa terminar com um deles)
BRANDS = {
    "bradesco": ["bradesco.com.br", "bradesco"], "itau": ["itau.com.br", "itau-unibanco.com.br", "itau"],
    "santander": ["santander.com.br", "santander.com"], "caixa": ["caixa.gov.br"],
    "bancodobrasil": ["bb.com.br"], "nubank": ["nubank.com.br", "nu.com.mx", "nubank.com"],
    "bancointer": ["bancointer.com.br", "inter.co"], "sicoob": ["sicoob.com.br"], "sicredi": ["sicredi.com.br"],
    "mercadopago": ["mercadopago.com.br", "mercadopago.com", "mercadolivre.com.br"],
    "mercadolivre": ["mercadolivre.com.br", "mercadolibre.com"], "picpay": ["picpay.com"],
    "pagseguro": ["pagseguro.uol.com.br", "pagbank.com.br"], "pagbank": ["pagbank.com.br"],
    "c6bank": ["c6bank.com.br"], "serasa": ["serasa.com.br", "serasaexperian.com.br"],
    "receita": ["gov.br", "receita.fazenda.gov.br"], "correios": ["correios.com.br"], "detran": ["gov.br"],
    "paypal": ["paypal.com"], "microsoft": ["microsoft.com", "live.com", "office.com", "microsoftonline.com", "sharepoint.com"],
    "office365": ["office.com", "microsoft.com", "microsoftonline.com"], "outlook": ["outlook.com", "live.com", "office.com"],
    "docusign": ["docusign.com", "docusign.net"], "dropbox": ["dropbox.com"], "netflix": ["netflix.com"],
    "amazon": ["amazon.com", "amazon.com.br"], "apple": ["apple.com", "icloud.com"], "icloud": ["icloud.com", "apple.com"],
    "whatsapp": ["whatsapp.com", "wa.me"], "instagram": ["instagram.com"], "facebook": ["facebook.com", "fb.com"],
    "gov.br": ["gov.br"], "shopee": ["shopee.com.br"], "magalu": ["magazineluiza.com.br", "magalu.com"],
}

# nomes que quase nunca aparecem por acaso dentro de outra palavra
_DISTINCT = {"bradesco", "santander", "nubank", "bancodobrasil", "bancointer", "mercadopago", "mercadolivre", "picpay",
             "pagseguro", "pagbank", "sicoob", "sicredi", "serasa", "correios", "paypal", "office365", "docusign",
             "netflix", "whatsapp", "instagram", "facebook", "shopee", "c6bank", "icloud", "microsoft"}

EXEC_EXT = {"exe", "scr", "msi", "bat", "cmd", "com", "pif", "js", "jse", "vbs", "vbe", "wsf", "ps1", "hta",
            "jar", "lnk", "reg", "apk", "dll", "cpl", "msc", "iso", "img", "vhd", "docm", "xlsm", "pptm", "appx", "msix"}
ARCHIVE_EXT = {"zip", "rar", "7z", "gz", "tar", "cab", "arj"}

_SECOND_LEVEL = {"com", "net", "org", "gov", "edu", "art", "blog", "eco", "emp", "eng", "ind", "inf", "jus", "leg",
                 "med", "mil", "rec", "srv", "tur", "app", "dev", "log", "adv", "arq", "coop", "nom", "co", "ac", "or", "ne", "go"}


@dataclass
class Risk:
    level: int
    text: str


@dataclass
class LinkCheck:
    url: str
    host: str = ""
    domain: str = ""          # domínio registrado (o que importa: "bradesco.com.br")
    risks: list = field(default_factory=list)

    @property
    def level(self):
        return max((r.level for r in self.risks), default=-1)


def _plain(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def registered_domain(host: str) -> str:
    host = (host or "").lower().strip(".")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$|^\[?[0-9a-f:]+\]?$", re.I)
_DOMAIN_IN_TEXT = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+(?:com|net|org|gov|br|io|co|me|app|info|biz|online|site|xyz|top|ly|gl|us|pt)(?:\.[a-z]{2})?)\b", re.I)


def link_risk(uri: str, shown: str = "") -> LinkCheck:
    uri = (uri or "").strip()
    chk = LinkCheck(uri)
    r = chk.risks
    try:
        u = urlsplit(uri)
    except ValueError:
        r.append(Risk(DANGER, "Endereço malformado."))
        return chk
    scheme = (u.scheme or "").lower()
    if scheme in ("mailto",):
        r.append(Risk(INFO, f"Abre o programa de e-mail para escrever a {unquote(u.path)}."))
        return chk
    if scheme in ("tel", "sms"):
        r.append(Risk(INFO, f"Liga ou manda mensagem para {unquote(u.path)}."))
        return chk
    if scheme not in ("http", "https"):
        r.append(Risk(DANGER, f"Não é um site: o link usa “{scheme or '?'}:”, que pode abrir arquivos ou programas no computador."))
        return chk
    host = (u.hostname or "").lower()
    chk.host, chk.domain = host, registered_domain(host)
    if not host:
        r.append(Risk(DANGER, "O link não tem endereço de site."))
        return chk
    if "@" in (u.netloc or ""):
        r.append(Risk(DANGER, f"O endereço esconde o site verdadeiro: tudo antes do “@” é enfeite; o site é {host}."))
    if _IP.match(host):
        r.append(Risk(DANGER, "O site é só um número (endereço IP), sem nome — empresas de verdade não fazem isso."))
    if "xn--" in host:
        try:
            shown_host = host.encode("ascii").decode("idna")
        except Exception:
            shown_host = host
        r.append(Risk(DANGER, f"O nome do site usa letras de outros alfabetos que imitam letras comuns ({shown_host})."))
    if chk.domain in SHORTENERS or host in SHORTENERS:
        r.append(Risk(WARN, f"É um link encurtado ({chk.domain}): não dá para saber para onde ele leva de verdade."))
    if host.endswith("wa.me") or "whatsapp" in chk.domain:
        num = re.sub(r"\D", "", u.path)
        if num:
            r.append(Risk(INFO, f"Abre uma conversa no WhatsApp com o número +{num}."))
    # nome de banco/empresa conhecida em um site que não é dela
    tokens = [t for t in re.split(r"[.\-_]", host) if t]
    joined = "".join(tokens)
    for brand, official in BRANDS.items():
        if brand == "gov.br":
            hit = ("govbr" in tokens or any(a == "gov" and b == "br" for a, b in zip(tokens, tokens[1:]))) \
                and not host.endswith(".gov.br")
        else:
            hit = brand in tokens or (brand in _DISTINCT and brand in joined)
        if hit and not any(host == o or host.endswith("." + o) for o in official if "." in o):
            r.append(Risk(DANGER, f"O endereço usa o nome “{brand}”, mas o site é {chk.domain}, que não é o oficial."))
            break
    path = unquote(u.path or "").lower()
    ext = path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    if ext in EXEC_EXT:
        r.append(Risk(DANGER, f"O link baixa um programa (.{ext}). Golpes usam isso para instalar vírus."))
    elif ext in ARCHIVE_EXT:
        r.append(Risk(WARN, f"O link baixa um arquivo compactado (.{ext}), que pode conter programas."))
    # o texto mostra um site e o link vai para outro
    if shown:
        m = _DOMAIN_IN_TEXT.search(_plain(shown).replace(" ", ""))
        if m:
            sd = registered_domain(m.group(1).lower())
            if sd and sd != chk.domain and not host.endswith(sd):
                r.append(Risk(DANGER, f"O texto mostra “{m.group(1)}”, mas o link vai para {chk.domain}."))
    if scheme == "http" and not any(x.level == DANGER for x in r):
        r.append(Risk(WARN, "O site não usa conexão segura (https): não digite senhas nem dados de cartão nele."))
    return chk


def shown_text(words, rect):
    """Texto que está de fato dentro da área do link (palavras com o centro dentro dela)."""
    out = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if rect.x0 - 1 <= cx <= rect.x1 + 1 and rect.y0 - 1 <= cy <= rect.y1 + 1:
            out.append(w[4])
    return " ".join(out)


# ------------------------------------------------------------------ documento
@dataclass
class Threat:
    level: int
    title: str
    detail: str = ""
    page: int = -1


_ACTION = re.compile(r"/S\s*/(JavaScript|Launch|SubmitForm|ImportData|URI|GoToR|GoToE)\b")


def _uri_of(obj):
    m = re.search(r"/URI\s*\((.*?)\)\s*[/>]", obj, re.S)
    return m.group(1) if m else ""


def scan(doc, cancel=lambda: False, max_pages=300) -> list[Threat]:
    out: list[Threat] = []
    js = launch = submit = auto = 0
    submit_urls, launch_files = [], []
    try:
        nx = doc.xref_length()
    except Exception:
        nx = 0
    for x in range(1, nx):
        if cancel():
            return out
        try:
            obj = doc.xref_object(x, compressed=True)
        except Exception:
            continue
        if "/JS" in obj and re.search(r"/JS\s*[(<\d]", obj):
            js += 1
        for m in _ACTION.finditer(obj):
            k = m.group(1)
            if k == "JavaScript":
                js += 1
            elif k in ("Launch", "GoToE"):
                launch += 1
                f = re.search(r"/F\s*\((.*?)\)", obj)
                if f:
                    launch_files.append(f.group(1))
            elif k == "SubmitForm":
                submit += 1
                f = re.search(r"/F\s*(?:<<.*?/F\s*)?\((.*?)\)", obj, re.S)
                if f:
                    submit_urls.append(f.group(1))
    try:
        cat = doc.xref_object(doc.pdf_catalog(), compressed=True)
        if "/OpenAction" in cat or "/AA" in cat:
            t, oa = doc.xref_get_key(doc.pdf_catalog(), "OpenAction")
            body = oa
            if t == "xref":
                body = doc.xref_object(int(oa.split()[0]), compressed=True)
            if re.search(r"/S\s*/(JavaScript|Launch|URI|SubmitForm|ImportData)", body) or "/AA" in cat:
                auto = 1
            if "/S/URI" in body.replace(" ", "") or "/S /URI" in body:
                u = _uri_of(body)
                out.append(Threat(DANGER, "Abre um site sozinho ao abrir o documento", u))
    except Exception:
        pass
    if js:
        out.append(Threat(DANGER if (auto or launch) else WARN, "Contém JavaScript (código escondido)",
                          "O Dispersio PDF não executa esse código, mas outros leitores podem executar. "
                          "Documentos comuns (boletos, contratos, notas) não precisam disso."))
    if launch:
        out.append(Threat(DANGER, "Tenta abrir um programa ou arquivo do computador",
                          ", ".join(launch_files[:3]) or "ação “Launch”"))
    if submit:
        dests = sorted({registered_domain(urlsplit(u).hostname or "") or u for u in submit_urls if u})
        out.append(Threat(WARN, "O formulário envia o que for digitado para a internet",
                          ("Destino: " + ", ".join(dests[:3])) if dests else ""))
    if auto and not js and not launch:
        out.append(Threat(WARN, "Executa uma ação sozinho ao ser aberto"))
    # anexos
    try:
        names = doc.embfile_names()
    except Exception:
        names = []
    for n in names:
        try:
            info = doc.embfile_info(n)
            fname = info.get("filename") or info.get("ufilename") or n
        except Exception:
            fname = n
        ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        if ext in EXEC_EXT:
            out.append(Threat(DANGER, f"Tem um programa anexado: {fname}", "Não salve nem abra esse anexo."))
        elif ext in ARCHIVE_EXT:
            out.append(Threat(WARN, f"Tem um arquivo compactado anexado: {fname}", "Pode conter programas; só abra se esperava receber."))
    # links das páginas
    bad_links, fake_button = [], None
    for pno in range(min(doc.page_count, max_pages)):
        if cancel():
            return out
        try:
            page = doc[pno]
            links = [ln for ln in page.get_links() if ln.get("kind") == 2 and ln.get("uri")]
        except Exception:
            continue
        if not links:
            continue
        area = abs(page.rect)
        text_len = None
        words = None
        for ln in links:
            r = ln["from"]
            if words is None:
                try:
                    words = page.get_text("words")
                except Exception:
                    words = []
            chk = link_risk(ln["uri"], shown_text(words, r))
            if chk.level >= DANGER:
                bad_links.append((pno, chk))
            if fake_button is None and area and abs(r) / area > 0.2:
                if text_len is None:
                    text_len = len(page.get_text("text").strip())
                if text_len < 300:
                    fake_button = (pno, chk)
    if fake_button:
        pno, chk = fake_button
        out.append(Threat(DANGER, "Página com “botão” que leva para um site",
                          f"Quase toda a página {pno + 1} é um link para {chk.domain or chk.url}. "
                          "Golpes usam uma imagem de documento borrado com “clique para visualizar” para roubar senhas.", pno))
    seen = set()
    for pno, chk in bad_links:
        key = (chk.domain, chk.risks[0].text if chk.risks else "")
        if key in seen:
            continue
        seen.add(key)
        worst = max(chk.risks, key=lambda x: x.level)
        out.append(Threat(DANGER, f"Link suspeito na página {pno + 1}", worst.text, pno))
        if len(seen) >= 5:
            break
    out.sort(key=lambda t: -t.level)
    return out
