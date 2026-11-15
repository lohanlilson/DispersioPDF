"""“Meus dados”: guardados no computador e usados para preencher formulários com um clique (igual ao celular).

Funciona nos campos de formulário do PDF e, se o PDF só tiver linhas em branco ("Nome: ______"), o programa cria os
campos antes (Detectar campos) e preenche.
"""
import re
import unicodedata
from datetime import date

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox, QLabel, QScrollArea,
                               QWidget, QCheckBox, QPushButton, QHBoxLayout)

from .config import cfg

# chave, rótulo, palavras que identificam o campo (sem acento, minúsculas)
ITEMS = [
    ("nome", "Nome completo", ["nome completo", "nome", "name", "requerente", "contratante", "declarante", "outorgante",
                               "solicitante", "assinante"]),
    ("cpf", "CPF", ["cpf", "cpf mf", "c p f"]),
    ("rg", "RG / Identidade", ["rg", "identidade", "carteira de identidade", "documento de identidade"]),
    ("orgao", "Órgão emissor do RG", ["orgao emissor", "orgao expedidor", "emissor"]),
    ("nascimento", "Data de nascimento", ["data de nascimento", "nascimento", "data nasc", "nasc", "dt nasc"]),
    ("nacionalidade", "Nacionalidade", ["nacionalidade"]),
    ("estadocivil", "Estado civil", ["estado civil"]),
    ("profissao", "Profissão", ["profissao", "ocupacao", "cargo", "funcao"]),
    ("email", "E-mail", ["e mail", "email", "correio eletronico"]),
    ("telefone", "Telefone / Celular", ["telefone", "celular", "fone", "tel", "whatsapp"]),
    ("endereco", "Endereço (rua, número, complemento)", ["endereco", "endereco completo", "logradouro", "rua",
                                                         "residencia", "domicilio"]),
    ("bairro", "Bairro", ["bairro", "setor"]),
    ("cidade", "Cidade", ["cidade", "municipio"]),
    ("uf", "UF", ["uf", "estado"]),
    ("cep", "CEP", ["cep"]),
    ("empresa", "Empresa / Razão social", ["razao social", "empresa", "nome empresarial"]),
    ("cnpj", "CNPJ", ["cnpj"]),
]

# rótulos que parecem "nome", mas são de outra pessoa ou coisa
NOT_MINE = {"mae", "pai", "conjuge", "fantasia", "testemunha", "empresa", "social", "banco", "responsavel", "procurador",
            "filho", "filha", "dependente", "beneficiario", "vendedor", "comprador", "locador", "locatario", "fiador",
            "avalista"}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b(do|da|de|dos|das|n|no|o|a)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load():
    return {k: (cfg.qs.value(f"meus_dados/{k}", "") or "") for k, _l, _w in ITEMS}


def save(data):
    for k, v in data.items():
        cfg.qs.setValue(f"meus_dados/{k}", (v or "").strip())


def has_any():
    return any(v.strip() for v in load().values())


_CANDS = sorted(((k, norm(w)) for k, _l, ws in ITEMS for w in ws), key=lambda t: -len(t[1]))


def match(label, name=""):
    """Qual dado serve para o campo, pelo rótulo e pelo nome interno. "hoje" = data de hoje."""
    for raw in (label, (name or "").rsplit(".", 1)[-1]):
        n = norm(re.sub(r"([a-z])([A-Z])", r"\1 \2", (raw or "").replace("_", " ")))
        if not n:
            continue
        if n in ("data", "data assinatura", "data hoje", "local e data", "local data"):
            return "hoje"
        words = set(n.split())
        for key, w in _CANDS:
            hit = f" {w} " in f" {n} " if " " in w else w in words
            if not hit:
                continue
            if key == "nome" and NOT_MINE & words:
                break
            if key == "uf" and "civil" in words:
                continue
            return key
    return None


