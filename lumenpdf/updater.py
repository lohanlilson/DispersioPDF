"""Atualização automática: consulta o versao.json da última Release no GitHub, baixa o patch (ou o instalador
completo), confere o SHA-256, executa em modo silencioso e reabre o programa."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QProgressBar,
                               QMessageBox, QCheckBox)

from . import __version__, APP_NAME, UPDATE_REPO

VERSION_URL = f"https://github.com/{UPDATE_REPO}/releases/latest/download/versao.json"
UA = {"User-Agent": f"{APP_NAME}/{__version__}"}


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def fetch_info(timeout=10):
    req = urllib.request.Request(VERSION_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pick_package(info):
    """Patch da versão instalada, se existir; senão o instalador completo."""
    p = (info.get("patches") or {}).get(__version__)
    if p:
        return p["url"], p["sha256"], "patch"
    return info["instalador"]["url"], info["instalador"]["sha256"], "instalador"


class CheckThread(QThread):
    result = Signal(object, str)

    def run(self):
        try:
            self.result.emit(fetch_info(), "")
        except Exception as e:
            self.result.emit(None, str(e))


class DownloadThread(QThread):
    progress = Signal(int, int)
    done = Signal(str, str)

    def __init__(self, url, sha):
        super().__init__()
        self.url, self.sha, self.cancel = url, sha, False

    def run(self):
        try:
            name = self.url.rsplit("/", 1)[-1] or "LumenPDF-update.exe"
            path = os.path.join(tempfile.gettempdir(), name)
            req = urllib.request.Request(self.url, headers=UA)
            h = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    if self.cancel:
                        raise RuntimeError("Download cancelado.")
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            if h.hexdigest().lower() != self.sha.lower():
                os.remove(path)
                raise RuntimeError("O arquivo baixado está corrompido (SHA-256 não confere). Tente novamente.")
            self.done.emit(path, "")
        except Exception as e:
            self.done.emit("", str(e))


def run_package(path):
    """Executa o patch/instalador em modo silencioso depois que o programa fechar (ele reabre o programa)."""
    args = f'"{path}" /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS'
    # espera ~3 s para o Lumen PDF terminar de fechar e então executa
    subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & start "" {args}',
                     shell=True, creationflags=0x00000008 | 0x08000000)  # DETACHED | NO_WINDOW


class UpdateDialog(QDialog):
    def __init__(self, win, info):
        super().__init__(win)
        self.win, self.info = win, info
        self.setWindowTitle(f"Atualização do {APP_NAME}")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        url, sha, kind = pick_package(info)
        self.url, self.sha = url, sha
        lay.addWidget(QLabel(f"<h3 style='margin:0'>Nova versão disponível: {info['versao']}</h3>"
                             f"<p>Você está usando a versão {__version__}.</p>"))
        notes = QTextBrowser()
        notes.setMarkdown(info.get("novidades") or "Melhorias e correções.")
        notes.setMaximumHeight(220)
        lay.addWidget(QLabel("<b>Novidades</b>"))
        lay.addWidget(notes)
        size = (info.get("patches", {}).get(__version__) or info.get("instalador", {})).get("tamanho", 0)
        hint = QLabel(("Será baixada apenas a atualização" if kind == "patch" else "Será baixado o instalador completo")
                      + (f" ({size / 1024 / 1024:.1f} MB)" if size else "")
                      + f". O {APP_NAME} será fechado, atualizado e aberto de novo.")
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)
        self.bar = QProgressBar()
        self.bar.hide()
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.skip = QPushButton("Pular esta versão")
        self.later = QPushButton("Lembrar depois")
        self.now = QPushButton("Atualizar agora")
        self.now.setObjectName("Primary")
        row.addWidget(self.skip)
        row.addStretch()
        row.addWidget(self.later)
        row.addWidget(self.now)
        lay.addLayout(row)
        self.skip.clicked.connect(self._skip)
        self.later.clicked.connect(self.reject)
        self.now.clicked.connect(self._start)
        self.th = None

    def _skip(self):
        self.win.settings.setValue("skip_version", self.info["versao"])
        self.reject()

    def _start(self):
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            QMessageBox.information(self, APP_NAME, "A atualização automática funciona no programa instalado.\n"
                                                    f"Baixe manualmente em:\n{self.url}")
            return
        for b in (self.skip, self.later, self.now):
            b.setEnabled(False)
        self.bar.show()
        self.th = DownloadThread(self.url, self.sha)
        self.th.progress.connect(lambda a, b: (self.bar.setMaximum(max(b, 1)), self.bar.setValue(a if b else 0)))
        self.th.done.connect(self._downloaded)
        self.th.start()

    def _downloaded(self, path, err):
        if err:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível baixar a atualização:\n{err}")
            for b in (self.skip, self.later, self.now):
                b.setEnabled(True)
            self.bar.hide()
            return
        self.accept()
        if self.win.close():  # pergunta para salvar documentos abertos
            run_package(path)
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()
        else:
            QMessageBox.information(self.win, APP_NAME, "Atualização baixada. Ela será instalada quando você "
                                                        "fechar todos os documentos e clicar em Atualizar de novo.")

    def reject(self):
        if self.th and self.th.isRunning():
            self.th.cancel = True
        super().reject()


class Updater:
    def __init__(self, win):
        self.win = win
        self.th = None

    def auto_check(self):
        s = self.win.settings
        if s.value("auto_update", "true") == "false":
            return
        last = s.value("last_update_check", "")
        try:
            if last and datetime.now() - datetime.fromisoformat(last) < timedelta(hours=12):
                return
        except ValueError:
            pass
        self.check(silent=True)

    def check(self, silent=False):
        if self.th and self.th.isRunning():
            return
        self.th = CheckThread()
        self.th.result.connect(lambda info, err: self._result(info, err, silent))
        self.th.start()
        if not silent:
            self.win.statusBar().showMessage("Verificando atualizações…", 4000)

    def _result(self, info, err, silent):
        s = self.win.settings
        if err or not info:
            if not silent:
                QMessageBox.warning(self.win, APP_NAME, f"Não foi possível verificar atualizações.\n{err}")
            return
        s.setValue("last_update_check", datetime.now().isoformat(timespec="seconds"))
        latest = info.get("versao", "0")
        if vtuple(latest) <= vtuple(__version__):
            if not silent:
                QMessageBox.information(self.win, APP_NAME, f"Você já está usando a versão mais recente ({__version__}).")
            return
        if silent and s.value("skip_version", "") == latest:
            return
        UpdateDialog(self.win, info).exec()
