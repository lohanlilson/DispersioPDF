"""Biblioteca de quadrinhos, mangás e livros: uma pasta; cada subpasta é uma série, cada arquivo um capítulo.

Capa (primeira imagem do primeiro capítulo), % lido, etiquetas (Lendo / Quero ler / Concluído) e favoritos.
"Continuar" abre o primeiro capítulo não terminado, na página em que você parou.
"""
import hashlib
import os
import zipfile

from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtGui import QPixmap, QIcon, QImage, QPainter, QColor, QFont
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem,
                               QComboBox, QFileDialog, QMenu, QListView, QStackedWidget, QWidget)

from .config import cfg
from . import quadrinhos as hq

EXT = hq.COMIC_EXT | hq.BOOK_EXT | {".zip"}
TAGS = [("lendo", "Lendo"), ("quero", "Quero ler"), ("concluido", "Concluído")]


def chapter_progress(path):
    """0..1 ou None se nunca abriu (usa a posição que o leitor guarda)."""
    k = hq.pos_key(path)
    t = int(cfg.qs.value(k + "_t", 0) or 0)
    if not t:
        return None
    return min(1.0, (int(cfg.qs.value(k, 0) or 0) + 1) / t)


def mark_read(path, done=True):
    k = hq.pos_key(path)
    cfg.qs.setValue(k + "_t", 1)
    cfg.qs.setValue(k, 0 if done else -1)


def scan(folder):
    """[(id, nome, [capítulos])], ordem natural."""
    series = []
    try:
        entries = sorted(os.scandir(folder), key=lambda e: hq.natural_key(e.name))
    except OSError:
        return []
    for e in entries:
        if e.is_dir() and not e.name.startswith("."):
            chs = []
            for root, dirs, files in os.walk(e.path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                chs += [os.path.join(root, f) for f in files if os.path.splitext(f)[1].lower() in EXT]
            chs.sort(key=lambda p: hq.natural_key(os.path.relpath(p, e.path)))
            if chs:
                series.append((sid(e.path), e.name, chs))
        elif e.is_file() and os.path.splitext(e.name)[1].lower() in EXT:
            series.append((sid(e.path), os.path.splitext(e.name)[0], [e.path]))
    return series


def sid(path):
    return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode()).hexdigest()[:16]


def series_progress(chs):
    return sum((chapter_progress(c) or 0) for c in chs) / max(1, len(chs))


def tag(s_id, chs):
    t = cfg.qs.value(f"biblioteca/tag/{s_id}", "")
    if t:
        return t
    p = series_progress(chs)
    return "concluido" if p >= 0.995 else ("lendo" if p > 0 else "")


def fav(s_id):
    return cfg.qs.value(f"biblioteca/fav/{s_id}", "false") in ("true", True)


def resume_index(chs):
    for i, c in enumerate(chs):
        p = chapter_progress(c)
        if p is None or p < 0.995:
            return i
    return 0


