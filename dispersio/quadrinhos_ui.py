"""Barra do modo quadrinhos: Webtoon / Página / Mangá, capítulo anterior e próximo, tela cheia."""
import os

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel, QButtonGroup

from .config import cfg
from . import quadrinhos as hq

MODES = [("webtoon", "Webtoon", "Rolagem contínua, sem espaço entre as páginas (manhwa, webtoon)"),
         ("pagina", "Página", "Uma página por vez; setas ou espaço para passar"),
         ("dupla", "Dupla", "Duas páginas lado a lado, como revista (capa sozinha)"),
         ("manga", "Mangá", "Uma página por vez, da direita para a esquerda (← avança)")]


def mode_for(tab):
    """Modo salvo para a série (pasta) ou o sugerido pelo próprio arquivo."""
    src = getattr(tab, "source_path", "") or ""
    key = "hq_modo/" + os.path.normcase(os.path.dirname(src))
    saved = cfg.qs.value(key, "")
    if saved in dict((m[0], 1) for m in MODES):
        return saved
    info = getattr(tab, "comic", {}) or {}
    if info.get("webtoon"):
        return "webtoon"
    if info.get("rtl"):
        return "manga"
    return "pagina"


def set_mode(tab, mode, remember=True):
    v = tab.view
    page = v.current_page()
    v.rtl = mode == "manga"
    v.cover_alone = mode == "dupla"
    v.page_gap = 0 if mode == "webtoon" else 14
    v.page_shadow = mode != "webtoon"
    v.two_page = mode == "dupla"
    v.zoom_mode = "fit_width" if mode == "webtoon" else "fit_page"
    v.relayout()
    v.goto(page)
    tab.comic_mode = mode
    if remember and getattr(tab, "source_path", None):
        cfg.qs.setValue("hq_modo/" + os.path.normcase(os.path.dirname(tab.source_path)), mode)
    bar = getattr(tab, "comic_bar", None)
    if bar:
        bar.sync()


class ComicBar(QFrame):
    def __init__(self, win, tab):
        super().__init__(tab)
        self.win, self.tab = win, tab
        self.setObjectName("ComicBar")
        self.setStyleSheet("QFrame#ComicBar{background:rgba(30,30,34,215); border-radius:10px;}"
                           "QFrame#ComicBar QPushButton{color:#eee; background:transparent; border:none; padding:5px 10px;"
                           " border-radius:6px; font-size:13px;}"
                           "QFrame#ComicBar QPushButton:hover{background:rgba(255,255,255,40);}"
                           "QFrame#ComicBar QPushButton:checked{background:#1473e6; color:white;}"
                           "QFrame#ComicBar QPushButton:disabled{color:#777;}"
                           "QFrame#ComicBar QLabel{color:#ccc; padding:0 6px;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        self.prev_ch = QPushButton("‹ Capítulo")
        self.prev_ch.setToolTip("Capítulo anterior (mesma pasta)")
        self.prev_ch.clicked.connect(lambda: self.chapter(-1))
        lay.addWidget(self.prev_ch)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.btns = {}
        for key, label, tip in MODES:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: set_mode(self.tab, k))
            self.group.addButton(b)
            self.btns[key] = b
            lay.addWidget(b)
        self.info = QLabel()
        lay.addWidget(self.info)
        full = QPushButton("⛶")
        full.setToolTip("Tela cheia (Esc sai)")
        full.clicked.connect(self._full)
        lay.addWidget(full)
        self.next_ch = QPushButton("Capítulo ›")
        self.next_ch.setToolTip("Próximo capítulo (mesma pasta)")
        self.next_ch.clicked.connect(lambda: self.chapter(1))
        lay.addWidget(self.next_ch)
        tab.view.pageChanged.connect(lambda c, n: self._page(c, n))
        self.sync()

    def _full(self):
        self.win.toggle_read_mode()
        if not self.win.isFullScreen():
            self.win.showFullScreen()

    def sync(self):
        m = getattr(self.tab, "comic_mode", "pagina")
        if m in self.btns:
            self.btns[m].setChecked(True)
        src = getattr(self.tab, "source_path", None)
        self.prev_ch.setEnabled(bool(src and hq.neighbor(src, -1)))
        nxt = src and hq.neighbor(src, 1)
        self.next_ch.setEnabled(bool(nxt))
        self.next_ch.setToolTip(f"Próximo capítulo: {os.path.basename(nxt)}" if nxt else "Este é o último capítulo da pasta")
        self._page(self.tab.view.current_page(), self.tab.doc.page_count)

    def _page(self, c, n):
        self.info.setText(f"{c + 1}/{n}")
        last = n and c >= n - (2 if self.tab.view.two_page else 1)
        self.next_ch.setStyleSheet("background:#1473e6; color:white;" if last and self.next_ch.isEnabled() else "")

    def chapter(self, step):
        src = getattr(self.tab, "source_path", None)
        target = src and hq.neighbor(src, step)
        if not target:
            return
        win, old = self.win, self.tab
        mode = getattr(old, "comic_mode", None)
        win.open_path(target)
        new = win.cur()
        if new is not old and new is not None:
            if mode and hasattr(new, "comic_bar"):
                set_mode(new, mode, remember=False)
            new.view.goto(0)
            if not old.modified:                       # não acumula abas: fecha o capítulo anterior
                win.close_tab(win.tab_widgets.index(old))

    def place(self):
        p = self.parentWidget()
        if not p:
            return
        self.adjustSize()
        v = self.tab.view
        o = v.mapTo(p, QPoint(0, 0))
        self.move(o.x() + (v.width() - self.width()) // 2, o.y() + v.height() - self.height() - 14)
        self.raise_()


def apply_comic_mode(win, tab):
    bar = ComicBar(win, tab)
    tab.comic_bar = bar
    set_mode(tab, mode_for(tab), remember=False)
    old = getattr(tab.view, "on_resize", None)

    def on_resize():
        if old:
            old()
        bar.place()
    tab.view.on_resize = on_resize
    bar.show()
    QTimer.singleShot(0, bar.place)
    QTimer.singleShot(100, bar.place)
