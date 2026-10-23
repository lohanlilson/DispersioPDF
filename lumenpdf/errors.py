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


class ErrorDialog(QDialog):
    def __init__(self, parent, summary, report):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — erro")
        self.setMinimumWidth(560)
        self.report = report
        lay = QVBoxLayout(self)
        head = QLabel(f"<span style='font-size:15px; font-weight:600'>Algo deu errado</span><br>{summary}")
        head.setWordWrap(True)
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)
        info = QLabel("Você pode enviar este relatório ao desenvolvedor para que o problema seja corrigido "
                      "numa próxima atualização. Nenhum documento é enviado — só os dados técnicos abaixo.")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        self.text = QPlainTextEdit(report)
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
        copy = QPushButton("Copiar relatório")
        copy.clicked.connect(self._copy)
        row.addWidget(copy)
        row.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        send = QPushButton("Enviar por e-mail")
        send.setObjectName("Primary")
        send.clicked.connect(self._send)
        row.addWidget(close)
        row.addWidget(send)
        lay.addLayout(row)

    def _full(self):
        note = self.user_note.toPlainText().strip()
        return (f"O que o usuário fazia: {note}\n\n" if note else "") + self.report

    def _copy(self):
        QGuiApplication.clipboard().setText(self._full())
        self.note.setText("Relatório copiado. Cole num e-mail para " + EMAIL)

    def _send(self):
        body = self._full()
        if len(body) > 1800:  # limite prático do mailto
            body = body[:1800] + "\n…(relatório completo copiado para a área de transferência — cole aqui)"
            QGuiApplication.clipboard().setText(self._full())
        subject = f"{APP_NAME} {__version__} — relatório de erro"
        url = f"mailto:{EMAIL}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        if not QDesktopServices.openUrl(QUrl(url)):
            self._copy()
            return
        self.accept()


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