def cover_bytes(path):
    """Primeira imagem (ordem natural) de um .cbz/.zip, ou a capa do livro/PDF."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".cbz", ".zip") or open(path, "rb").read(2) == b"PK" and ext not in hq.BOOK_EXT:
            with zipfile.ZipFile(path) as z:
                imgs = sorted((n for n in z.namelist() if os.path.splitext(n)[1].lower() in hq.IMG_EXT and not n.startswith("__MACOSX")),
                              key=hq.natural_key)
                return z.read(imgs[0]) if imgs else None
        import pymupdf
        if ext in (".cbr", ".cb7", ".cbt"):
            images, _ = hq.read_comic(path)
            return images[0][1] if images else None
        d = pymupdf.open(path)
        pix = d[0].get_pixmap(dpi=40)
        return pix.tobytes("png")
    except Exception:
        return None


class _CoverThread(QThread):
    done = Signal(str, bytes)

    def __init__(self, items):
        super().__init__()
        self.items = items

    def run(self):
        cache = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache"), "Dispersio PDF", "Capas")
        os.makedirs(cache, exist_ok=True)
        for s_id, first in self.items:
            if self.isInterruptionRequested():
                return
            f = os.path.join(cache, s_id + ".png")
            data = None
            if os.path.exists(f):
                data = open(f, "rb").read()
            else:
                raw = cover_bytes(first)
                if raw:
                    img = QImage.fromData(raw)
                    if not img.isNull():
                        img = img.scaledToWidth(220, Qt.SmoothTransformation)
                        from PySide6.QtCore import QBuffer, QByteArray
                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QBuffer.WriteOnly)
                        img.save(buf, "PNG")
                        data = bytes(ba)
                        try:
                            open(f, "wb").write(data)
                        except OSError:
                            pass
            if data:
                self.done.emit(s_id, data)


def _placeholder(name):
    pm = QPixmap(150, 220)
    pm.fill(QColor("#2a2a2e"))
    p = QPainter(pm)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPointSize(36)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, (name[:1] or "?").upper())
    p.end()
    return pm


class LibraryDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Biblioteca — quadrinhos, mangás e livros")
        self.resize(900, 640)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.series = []
        self.thread = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.folder_lbl = QLabel()
        pick = QPushButton("Escolher pasta…")
        pick.clicked.connect(self._pick)
        self.filter = QComboBox()
        for k, label in [("todos", "Todos"), ("lendo", "Lendo"), ("quero", "Quero ler"), ("concluido", "Concluídos"), ("fav", "Favoritos")]:
            self.filter.addItem(label, k)
        self.filter.currentIndexChanged.connect(self._fill)
        top.addWidget(self.folder_lbl, 1)
        top.addWidget(self.filter)
        top.addWidget(pick)
        lay.addLayout(top)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setIconSize(QSize(150, 220))
        self.grid.setGridSize(QSize(176, 290))
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setWordWrap(True)
        self.grid.setUniformItemSizes(True)
        self.grid.itemActivated.connect(lambda it: self._open_series(it.data(Qt.UserRole)))
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._menu)
        self.stack.addWidget(self.grid)
        # tela da série
        page = QWidget()
        pl = QVBoxLayout(page)
        row = QHBoxLayout()
        back = QPushButton("‹ Biblioteca")
        back.clicked.connect(lambda: (self.stack.setCurrentIndex(0), self._fill()))
        self.s_title = QLabel()
        self.s_title.setStyleSheet("font-size:16px; font-weight:600")
        self.cont = QPushButton("Continuar")
        self.cont.setObjectName("Primary")
        self.cont.clicked.connect(self._continue)
        self.s_tag = QComboBox()
        self.s_tag.addItem("Sem etiqueta (automática)", "")
        for k, label in TAGS:
            self.s_tag.addItem(label, k)
        self.s_tag.currentIndexChanged.connect(self._set_tag)
        self.s_fav = QPushButton("☆ Favorito")
        self.s_fav.setCheckable(True)
        self.s_fav.toggled.connect(self._set_fav)
        for wdg in (back, self.s_title):
            row.addWidget(wdg)
        row.addStretch()
        for wdg in (self.s_tag, self.s_fav, self.cont):
            row.addWidget(wdg)
        pl.addLayout(row)
        self.chapters = QListWidget()
        self.chapters.itemActivated.connect(lambda it: self._open_chapter(it.data(Qt.UserRole)))
        self.chapters.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chapters.customContextMenuRequested.connect(self._ch_menu)
        pl.addWidget(self.chapters, 1)
        self.stack.addWidget(page)
        self.cur = None
        self._load(cfg.qs.value("biblioteca/pasta", ""))

    # ---------------------------------------------------------------- lista de séries
    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta da biblioteca", cfg.qs.value("biblioteca/pasta", "") or os.path.expanduser("~"))
        if d:
            cfg.qs.setValue("biblioteca/pasta", d)
            self._load(d)

    def _load(self, folder):
        self.folder = folder
        if not folder or not os.path.isdir(folder):
            self.folder_lbl.setText("Escolha a pasta onde ficam seus quadrinhos, mangás e livros. Cada subpasta vira uma série.")
            self.series = []
            self._fill()
            return
        self.folder_lbl.setText(folder)
        self.series = scan(folder)
        self.covers = {}
        self._fill()
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.thread.wait(2000)
        self.thread = _CoverThread([(s, chs[0]) for s, _n, chs in self.series])
        self.thread.done.connect(self._cover)
        self.thread.start()

    def _fill(self):
        self.grid.clear()
        f = self.filter.currentData()
        shown = []
        for s_id, name, chs in self.series:
            if f == "fav" and not fav(s_id):
                continue
            if f not in ("todos", "fav") and tag(s_id, chs) != f:
                continue
            shown.append((s_id, name, chs))
        for s_id, name, chs in shown:
            p = series_progress(chs)
            star = "★ " if fav(s_id) else ""
            it = QListWidgetItem(f"{star}{name}\n{len(chs)} cap. · {int(p * 100)}%")
            pm = getattr(self, "covers", {}).get(s_id) or _placeholder(name)
            it.setIcon(QIcon(pm))
            it.setData(Qt.UserRole, s_id)
            it.setToolTip(name)
            self.grid.addItem(it)
        if not shown and self.series:
            self.grid.addItem(QListWidgetItem("Nada aqui ainda."))

    def _cover(self, s_id, data):
        pm = QPixmap()
        pm.loadFromData(data)
        self.covers[s_id] = pm
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            if it.data(Qt.UserRole) == s_id:
                it.setIcon(QIcon(pm))

    def _find(self, s_id):
        return next((s for s in self.series if s[0] == s_id), None)

    def _menu(self, pos):
        it = self.grid.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        s_id = it.data(Qt.UserRole)
        m = QMenu(self)
        for k, label in TAGS:
            m.addAction(f"Marcar como “{label}”", lambda k=k: (cfg.qs.setValue(f"biblioteca/tag/{s_id}", k), self._fill()))
        m.addAction("Etiqueta automática", lambda: (cfg.qs.remove(f"biblioteca/tag/{s_id}"), self._fill()))
        m.addSeparator()
        m.addAction("Tirar dos favoritos" if fav(s_id) else "Favoritar",
                    lambda: (cfg.qs.setValue(f"biblioteca/fav/{s_id}", "false" if fav(s_id) else "true"), self._fill()))
        m.exec(self.grid.mapToGlobal(pos))

    # ---------------------------------------------------------------- tela da série
    def _open_series(self, s_id):
        s = self._find(s_id)
        if not s:
            return
        self.cur = s
        s_id, name, chs = s
        self.s_title.setText(name)
        self.s_tag.blockSignals(True)
        manual = cfg.qs.value(f"biblioteca/tag/{s_id}", "")
        self.s_tag.setCurrentIndex(max(0, self.s_tag.findData(manual)))
        self.s_tag.blockSignals(False)
        self.s_fav.blockSignals(True)
        self.s_fav.setChecked(fav(s_id))
        self.s_fav.setText("★ Favorito" if fav(s_id) else "☆ Favorito")
        self.s_fav.blockSignals(False)
        self._fill_chapters()
        self.stack.setCurrentIndex(1)

    def _fill_chapters(self):
        s_id, name, chs = self.cur
        self.chapters.clear()
        for c in chs:
            p = chapter_progress(c)
            mark = "✓  " if p is not None and p >= 0.995 else (f"{int(p * 100):>3}%  " if p else "      ")
            it = QListWidgetItem(mark + os.path.relpath(c, os.path.join(self.folder, name)) if len(chs) > 1 else mark + os.path.basename(c))
            it.setData(Qt.UserRole, c)
            if p is not None and p >= 0.995:
                it.setForeground(QColor("#888"))
            self.chapters.addItem(it)
        r = resume_index(chs)
        started = chapter_progress(chs[r]) is not None
        self.cont.setText(("Continuar: " if started else "Começar: ") + os.path.splitext(os.path.basename(chs[r]))[0][:40])

    def _set_tag(self):
        if self.cur:
            k = self.s_tag.currentData()
            if k:
                cfg.qs.setValue(f"biblioteca/tag/{self.cur[0]}", k)
            else:
                cfg.qs.remove(f"biblioteca/tag/{self.cur[0]}")

    def _set_fav(self, on):
        if self.cur:
            cfg.qs.setValue(f"biblioteca/fav/{self.cur[0]}", "true" if on else "false")
            self.s_fav.setText("★ Favorito" if on else "☆ Favorito")

    def _ch_menu(self, pos):
        it = self.chapters.itemAt(pos)
        if not it:
            return
        c = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Marcar como lido", lambda: (mark_read(c, True), self._fill_chapters()))
        m.addAction("Marcar como não lido", lambda: (cfg.qs.remove(hq.pos_key(c)), cfg.qs.remove(hq.pos_key(c) + "_t"), self._fill_chapters()))
        m.exec(self.chapters.mapToGlobal(pos))

    def _continue(self):
        if self.cur:
            self._open_chapter(self.cur[2][resume_index(self.cur[2])])

    def _open_chapter(self, path):
        self.win.open_path(path)
        self.win.raise_()
        self.win.activateWindow()

    def showEvent(self, e):
        super().showEvent(e)
        if self.stack.currentIndex() == 1 and self.cur:
            self._fill_chapters()
        else:
            self._fill()

    def closeEvent(self, e):
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.thread.wait(2000)
        super().closeEvent(e)
