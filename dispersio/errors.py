"""Relatório de erros: registra em arquivo e oferece enviar ao desenvolvedor por e-mail."""
import os
import platform
import sys
import traceback
import urllib.parse
from datetime import datetime

from PySide6.QtCore import QStandardPaths, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
                               QApplication, QTextEdit)

from . import APP_NAME, EMAIL, __version__


def log_dir():
    d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.expanduser("~")
    os.makedirs(d, exist_ok=True)
    return d


def log_path():
    return os.path.join(log_dir(), "erros.log")


def system_info():
    return (f"{APP_NAME} {__version__}\n"
            f"Windows: {platform.platform()}\n"
            f"Python: {platform.python_version()} ({'instalado' if getattr(sys, 'frozen', False) else 'código-fonte'})")


def build_report(summary, details, context=""):
    return (f"Resumo: {summary}\n"
            + (f"Ação: {context}\n" if context else "")
            + f"Data: {datetime.now():%d/%m/%Y %H:%M:%S}\n{system_info()}\n\n{details}")


def write_log(report):
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n" + report + "\n")
        # mantém o arquivo pequeno
        if os.path.getsize(log_path()) > 2_000_000:
            data = open(log_path(), encoding="utf-8", errors="replace").read()[-1_000_000:]
            open(log_path(), "w", encoding="utf-8").write(data)
    except OSError:
        pass


def recent_reports(n=3):
    """Os últimos n relatórios do registro de erros (inclui os que só foram gravados, como os da impressão rápida)."""
    try:
        data = open(log_path(), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    parts = [p.strip() for p in data.split("=" * 70) if p.strip()]
    return ("\n\n" + "-" * 40 + "\n\n").join(parts[-n:])


def _subject(summary=""):
    return f"{APP_NAME} {__version__} — " + (summary[:80] if summary else "relatório de problema")


def mail_url(body, summary=""):
    return f"mailto:{EMAIL}?subject={urllib.parse.quote(_subject(summary))}&body={urllib.parse.quote(body)}"


def gmail_url(body, summary=""):
    """Gmail no navegador: funciona mesmo sem programa de e-mail instalado."""
    return ("https://mail.google.com/mail/?view=cm&fs=1&to=" + urllib.parse.quote(EMAIL)
            + "&su=" + urllib.parse.quote(_subject(summary)) + "&body=" + urllib.parse.quote(body))


def github_url(body, summary=""):
    from . import UPDATE_REPO
    return (f"https://github.com/{UPDATE_REPO}/issues/new?title=" + urllib.parse.quote(_subject(summary))
            + "&body=" + urllib.parse.quote("```\n" + body + "\n```"))


LIMIT = 1800   # links longos demais são cortados pelo navegador / programa de e-mail


class ErrorDialog(QDialog):
    def __init__(self, parent, summary, report, title="Algo deu errado"):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — {'erro' if title == 'Algo deu errado' else 'relatar problema'}")
        self.setMinimumWidth(600)
        self.report = report
        self.summary = summary
        lay = QVBoxLayout(self)
        head = QLabel(f"<span style='font-size:15px; font-weight:600'>{title}</span>" + (f"<br>{summary}" if summary else ""))
        head.setWordWrap(True)
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)
        info = QLabel("Envie este relatório ao desenvolvedor para o problema ser corrigido numa próxima atualização. "
                      "Nenhum documento é enviado — só os dados técnicos abaixo. Você confere tudo antes de enviar.")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        self.text = QPlainTextEdit(report or "(nenhum erro registrado)")
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(170)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self.text)
        self.note = QLabel("O que você estava fazendo? (opcional)")
        lay.addWidget(self.note)
        self.user_note = QTextEdit()
        self.user_note.setFixedHeight(60)
        lay.addWidget(self.user_note)
        row = QHBoxLayout()
        copy = QPushButton("Copiar")
        copy.clicked.connect(self._copy)
        row.addWidget(copy)
        row.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        for label, fn, tip in (("GitHub", github_url, "Abre um chamado no GitHub já preenchido (precisa de conta no GitHub)"),
                               ("Gmail", gmail_url, "Abre o Gmail no navegador já preenchido — não precisa de programa de e-mail"),
                               ("E-mail", mail_url, "Abre o seu programa de e-mail (Outlook etc.) já preenchido")):
            b = QPushButton(f"Enviar por {label}")
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, f=fn: self._send(f))
            if label == "E-mail":
                b.setObjectName("Primary")
            row.addWidget(b)
        lay.addLayout(row)

    def _full(self):
        note = self.user_note.toPlainText().strip()
        return (f"O que o usuário fazia: {note}\n\n" if note else "") + (self.report or "")

    def _copy(self):
        QGuiApplication.clipboard().setText(self._full())
        self.note.setText("Relatório copiado. Cole numa mensagem para " + EMAIL)

    def _send(self, make_url):
        body = self._full()
        if len(body) > LIMIT:
            QGuiApplication.clipboard().setText(body)
            body = body[:LIMIT] + "\n…(o relatório completo foi copiado — cole aqui com Ctrl+V)"
        if not QDesktopServices.openUrl(QUrl(make_url(body, self.summary))):
            self._copy()
            return
        self.accept()


def report_problem(parent):
    """Ajuda › Relatar problema: junta os últimos erros registrados para enviar."""
    rep = recent_reports(3)
    rep = system_info() + ("\n\nÚltimos erros registrados:\n\n" + rep if rep else "\n\n(nenhum erro registrado)")
    ErrorDialog(parent, "", rep, title="Relatar problema ou enviar sugestão").exec()


_busy = False


def report(parent, summary, exc=None, context=""):
    """Registra o erro e mostra o diálogo com opção de envio."""
    global _busy
    details = "".join(traceback.format_exception(exc)) if exc is not None else traceback.format_exc()
    rep = build_report(summary, details, context)
    write_log(rep)
    if _busy or QApplication.instance() is None:
        return
    _busy = True
    try:
        ErrorDialog(parent, summary, rep).exec()
    finally:
        _busy = False


def install(win):
    """Captura erros não tratados (inclusive dentro de eventos do Qt)."""
    def hook(etype, value, tb):
        if issubclass(etype, KeyboardInterrupt):
            return sys.__excepthook__(etype, value, tb)
        try:
            report(win, f"{etype.__name__}: {value}", value.with_traceback(tb), "erro inesperado")
        except Exception:
            sys.__excepthook__(etype, value, tb)
    sys.excepthook = hook
