"""Boletos, Pix e chaves de NF-e/CT-e encontrados no documento: conferidos e prontos para copiar.

Lê o texto das páginas (linha digitável, Pix copia e cola, chave de acesso) e, nas primeiras páginas,
os códigos desenhados (código de barras do boleto, QR Code do Pix, código de barras da DANFE).
Confere os dígitos verificadores e avisa quando a linha digitável não bate com o código de barras.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

# ------------------------------------------------------------------ tabelas
BANCOS = {
    "001": "Banco do Brasil", "003": "Banco da Amazônia", "004": "Banco do Nordeste", "021": "Banestes",
    "033": "Santander", "037": "Banpará", "041": "Banrisul", "047": "Banese", "070": "BRB", "077": "Inter",
    "084": "Uniprime Norte do Paraná", "085": "Ailos", "097": "Credisis", "104": "Caixa Econômica Federal",
    "133": "Cresol", "136": "Unicred", "197": "Stone", "208": "BTG Pactual", "212": "Banco Original",
    "218": "BS2", "237": "Bradesco", "260": "Nubank", "290": "PagBank", "323": "Mercado Pago",
    "336": "C6 Bank", "341": "Itaú", "380": "PicPay", "389": "Mercantil do Brasil", "403": "Cora",
    "422": "Safra", "633": "Rendimento", "655": "Votorantim", "707": "Daycoval", "741": "Ribeirão Preto",
    "745": "Citibank", "746": "Modal", "748": "Sicredi", "756": "Sicoob",
}
SEGMENTOS = {"1": "Prefeitura", "2": "Saneamento", "3": "Energia elétrica e gás", "4": "Telecomunicações",
             "5": "Órgão governamental", "6": "Carnê ou assemelhado", "7": "Multa de trânsito", "9": "Uso do banco"}
UFS = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
       "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
       "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"}
MODELOS = {"55": "NF-e", "65": "NFC-e", "57": "CT-e", "67": "CT-e OS", "58": "MDF-e", "62": "NFCom", "66": "NF3e"}


# ------------------------------------------------------------------ dígitos verificadores
def mod10(num: str) -> int:
    s, w = 0, 2
    for c in reversed(num):
        p = int(c) * w
        s += p // 10 + p % 10
        w = 3 - w
    return (10 - s % 10) % 10


def mod11_boleto(num: str) -> int:
    """DV geral do boleto bancário: 0, 10 e 11 viram 1."""
    s, w = 0, 2
    for c in reversed(num):
        s += int(c) * w
        w = 2 if w == 9 else w + 1
    dv = 11 - s % 11
    return 1 if dv in (0, 10, 11) else dv


def mod11_zero(num: str) -> int:
    """Módulo 11 com resto 0 ou 1 virando 0 (arrecadação e chave de acesso). Aceita letras (CNPJ alfanumérico)."""
    s, w = 0, 2
    for c in reversed(num):
        s += (ord(c) - 48) * w
        w = 2 if w == 9 else w + 1
    r = s % 11
    return 0 if r in (0, 1) else 11 - r


def crc16(data: str) -> str:
    """CRC16-CCITT (polinômio 0x1021, início 0xFFFF) usado no Pix copia e cola."""
    crc = 0xFFFF
    for b in data.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


# ------------------------------------------------------------------ resultado
@dataclass
class Item:
    kind: str                    # boleto | arrecadacao | pix | nfe
    page: int
    copy: str                    # o que vai para a área de transferência
    title: str                   # "Boleto Bradesco", "Pix", "NF-e nº 1234"
    details: list = field(default_factory=list)   # [(rótulo, valor)]
    ok: bool = True
    problem: str = ""
    source: str = "texto"        # texto | código | texto e código
    key: str = ""                # identidade para juntar texto e código (código de barras de 44 dígitos, chave...)
    rect: tuple | None = None    # área na página (pontos do PDF), quando conhecida

    @property
    def copy_label(self):
        return {"boleto": "Copiar linha digitável", "arrecadacao": "Copiar linha digitável",
                "pix": "Copiar Pix copia e cola", "nfe": "Copiar chave de acesso"}[self.kind]

    @property
    def summary(self):
        d = dict(self.details)
        parts = [d.get("Valor"), d.get("Vencimento"), d.get("Recebedor"), d.get("Emitente")]
        return " · ".join(p for p in parts if p)


def money(cents: int) -> str:
    s = f"{cents / 100:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_cnpj(s: str) -> str:
    if len(s) == 14:
        return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"
    return s


def due_date(fator: int, today: date | None = None) -> date | None:
    """Fator de vencimento: dias desde 07/10/1997; em 22/02/2025 voltou a 1000 (base nova 29/05/2022)."""
    if fator == 0:
        return None
    today = today or date.today()
    cands = [date(1997, 10, 7) + timedelta(days=fator), date(2022, 5, 29) + timedelta(days=fator)]
    return min(cands, key=lambda d: abs((d - today).days))


# ------------------------------------------------------------------ boleto bancário
def boleto_barcode_ok(bc: str) -> bool:
    return len(bc) == 44 and bc.isdigit() and bc[0] != "8" and int(bc[4]) == mod11_boleto(bc[:4] + bc[5:])


def boleto_line_to_barcode(ld: str) -> str:
    return ld[0:4] + ld[32] + ld[33:47] + ld[4:9] + ld[10:20] + ld[21:31]


def boleto_barcode_to_line(bc: str) -> str:
    livre = bc[19:]
    c1 = bc[0:4] + livre[0:5]
    c2 = livre[5:15]
    c3 = livre[15:25]
    return c1 + str(mod10(c1)) + c2 + str(mod10(c2)) + c3 + str(mod10(c3)) + bc[4] + bc[5:19]


def fmt_boleto(ld: str) -> str:
    return f"{ld[0:5]}.{ld[5:10]} {ld[10:15]}.{ld[15:21]} {ld[21:26]}.{ld[26:32]} {ld[32]} {ld[33:47]}"


def check_boleto_line(ld: str) -> str:
    """'' se a linha digitável confere; senão, o problema encontrado."""
    bad = [n for n, (a, b) in enumerate([(0, 9), (10, 20), (21, 31)], 1) if mod10(ld[a:b]) != int(ld[b])]
    if bad:
        return "Dígito errado no " + " e ".join(f"{n}º" for n in bad) + " campo da linha digitável"
    if not boleto_barcode_ok(boleto_line_to_barcode(ld)):
        return "O dígito verificador geral (5º campo... 4º grupo) não confere"
    return ""


def boleto_item(page: int, ld: str, today=None) -> Item:
    bc = boleto_line_to_barcode(ld)
    banco = BANCOS.get(ld[:3])
    det = [("Banco", f"{ld[:3]} – {banco}" if banco else ld[:3])]
    valor = int(bc[9:19])
    det.append(("Valor", money(valor) if valor else "não informado (preencher na hora de pagar)"))
    venc = due_date(int(bc[5:9]), today)
    if venc:
        det.append(("Vencimento", venc.strftime("%d/%m/%Y")))
    det.append(("Linha digitável", fmt_boleto(ld)))
    problem = check_boleto_line(ld)
    if problem.startswith("O dígito verificador geral"):
        problem = "O dígito verificador geral não confere (o número foi alterado ou digitado errado)"
    return Item("boleto", page, ld, f"Boleto {banco}" if banco else "Boleto", det, not problem, problem, key=bc)


# ------------------------------------------------------------------ arrecadação (contas de consumo, tributos)
def arrec_mod(bc: str):
    return mod10 if bc[2] in "67" else mod11_zero


def arrec_barcode_ok(bc: str) -> bool:
    if len(bc) != 44 or not bc.isdigit() or bc[0] != "8" or bc[2] not in "6789":
        return False
    return int(bc[3]) == arrec_mod(bc)(bc[:3] + bc[4:])


def arrec_line_to_barcode(ld: str) -> str:
    return "".join(ld[i * 12:i * 12 + 11] for i in range(4))


def arrec_barcode_to_line(bc: str) -> str:
    m = arrec_mod(bc)
    return "".join(bc[i * 11:(i + 1) * 11] + str(m(bc[i * 11:(i + 1) * 11])) for i in range(4))


def fmt_arrec(ld: str) -> str:
    return " ".join(f"{ld[i * 12:i * 12 + 11]}-{ld[i * 12 + 11]}" for i in range(4))


def check_arrec_line(ld: str) -> str:
    if ld[0] != "8" or ld[2] not in "6789":
        return "não é arrecadação"
    m = mod10 if ld[2] in "67" else mod11_zero
    bad = [i + 1 for i in range(4) if m(ld[i * 12:i * 12 + 11]) != int(ld[i * 12 + 11])]
    if bad:
        return "Dígito errado no " + " e ".join(f"{n}º" for n in bad) + " bloco da linha digitável"
    if not arrec_barcode_ok(arrec_line_to_barcode(ld)):
        return "O dígito verificador geral não confere (o número foi alterado ou digitado errado)"
    return ""


def arrec_item(page: int, ld: str) -> Item:
    bc = arrec_line_to_barcode(ld)
    seg = SEGMENTOS.get(bc[1], "Arrecadação")
    det = [("Tipo", seg)]
    if bc[2] in "68":
        v = int(bc[4:15])
        det.append(("Valor", money(v) if v else "não informado"))
    det.append(("Linha digitável", fmt_arrec(ld)))
    problem = check_arrec_line(ld)
    return Item("arrecadacao", page, ld, f"Conta / tributo – {seg}", det, not problem, problem, key=bc)


# ------------------------------------------------------------------ chave de acesso (NF-e, CT-e, NFC-e, MDF-e)
CHAVE_RE = re.compile(r"^\d{6}[0-9A-Z]{12}\d{2}\d{2}\d{3}\d{9}\d\d{8}\d$")


def chave_plausible(ch: str) -> bool:
    return (len(ch) == 44 and bool(CHAVE_RE.match(ch)) and ch[:2] in UFS and 1 <= int(ch[4:6]) <= 12
            and ch[20:22] in MODELOS)


def chave_ok(ch: str) -> bool:
    return chave_plausible(ch) and int(ch[43]) == mod11_zero(ch[:43])


def fmt_chave(ch: str) -> str:
    return " ".join(ch[i:i + 4] for i in range(0, 44, 4))


def chave_item(page: int, ch: str) -> Item:
    mod = MODELOS[ch[20:22]]
    numero, serie = int(ch[25:34]), int(ch[22:25])
    det = [("Emitente", f"CNPJ {fmt_cnpj(ch[6:20])}" if ch[6:9] != "000" or not ch[6:20].isdigit()
            else f"CPF {ch[9:12]}.{ch[12:15]}.{ch[15:18]}-{ch[18:20]}"),
           ("Número / série", f"{numero} / {serie}"),
           ("Emissão", f"{ch[4:6]}/20{ch[2:4]} – {UFS[ch[:2]]}"),
           ("Chave de acesso", fmt_chave(ch))]
    ok = chave_ok(ch)
    return Item("nfe", page, ch, f"{mod} nº {numero}", det, ok,
                "" if ok else "O dígito verificador da chave não confere (número alterado ou digitado errado)", key=ch)


# ------------------------------------------------------------------ Pix copia e cola (BR Code)
def parse_tlv(s: str) -> dict | None:
    out, i = {}, 0
    while i < len(s):
        if i + 4 > len(s) or not s[i:i + 4].isdigit():
            return None
        tag, n = s[i:i + 2], int(s[i + 2:i + 4])
        if i + 4 + n > len(s):
            return None
        out[tag] = s[i + 4:i + 4 + n]
        i += 4 + n
    return out


def pix_extract(text: str) -> str | None:
    """Recorta um BR Code válido a partir de '000201' (lendo campo a campo até o CRC)."""
    i = 0
    while i < len(text):
        tag, n = text[i:i + 2], text[i + 2:i + 4]
        if len(n) < 2 or not (tag.isdigit() and n.isdigit()):
            return None
        i += 4 + int(n)
        if i > len(text):
            return None
        if tag == "63":
            return text[:i]
    return None


def pix_item(page: int, code: str) -> Item | None:
    top = parse_tlv(code)
    if not top or top.get("00") != "01" or "63" not in top:
        return None
    acc = None
    for t in range(26, 52):
        sub = parse_tlv(top.get(f"{t:02d}", "")) if f"{t:02d}" in top else None
        if sub and sub.get("00", "").lower() == "br.gov.bcb.pix":
            acc = sub
            break
    if acc is None:
        return None
    det = []
    if top.get("59"):
        det.append(("Recebedor", top["59"].strip()))
    if top.get("60"):
        det.append(("Cidade", top["60"].strip()))
    if top.get("54"):
        try:
            det.append(("Valor", money(round(float(top["54"]) * 100))))
        except ValueError:
            pass
    else:
        det.append(("Valor", "livre (definido na hora de pagar)"))
    if acc.get("01"):
        det.append(("Chave Pix", acc["01"]))
    elif acc.get("25"):
        det.append(("Cobrança", "Pix dinâmico (QR do banco)"))
    if acc.get("02"):
        det.append(("Mensagem", acc["02"]))
    extra = parse_tlv(top.get("62", "")) or {}
    if extra.get("05") and extra["05"] != "***":
        det.append(("Identificador", extra["05"]))
    ok = crc16(code[:-4]) == code[-4:].upper()
    return Item("pix", page, code, "Pix", det, ok,
                "" if ok else "O código Pix está incompleto ou foi alterado (CRC não confere)", key=code)


# ------------------------------------------------------------------ busca no texto
LINE47_RE = re.compile(r"(?<!\d)\d{5}[.\s]?\d{5}\s*\d{5}[.\s]?\d{6}\s*\d{5}[.\s]?\d{6}\s*\d\s*\d{14}(?!\d)")
LINE48_RE = re.compile(r"(?<!\d)8\d{10}[\s\-]?\d\s*\d{11}[\s\-]?\d\s*\d{11}[\s\-]?\d\s*\d{11}[\s\-]?\d(?!\d)")
DIGITS_RE = re.compile(r"(?<![\d.\-])\d(?:\d|[ .\-](?=\d)){43,60}(?![\d])")
RUN_RE = re.compile(r"[0-9A-Z](?:[0-9A-Z]|[ .\-/](?=[0-9A-Z])){43,70}")
PIX_RE = re.compile(r"000201")


def find_in_text(text: str, page: int = 0, today=None) -> list[Item]:
    items: list[Item] = []
    used: set[str] = set()

    def add(it):
        if it and len(set(it.copy)) <= 2:     # 1111..., 0000...: não é código de verdade
            return
        if it and it.key not in used:
            used.add(it.key)
            items.append(it)

    # linhas digitáveis no formato impresso (mostra mesmo com dígito errado, para avisar)
    for m in LINE48_RE.finditer(text):
        ld = re.sub(r"\D", "", m.group())
        if len(ld) == 48 and ld[2] in "6789":
            add(arrec_item(page, ld))
    for m in LINE47_RE.finditer(text):
        ld = re.sub(r"\D", "", m.group())
        if len(ld) == 47:
            add(boleto_item(page, ld, today))
    # números corridos com o tamanho exato (código de barras impresso, linha sem formatação) e válidos
    for m in DIGITS_RE.finditer(text):
        s = re.sub(r"\D", "", m.group())
        if len(s) == 44 and boleto_barcode_ok(s) and s[3] == "9":
            add(boleto_item(page, boleto_barcode_to_line(s), today))
        elif len(s) == 44 and arrec_barcode_ok(s):
            add(arrec_item(page, arrec_barcode_to_line(s)))
        elif len(s) == 47 and s[3] == "9" and not check_boleto_line(s):
            add(boleto_item(page, s, today))
        elif len(s) == 48 and not check_arrec_line(s):
            add(arrec_item(page, s))
    # chaves de acesso (estrutura conferida: UF, mês, modelo e dígito), mesmo coladas a outros números
    for m in RUN_RE.finditer(text.upper()):
        run = re.sub(r"[ .\-/]", "", m.group())
        for a in range(0, len(run) - 43):
            if chave_ok(run[a:a + 44]):
                add(chave_item(page, run[a:a + 44]))
    # Pix copia e cola (pode estar quebrado em várias linhas)
    flat = re.sub(r"\s*\n\s*", "", text)
    for src in (flat, text):
        for m in PIX_RE.finditer(src):
            code = pix_extract(src[m.start():])
            if code:
                add(pix_item(page, code))
    return items


# ------------------------------------------------------------------ códigos desenhados (código de barras e QR)
def from_barcode(fmt: str, payload: str, page: int, today=None) -> Item | None:
    p = payload.strip()
    if p.startswith("000201"):
        return pix_item(page, p)
    if len(p) == 44 and p.isdigit():
        if fmt != "Code128" and boleto_barcode_ok(p):
            return boleto_item(page, boleto_barcode_to_line(p), today)
        if fmt != "Code128" and arrec_barcode_ok(p):
            return arrec_item(page, arrec_barcode_to_line(p))
        if chave_ok(p):
            return chave_item(page, p)
    return None


def decode_page_image(page, dpi=200):
    """Lê códigos de barras e QR Codes desenhados na página (PyMuPDF). [(formato, conteúdo)]."""
    try:
        import zxingcpp
        import numpy as np
    except Exception:
        return []
    import pymupdf
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, annots=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    F = zxingcpp.BarcodeFormat
    fmts = F.QRCode | F.ITF | F.Code128
    out = []
    for b in zxingcpp.read_barcodes(arr, formats=fmts):
        out.append((b.format.name if hasattr(b.format, "name") else str(b.format), b.text))
    return out


IMAGE_PAGES = 10   # código de barras / QR: só nas primeiras páginas (é o que costuma ter boleto e DANFE)


def scan(doc, today=None, images=True, cancel=lambda: False) -> list[Item]:
    """Tudo o que foi encontrado no documento, por página."""
    found: list[Item] = []
    for pno in range(doc.page_count):
        if cancel():
            break
        page = doc[pno]
        text = page.get_text("text")
        items = find_in_text(text, pno, today)
        if images and pno < IMAGE_PAGES:
            for fmt, payload in decode_page_image(page):
                it = from_barcode(fmt, payload, pno, today)
                if it is None:
                    continue
                it.source = "código"
                twin = next((x for x in items if x.kind == it.kind and x.key == it.key), None)
                if twin:
                    twin.source = "texto e código"
                    continue
                # boleto com linha digitável diferente do código de barras: sinal de adulteração
                if it.kind in ("boleto", "arrecadacao"):
                    for x in items:
                        if x.kind == it.kind and x.source == "texto" and x.key != it.key:
                            x.ok = False
                            x.problem = ("A linha digitável impressa NÃO confere com o código de barras "
                                         "(possível adulteração). Confira com quem emitiu antes de pagar.")
                items.append(it)
        for it in items:
            if it.rect is None:
                it.rect = _locate(page, it)
        found.extend(items)
    return found


def _locate(page, it: Item):
    """Retângulo do item na página (para destacar ao clicar)."""
    try:
        if it.kind == "boleto":
            needles = [it.copy[:5] + "." + it.copy[5:10], it.copy[:5] + it.copy[5:10], it.copy[:10]]
        elif it.kind == "arrecadacao":
            needles = [it.copy[:11]]
        elif it.kind == "nfe":
            needles = [it.copy[:4] + " " + it.copy[4:8], it.copy[:12]]
        else:
            needles = ["000201"]
        for n in needles:
            r = page.search_for(n)
            if r:
                return tuple(r[0])
    except Exception:
        pass
    return None
