"""Quem assinou pode assinar pela empresa?

Para uma assinatura com e-CNPJ, consulta o quadro de sócios e administradores (QSA) do CNPJ nos dados públicos da
Receita Federal (BrasilAPI; se falhar, CNPJ.ws) e confere se o responsável pelo certificado aparece nele.
A Receita publica o CPF dos sócios mascarado (***456789**): os 6 dígitos do meio são comparados com o CPF do
certificado, além do nome. Só o CNPJ é enviado na consulta. O resultado fica guardado por 7 dias.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request

UA = "DispersioPDF/1.0 (https://github.com/lohanlilson/DispersioPDF)"
VALIDADE = 7 * 24 * 3600
_mem: dict = {}
_lock = threading.Lock()


def _digits(s):
    return re.sub(r"\D", "", s or "")


def norm_nome(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    s = re.sub(r"[^A-Z ]", " ", s)
    return " ".join(w for w in s.split() if w not in ("DE", "DA", "DO", "DAS", "DOS", "E"))


def _cache_file():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "Dispersio PDF")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "socios.json")


def _cache():
    if not _mem:
        try:
            _mem.update(json.load(open(_cache_file(), encoding="utf-8")))
        except Exception:
            pass
    return _mem


def _salvar():
    try:
        with _lock:
            json.dump(_mem, open(_cache_file(), "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def _get_json(url, timeout=12):
    for tentativa in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise LookupError("CNPJ não encontrado na Receita Federal")
            if e.code in (429, 503) and tentativa < 2:
                time.sleep(2 * (tentativa + 1))
                continue
            raise


def _brasilapi(cnpj):
    j = _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    socios = [{"nome": s.get("nome_socio") or "", "doc": s.get("cnpj_cpf_do_socio") or "",
               "qualificacao": s.get("qualificacao_socio") or "",
               "representante": s.get("nome_representante_legal") or "",
               "doc_representante": s.get("cpf_representante_legal") or ""} for s in j.get("qsa") or []]
    return {"razao_social": j.get("razao_social") or "", "situacao": j.get("descricao_situacao_cadastral") or "",
            "natureza": j.get("natureza_juridica") or "", "socios": socios, "fonte": "Receita Federal (BrasilAPI)"}


def _cnpjws(cnpj):
    j = _get_json(f"https://publica.cnpj.ws/cnpj/{cnpj}")
    est = j.get("estabelecimento") or {}
    socios = []
    for s in j.get("socios") or []:
        rep = s.get("representante_legal") or {}
        socios.append({"nome": s.get("nome") or "", "doc": s.get("cpf_cnpj_socio") or "",
                       "qualificacao": (s.get("qualificacao_socio") or {}).get("descricao") or "",
                       "representante": s.get("nome_representante") or rep.get("nome") or "",
                       "doc_representante": s.get("cpf_representante_legal") or ""})
    return {"razao_social": j.get("razao_social") or "", "situacao": est.get("situacao_cadastral") or "",
            "natureza": (j.get("natureza_juridica") or {}).get("descricao") or "", "socios": socios,
            "fonte": "Receita Federal (CNPJ.ws)"}


def consultar(cnpj, usar_cache=True):
    """Dados públicos do CNPJ: razão social, situação, natureza jurídica e sócios/administradores."""
    cnpj = _digits(cnpj)
    if len(cnpj) != 14:
        raise ValueError("CNPJ inválido")
    c = _cache()
    if usar_cache and cnpj in c and time.time() - c[cnpj].get("_em", 0) < VALIDADE:
        return c[cnpj]
    erro = None
    for f in (_brasilapi, _cnpjws):
        try:
            dados = f(cnpj)
            dados["_em"] = time.time()
            c[cnpj] = dados
            _salvar()
            return dados
        except LookupError:
            raise
        except Exception as e:  # noqa: BLE001
            erro = e
    if cnpj in c:                       # sem internet: usa o último resultado, mesmo antigo
        return c[cnpj]
    raise ConnectionError(f"não foi possível consultar a Receita Federal ({erro})")


def _cpf_confere(mascarado, cpf):
    """CPF mascarado da Receita (***456789**) contra o CPF completo do certificado: None se não dá para comparar."""
    m = _digits(mascarado)
    c = _digits(cpf)
    if len(c) != 11 or len(m) != 6 or m == "000000":
        return None
    return c[3:9] == m


def _nome_confere(a, b):
    a, b = norm_nome(a), norm_nome(b)
    return bool(a) and a == b


def conferir(responsavel, cpf, dados):
    """Confere o responsável do e-CNPJ no quadro de sócios. Retorna {nivel: ok|warn|bad|info, texto, socios}."""
    socios = dados.get("socios") or []
    sit = (dados.get("situacao") or "").upper()
    aviso_sit = "" if not sit or sit == "ATIVA" else f" Atenção: a situação do CNPJ na Receita é {sit}."
    base = {"socios": socios, "razao_social": dados.get("razao_social"), "situacao": dados.get("situacao"),
            "fonte": dados.get("fonte")}
    if not responsavel:
        return {**base, "nivel": "warn",
                "texto": "O certificado não informa o responsável, então não dá para conferir no quadro de sócios." + aviso_sit}
    achados = []
    for s in socios:
        for nome, doc, papel in ((s["nome"], s["doc"], s["qualificacao"]),
                                 (s["representante"], s["doc_representante"], f"representante legal de {s['nome']}")):
            if not nome:
                continue
            cpf_ok = _cpf_confere(doc, cpf)
            if _nome_confere(nome, responsavel):
                achados.append((papel, cpf_ok))
            elif cpf_ok and norm_nome(nome).split()[:1] == norm_nome(responsavel).split()[:1]:
                achados.append((papel, True))          # mesmo CPF e primeiro nome (nome abreviado no certificado)
    if achados:
        papel, cpf_ok = next(((p, c) for p, c in achados if c), achados[0])
        if cpf_ok is False:
            return {**base, "nivel": "warn",
                    "texto": f"Há um sócio com o mesmo nome ({papel}), mas o CPF não confere com o do certificado." + aviso_sit}
        return {**base, "nivel": "bad" if aviso_sit else "ok",
                "texto": f"{responsavel} consta no quadro de sócios e administradores como {papel}." + aviso_sit}
    if not socios:
        rs = dados.get("razao_social") or ""
        if norm_nome(responsavel) and norm_nome(responsavel) in norm_nome(rs):
            return {**base, "nivel": "bad" if aviso_sit else "ok",
                    "texto": f"Empresa individual em nome de {responsavel}." + aviso_sit}
        return {**base, "nivel": "info",
                "texto": "A Receita não lista sócios para este tipo de empresa; confira o responsável pelo contrato "
                         "social ou ato constitutivo." + aviso_sit}
    return {**base, "nivel": "bad" if aviso_sit else "warn",
            "texto": f"{responsavel} NÃO consta no quadro de sócios e administradores. Pode ser um procurador: peça a "
                     "procuração e confira se ela dá poderes para assinar este documento." + aviso_sit}


def verificar(cert_info):
    """Para o dicionário 'cert' de signing.validate (só e-CNPJ). Pode levantar ConnectionError/LookupError."""
    cnpj = cert_info.get("cnpj") or cert_info.get("documento")
    if cert_info.get("tipo") != "e-CNPJ" or len(_digits(cnpj)) != 14:
        return None
    return conferir(cert_info.get("responsavel"), cert_info.get("responsavel_cpf"), consultar(cnpj))


__all__ = ["consultar", "conferir", "verificar", "norm_nome"]