def field_label(page, widget):
    """Rótulo do campo: o do PDF ou o texto logo à esquerda/acima dele."""
    lab = (widget.field_label or "").strip()
    r = widget.rect
    try:
        left = page.get_textbox((max(0, r.x0 - 220), r.y0 - 2, r.x0, r.y1 + 2)).strip()
        above = page.get_textbox((r.x0, r.y0 - r.height - 12, r.x1, r.y0)).strip() if not left else ""
    except Exception:
        left = above = ""
    near = (left or above).splitlines()[-1] if (left or above) else ""
    near = re.split(r"[_.]{3,}", near)[-1] if re.search(r"[_.]{3,}", near) else near
    return lab or near or (widget.field_name or "")


def plan(doc, data=None):
    """[(página, xref do campo, rótulo, chave, valor)] para os campos de texto vazios que dá para preencher."""
    import pymupdf
    data = data if data is not None else load()
    today = date.today().strftime("%d/%m/%Y")
    out, seen = [], set()
    for pno in range(doc.page_count):
        page = doc[pno]
        for w in page.widgets() or []:
            if w.field_type != pymupdf.PDF_WIDGET_TYPE_TEXT or (w.field_flags & 1) or (w.field_value or "").strip():
                continue
            if w.field_name in seen:
                continue
            label = field_label(page, w)
            key = match(label, w.field_name)
            if not key:
                continue
            val = today if key == "hoje" else data.get(key, "")
            if val:
                seen.add(w.field_name)
                out.append((pno, w.xref, label, key, val))
    return out


def apply(doc, fills):
    n = 0
    for pno, xref, _label, _key, val in fills:
        page = doc[pno]
        for w in page.widgets() or []:
            if w.xref == xref:
                w.field_value = val
                w.update()
                n += 1
                break
    return n


class MyDataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meus dados")
        self.resize(480, 600)
        lay = QVBoxLayout(self)
        info = QLabel("Guardados só neste computador. Usados em Formulários › Preencher com meus dados.")
        info.setWordWrap(True)
        lay.addWidget(info)
        area = QScrollArea()
        area.setWidgetResizable(True)
        box = QWidget()
        form = QFormLayout(box)
        data = load()
        self.edits = {}
        for k, label, _w in ITEMS:
            e = QLineEdit(data.get(k, ""))
            self.edits[k] = e
            form.addRow(label, e)
        area.setWidget(box)
        lay.addWidget(area, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Salvar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        save({k: e.text() for k, e in self.edits.items()})
        self.accept()


class AutofillDialog(QDialog):
    """Lista do que vai ser preenchido; dá para desmarcar."""

    def __init__(self, parent, fills):
        super().__init__(parent)
        self.setWindowTitle("Preencher com meus dados")
        self.resize(520, 480)
        self.fills = fills
        self.want_edit = False
        lay = QVBoxLayout(self)
        if not fills:
            msg = QLabel("Nenhum campo vazio corresponde aos seus dados salvos. Confira “Meus dados”.")
            msg.setWordWrap(True)
            lay.addWidget(msg)
        area = QScrollArea()
        area.setWidgetResizable(True)
        box = QWidget()
        bl = QVBoxLayout(box)
        self.checks = []
        for pno, _x, label, _k, val in fills:
            c = QCheckBox(f"{val}    — {label[:50]} (pág. {pno + 1})")
            c.setChecked(True)
            bl.addWidget(c)
            self.checks.append(c)
        bl.addStretch()
        area.setWidget(box)
        lay.addWidget(area, 1)
        row = QHBoxLayout()
        edit = QPushButton("Editar meus dados…")
        edit.clicked.connect(self._edit)
        row.addWidget(edit)
        row.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Preencher")
        ok.setDefault(True)
        ok.setEnabled(bool(fills))
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _edit(self):
        self.want_edit = True
        self.reject()

    def chosen(self):
        return [f for f, c in zip(self.fills, self.checks) if c.isChecked()]
