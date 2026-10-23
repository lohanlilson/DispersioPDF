"""Tela Início: banner da marca, ferramentas em cartões coloridos e arquivos recentes com miniaturas."""
import hashlib
import os
import subprocess
import sys
from datetime import datetime

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, QStandardPaths, Signal, QUrl
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
                               QLineEdit, QMenu, QSizePolicy, QGraphicsDropShadowEffect)

from . import icons, theme, resource, __version__, AUTHOR, EMAIL, APP_NAME
from .config import cfg

TOOLS = [
    ("open", "open", "Abrir arquivo", "Visualize e comente PDFs", "#7c3aed"),
    ("edittext", "edit", "Editar PDF", "Textos, imagens e links", "#7c3aed"),
    ("merge", "merge", "Combinar arquivos", "Junte vários em um PDF", "#10b981"),
    ("export_word", "convert", "Converter PDF", "Word, Excel ou imagem", "#3b82f6"),
    ("signature", "sign", "Preencher e assinar", "Assine e preencha", "#ec4899"),
    ("certsign", "certificate", "Certificado digital", "A1/A3 ICP-Brasil", "#ec4899"),
    ("ocr", "ocr", "Escanear e OCR", "Torne pesquisável", "#3b82f6"),
    ("compress", "compress", "Comprimir PDF", "Reduza o tamanho", "#3b82f6"),
    ("organize", "organize", "Organizar páginas", "Reordene, gire e exclua", "#10b981"),
    ("protect", "lock", "Proteger", "Senhas e permissões", "#ef4444"),
    ("redact", "redact", "Ocultar", "Tarje dados sigilosos", "#ef4444"),
    ("print", "print", "Imprimir", "Livreto, várias por folha…", "#64748b"),
]


def thumb_dir():
    d = os.path.join(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.expanduser("~"),
                     "miniaturas")
    os.makedirs(d, exist_ok=True)
    return d


def thumb_path(path):
    try:
        st = os.stat(path)
        key = f"{os.path.abspath(path).lower()}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return None
    return os.path.join(thumb_dir(), hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".png")


def make_thumb(path, w=150, h=190):
    """Miniatura da primeira página (com cache em disco)."""
    tp = thumb_path(path)
    if tp is None:
        return None
    if os.path.exists(tp):
        return QPixmap(tp)
    try:
        with pymupdf.open(path) as d:
            if d.needs_pass or not d.page_count:
                return None
            page = d[0]
            z = min(w * 2 / page.rect.width, h * 2 / page.rect.height)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            pix.save(tp)
        return QPixmap(tp)
    except Exception:
        return None


def greeting():
    h = datetime.now().hour
    return "Bom dia" if 5 <= h < 12 else ("Boa tarde" if 12 <= h < 18 else "Boa noite")


class RecentCard(QFrame):
    clicked = Signal(str)

    def __init__(self, path, home):
        super().__init__()
        self.path, self.home = path, home
        self.setObjectName("RecentCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(176, 262)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(156, 180)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setPixmap(QPixmap(resource("assets", "pdfdoc.png")).scaled(72, 72, Qt.KeepAspectRatio,
                                                                              Qt.SmoothTransformation))
        lay.addWidget(self.thumb)
        exists = os.path.exists(path)
        name = QLabel(os.path.basename(path))
        name.setObjectName("RecentName")
        name.setToolTip(path)
        fm = name.fontMetrics()
        name.setText(fm.elidedText(os.path.basename(path), Qt.ElideMiddle, 154))
        lay.addWidget(name)
        when = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %H:%M") if exists else "Não encontrado"
        sub = QLabel(when)
        sub.setObjectName("Muted")
        lay.addWidget(sub)
        if not exists:
            self.setEnabled(False)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(40, 20, 90, 28 if not theme.is_dark else 70))
        self.setGraphicsEffect(shadow)

    def set_thumb(self, pm):
        if pm is None or pm.isNull():
            return
        pm = pm.scaled(150, 176, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        framed = QPixmap(pm.width() + 2, pm.height() + 2)
        framed.fill(QColor(theme.current["border"]))
        p = QPainter(framed)
        p.drawPixmap(1, 1, pm)
        p.end()
        self.thumb.setPixmap(framed)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.path)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction(icons.icon("open"), "Abrir", lambda: self.clicked.emit(self.path))
        m.addAction(icons.icon("open"), "Mostrar na pasta", self._show_folder)
        m.addSeparator()
        m.addAction(icons.icon("close"), "Remover da lista", lambda: self.home.remove_recent(self.path))
        m.exec(e.globalPos())

    def _show_folder(self):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.path)))


class HomePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("HomePage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 26, 36, 18)
        lay.setSpacing(16)

        # ---------- banner
        hero = QFrame()
        hero.setObjectName("Hero")
        hero.setMinimumHeight(176)
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(32, 24, 24, 24)
        text = QVBoxLayout()
        text.setSpacing(6)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(resource("assets", "logo.png")).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        bname = QLabel(f"<span style='font-size:15px; font-weight:700; letter-spacing:0.5px'>{APP_NAME}</span>")
        brand.addWidget(bname)
        brand.addStretch()
        text.addLayout(brand)
        text.addSpacing(6)
        self.hello = QLabel()
        self.hello.setObjectName("HeroTitle")
        text.addWidget(self.hello)
        sub = QLabel("Abra, edite, assine e imprima seus PDFs — tudo num só lugar.")
        sub.setObjectName("HeroSub")
        text.addWidget(sub)
        text.addSpacing(10)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        openb = QPushButton("  Abrir arquivo")
        openb.setObjectName("HeroPrimary")
        openb.setIcon(icons.icon("open", theme.LIGHT["hero_2"]))
        openb.setIconSize(QSize(18, 18))
        openb.setCursor(Qt.PointingHandCursor)
        openb.clicked.connect(lambda: self.win.home_tool("open"))
        btns.addWidget(openb)
        for key, ic, label in (("create_pdf", "createpdf", "Criar PDF"), ("merge", "merge", "Combinar")):
            b = QPushButton("  " + label)
            b.setObjectName("HeroGhost")
            b.setIcon(icons.icon(ic, "#ffffff"))
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.win.home_tool(k))
            btns.addWidget(b)
        hint = QLabel("ou arraste um PDF para esta janela")
        hint.setObjectName("HeroSub")
        btns.addSpacing(8)
        btns.addWidget(hint)
        btns.addStretch()
        text.addLayout(btns)
        hl.addLayout(text, 1)
        self.art = QLabel()
        self.art.setPixmap(QPixmap(resource("assets", "logo.png")).scaled(150, 150, Qt.KeepAspectRatio,
                                                                          Qt.SmoothTransformation))
        hl.addWidget(self.art, 0, Qt.AlignVCenter)
        lay.addWidget(hero)

        # ---------- ferramentas
        h = QLabel("Ferramentas")
        h.setObjectName("H2")
        lay.addWidget(h)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.cards = []
        for key, ic, title, desc, color in TOOLS:
            b = QPushButton(f"  {title}\n  {desc}")
            b.setObjectName("Card")
            b.setIcon(icons.chip(ic, color, 40))
            b.setIconSize(QSize(40, 40))
            b.setMinimumHeight(72)
            b.setMinimumWidth(170)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.win.home_tool(k))
            self.cards.append(b)
        lay.addLayout(self.grid)

        # ---------- recentes
        rh = QHBoxLayout()
        h = QLabel("Recentes")
        h.setObjectName("H2")
        rh.addWidget(h)
        rh.addStretch()
        self.filter = QLineEdit()
        self.filter.setObjectName("Search")
        self.filter.setPlaceholderText("Pesquisar nos recentes")
        self.filter.setFixedWidth(240)
        self.filter.textChanged.connect(lambda _: self._layout_recents())
        rh.addWidget(self.filter)
        clr = QPushButton("Limpar lista")
        clr.clicked.connect(self._clear)
        rh.addWidget(clr)
        lay.addLayout(rh)
        self.recent_box = QWidget()
        self.recent_grid = QGridLayout(self.recent_box)
        self.recent_grid.setContentsMargins(2, 2, 2, 2)
        self.recent_grid.setSpacing(14)
        self.recent_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay.addWidget(self.recent_box)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Muted")
        lay.addWidget(self.empty)
        lay.addStretch(1)
        foot = QLabel(f"{APP_NAME} {__version__}  •  Desenvolvido por {AUTHOR}  •  "
                      f"<a href='mailto:{EMAIL}'>{EMAIL}</a>")
        foot.setObjectName("Muted")
        foot.setWordWrap(True)
        foot.setOpenExternalLinks(True)
        lay.addWidget(foot)

        self.recent_cards = []
        self._pending = []
        self._thumb_timer = QTimer(self, interval=0, timeout=self._next_thumb)
        self.refresh()

    # ---------------------------------------------------------------- layout
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.reflow(self.width())

    def reflow(self, width):
        cols = max(1, min(4, (width - 72) // 250))
        if getattr(self, "_cols", None) != cols:
            self._cols = cols
            for b in self.cards:
                self.grid.removeWidget(b)
            for n, b in enumerate(self.cards):
                self.grid.addWidget(b, n // cols, n % cols)
        rcols = max(1, (width - 72) // 190)
        if getattr(self, "_rcols", None) != rcols:
            self._rcols = rcols
            self._layout_recents()
        self.art.setVisible(width > 820)

    def _layout_recents(self):
        for c in self.recent_cards:
            self.recent_grid.removeWidget(c)
            c.hide()
        q = self.filter.text().lower().strip()
        shown = [c for c in self.recent_cards if not q or q in os.path.basename(c.path).lower()]
        cols = getattr(self, "_rcols", 4) or 4
        for n, c in enumerate(shown):
            self.recent_grid.addWidget(c, n // cols, n % cols)
            c.show()
        if not self.recent_cards:
            self.empty.setText("Nenhum arquivo recente ainda.\nAbra um PDF ou arraste-o para esta janela — "
                               "ele aparecerá aqui com a miniatura da primeira página.")
        elif not shown:
            self.empty.setText("Nenhum arquivo encontrado com esse nome.")
        self.empty.setVisible(not shown)

    # ---------------------------------------------------------------- dados
    def refresh(self):
        self.hello.setText(f"{greeting()}, {cfg.get('author').split(' ')[0]}!")
        for c in self.recent_cards:
            c.deleteLater()
        self.recent_cards = []
        for p in self.win.recent_files():
            card = RecentCard(p, self)
            card.clicked.connect(self.win.open_path)
            self.recent_cards.append(card)
        self._pending = [c for c in self.recent_cards if os.path.exists(c.path)]
        self._thumb_timer.start()
        self._rcols = None
        self.reflow(self.width() or 1200)

    def _next_thumb(self):
        if not self._pending:
            self._thumb_timer.stop()
            return
        card = self._pending.pop(0)
        try:
            card.set_thumb(make_thumb(card.path))
        except RuntimeError:  # cartão já destruído
            pass

    def remove_recent(self, path):
        r = [p for p in self.win.recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        self.win.settings.setValue("recent", r)
        self.refresh()

    def _clear(self):
        self.win.settings.setValue("recent", [])
        self.refresh()
