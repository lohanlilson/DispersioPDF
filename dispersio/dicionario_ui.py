"""Janelinha do dicionário (duplo clique numa palavra ou botão direito › Significado)."""
import html
import urllib.parse

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget

from . import dicionario as D


class _Lookup(QThread):
    done = Signal(object)

    def __init__(self, word, lang):
        super().__init__()
        self.word, self.lang = word, lang

    def run(self):
        try:
            self.done.emit(D.lookup(self.word, self.lang))
        except Exception:
            self.done.emit(None)


class DictPopup(QFrame):
    def __init__(self, win, word, lang, pos):
        super().__init__(win, Qt.Popup)
        self.win, self.word, self.lang = win, D.clean_word(word), lang
        self.setObjectName("DictPopup")
        self.setStyleSheet("QFrame#DictPopup{border:1px solid palette(mid); border-radius:8px; background:palette(base);}"
                           "QLabel{background:transparent;}")
        self.setFixedWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.head = QLabel(f"<span style='font-size:16px; font-weight:600'>{html.escape(self.word)}</span>")
        lay.addWidget(self.head)
        self.body = QLabel("Procurando…")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.RichText)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setMaximumHeight(260)
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.body)
        bl.addStretch()
        area.setWidget(box)
        lay.addWidget(area)
        row = QHBoxLayout()
        speak = QPushButton("🔊 Ouvir")
        speak.clicked.connect(lambda: win.run_tool("speak", text=self.word))
        copy = QPushButton("Copiar")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.word))
        more = QPushButton("Ver mais ↗")
        site = "pt" if lang == "pt" else "en"
        more.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://{site}.wiktionary.org/wiki/{urllib.parse.quote(self.word)}")))
        for b in (speak, copy, more):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.adjustSize()
        scr = (QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()).availableGeometry()
        x = min(max(scr.left(), pos.x() - 40), scr.right() - self.width())
        y = pos.y() + 18 if pos.y() + 18 + 300 < scr.bottom() else pos.y() - 320
        self.move(x, y)
        self.job = _Lookup(self.word, lang)
        self.job.done.connect(self._show)
        self.job.start()

    def _show(self, r):
        if not r:
            self.body.setText("<span style='color:gray'>Não encontrei esta palavra. Sem internet, só aparecem as que você "
                              "já consultou antes.</span>")
            return
        parts = []
        if r.get("translation"):
            parts.append(f"<p style='font-size:14px'>Tradução: <b>{html.escape(r['translation'])}</b></p>")
        last = None
        for pos, d in r.get("defs", [])[:6]:
            if pos and pos != last:
                parts.append(f"<p style='margin:6px 0 2px 0; color:gray'><i>{html.escape(pos)}</i></p>")
                last = pos
            parts.append(f"<p style='margin:0 0 3px 0'>• {html.escape(d)}</p>")
        base = r.get("base")
        if base:
            parts.append(f"<p style='margin:8px 0 2px 0'><b>{html.escape(base[0])}</b> <span style='color:gray'>(forma básica)</span></p>")
            for pos, d in base[1][:4]:
                parts.append(f"<p style='margin:0 0 3px 0'>• {html.escape(d)}</p>")
        parts.append(f"<p style='color:gray; font-size:11px'>Fonte: {html.escape(r.get('source', ''))}</p>")
        self.body.setText("".join(parts))
        self.adjustSize()

    def closeEvent(self, e):
        if self.job.isRunning():
            self.job.done.disconnect()
        super().closeEvent(e)
