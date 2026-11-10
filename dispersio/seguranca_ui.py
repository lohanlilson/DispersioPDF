"""Janelas da proteção contra golpes: confirmar link e faixa de alerta do documento."""
import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFrame,
                               QApplication, QMessageBox)

from .config import cfg
from . import seguranca as seg

_RED, _AMBER, _BLUE = ("#fde8e9", "#d7373f"), ("#fff4e0", "#c77700"), ("#eef3fc", "#1473e6")


def _trusted():
    return {s.strip().lower() for s in (cfg.get("trusted_link_sites") or "").split(",") if s.strip()}


def _trust(domain):
    t = _trusted() | {domain.lower()}
    cfg.set("trusted_link_sites", ",".join(sorted(t)))


class LinkDialog(QDialog):
    def __init__(self, parent, chk: seg.LinkCheck):
        super().__init__(parent)
        self.setWindowTitle("Abrir link")
        self.setMinimumWidth(480)
        lvl = chk.level
        bg, fg = _RED if lvl >= seg.DANGER else _AMBER if lvl >= seg.WARN else _BLUE
        lay = QVBoxLayout(self)
        head = QLabel()
        head.setWordWrap(True)
        if lvl >= seg.DANGER:
            title = "⚠ Cuidado: este link parece golpe"
        elif lvl >= seg.WARN:
            title = "Atenção antes de abrir este link"
        else:
            title = "Este documento quer abrir um site"
        head.setText(f"<span style='font-size:15px; font-weight:600; color:{fg}'>{title}</span>")
        lay.addWidget(head)
        site = QLabel()
        site.setTextFormat(Qt.RichText)
        site.setWordWrap(True)
        dom = html.escape(chk.domain or chk.url)
        url = html.escape(chk.url if len(chk.url) <= 220 else chk.url[:220] + "…")
        site.setText(f"Site: <b style='font-size:14px'>{dom}</b><br><span style='color:#666'>{url}</span>")
        site.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(site)
        if chk.risks:
            box = QFrame()
            box.setStyleSheet(f"QFrame{{background:{bg}; border:1px solid {fg}; border-radius:6px;}} QLabel{{color:#222; border:none;}}")
            bl = QVBoxLayout(box)
            for r in sorted(chk.risks, key=lambda x: -x.level):
                lb = QLabel(("• " if r.level < seg.DANGER else "⚠ ") + html.escape(r.text))
                lb.setWordWrap(True)
                bl.addWidget(lb)
            lay.addWidget(box)
        if lvl >= seg.DANGER:
            tip = QLabel("Na dúvida, não abra. Entre no site digitando o endereço oficial no navegador, "
                         "ou confirme com quem mandou o documento por outro meio (telefone, aplicativo do banco).")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#555")
            lay.addWidget(tip)
        self.remember = QCheckBox(f"Abrir links de {chk.domain} sem perguntar")
        self.remember.setVisible(lvl < seg.WARN and bool(chk.domain))
        lay.addWidget(self.remember)
        row = QHBoxLayout()
        copy = QPushButton("Copiar endereço")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(chk.url))
        row.addWidget(copy)
        row.addStretch()
        cancel = QPushButton("Não abrir")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Abrir mesmo assim" if lvl >= seg.DANGER else "Abrir")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        (cancel if lvl >= seg.DANGER else ok).setDefault(True)
        (cancel if lvl >= seg.DANGER else ok).setFocus()
        lay.addLayout(row)


def confirm_link(parent, uri, shown=""):
    """True se pode abrir. Pergunta sempre que houver risco; nos demais, conforme a preferência."""
    chk = seg.link_risk(uri, shown)
    if chk.level < seg.WARN:
        if not cfg.get("confirm_links") or (chk.domain and chk.domain.lower() in _trusted()):
            return True
    d = LinkDialog(parent, chk)
    if d.exec() != QDialog.Accepted:
        return False
    if d.remember.isVisible() and d.remember.isChecked():
        _trust(chk.domain)
    return True


class SecurityBar(QFrame):
    """Faixa no topo do documento quando há algo típico de golpe."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.threats = []
        self.setObjectName("SecBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setWordWrap(True)
        more = QPushButton("Detalhes")
        more.clicked.connect(self.details)
        self.clean = QPushButton("Remover o perigo")
        self.clean.setToolTip("Tira JavaScript, ações automáticas e anexos (dá para desfazer)")
        self.clean.clicked.connect(self._clean)
        close = QPushButton("×")
        close.setFlat(True)
        close.setFixedWidth(30)
        close.setStyleSheet("font-size:18px; color:#555; border:none;")
        close.setToolTip("Fechar")
        close.clicked.connect(self.hide)
        for w in (self.icon, self.text, self.clean, more, close):
            lay.addWidget(w, 1 if w is self.text else 0)
        self.hide()

    def show_threats(self, threats):
        self.threats = threats or []
        if not self.threats:
            self.hide()
            return
        top = self.threats[0]
        bg, fg = _RED if top.level >= seg.DANGER else _AMBER
        self.setStyleSheet(f"QFrame#SecBar{{background:{bg}; border:1px solid {fg}; border-radius:8px;}}"
                           f"QFrame#SecBar QLabel{{color:#222; background:transparent;}}")
        self.icon.setText(f"<span style='font-size:18px; color:{fg}'>⚠</span>")
        head = "Este documento pode ser golpe" if top.level >= seg.DANGER else "Atenção a este documento"
        rest = f" (+{len(self.threats) - 1})" if len(self.threats) > 1 else ""
        self.text.setText(f"<b style='color:{fg}'>{head}:</b> {html.escape(top.title)}{rest}")
        self.clean.setVisible(any(t.title.startswith(("Contém JavaScript", "Tenta abrir", "Executa uma ação",
                                                       "Abre um site sozinho", "Tem um programa", "Tem um arquivo compactado"))
                                  for t in self.threats))
        self.show()

    def details(self):
        lines = []
        for t in self.threats:
            mark = "⚠" if t.level >= seg.DANGER else "•"
            lines.append(f"<p><b>{mark} {html.escape(t.title)}</b>" + (f"<br>{html.escape(t.detail)}" if t.detail else "") + "</p>")
        lines.append("<p style='color:#555'>O Dispersio PDF não executa código do documento nem abre sites sem perguntar. "
                     "Se não esperava este arquivo, não digite senhas, não pague e confirme com quem mandou por outro meio.</p>")
        m = QMessageBox(self)
        m.setWindowTitle("Segurança do documento")
        m.setIcon(QMessageBox.Warning)
        m.setTextFormat(Qt.RichText)
        m.setText("".join(lines))
        m.exec()

    def _clean(self):
        from . import ops
        t = self.tab
        t.checkpoint()
        ops.remove_active_content(t.doc)
        t.changed(structure=True)
        rest = [x for x in self.threats if x.title.startswith(("Link suspeito", "Página com", "O formulário"))]
        self.show_threats(rest)
        t.statusMsg.emit("JavaScript, ações automáticas e anexos removidos (Ctrl+Z desfaz).")
