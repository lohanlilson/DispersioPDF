"""Gerenciador de impressão: impressoras, cópias, frente e verso, várias páginas por folha, livreto, pôster,
escala, orientação, papel, comentários, escala de cinza, marca d'água, rodapé, predefinições, pré-visualização,
impressão em lote e salvar como PDF."""
import json
import math
import os
import subprocess
import sys
from datetime import datetime

import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer, QMarginsF
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPageLayout, QPageSize, QPen, QPixmap, QPdfWriter,
                           QIcon)
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintDialog
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QComboBox, QSpinBox,
                               QDoubleSpinBox, QCheckBox, QRadioButton, QButtonGroup, QLineEdit, QPushButton,
                               QGroupBox, QStackedWidget, QWidget, QScrollArea, QFrame, QFileDialog, QMessageBox,
                               QProgressDialog, QInputDialog, QToolButton, QApplication, QSizePolicy)

from . import ops, icons
from .config import cfg

PDF_PRINTER = "__pdf__"
MM = 72 / 25.4

DEFAULT_OPTS = dict(
    printer="", copies=1, collate=True, pages="all", range_text="", subset="all", reverse=False,
    mode="size", scaling="fit", custom_scale=100, auto_rotate=True, center=True,
    nup="2", nup_rows=2, nup_cols=2, nup_order="h", nup_borders=False,
    booklet_subset="both", booklet_binding="left",
    poster_scale=200, poster_overlap=10, poster_labels=True, poster_cutmarks=True,
    orientation="auto", paper="", duplex="none", gray=False, content="annots", quality=300,
    footer=False, watermark="", extra_margin=0,
)

NUP_GRID = {"2": (1, 2), "4": (2, 2), "6": (2, 3), "9": (3, 3), "16": (4, 4)}  # (linhas, colunas) em retrato
PAPERS = [(QPageSize.A4, "A4 (210 × 297 mm)"), (QPageSize.Letter, "Carta (216 × 279 mm)"),
          (QPageSize.Legal, "Ofício / Legal (216 × 356 mm)"), (QPageSize.A3, "A3 (297 × 420 mm)"),
          (QPageSize.A5, "A5 (148 × 210 mm)"), (QPageSize.B5, "B5 (176 × 250 mm)")]


# ====================================================================== fontes de páginas
class Source:
    """Um documento a imprimir."""

    def __init__(self, name, doc, current=0, selected=None):
        self.name, self.doc, self.current, self.selected = name, doc, current, selected or []
        self._variants = {}

    def variant(self, content):
        """Documento conforme a opção de comentários: annots | doc | forms."""
        if content == "forms":
            if "forms" not in self._variants:
                d = pymupdf.open("pdf", self.doc.tobytes())
                for page in d:
                    for a in list(page.annots() or []):
                        page.delete_annot(a)
                self._variants["forms"] = d
            base = self._variants["forms"]
        else:
            base = self.doc
        if content != "doc" and ops.has_empty_signature_fields(base):
            # o MuPDF desenha uma etiqueta "SIGN" em campos de assinatura vazios; no papel eles saem em branco
            key = content + "_nosig"
            if key not in self._variants:
                d = pymupdf.open("pdf", base.tobytes())
                ops.remove_empty_signature_fields(d)
                self._variants[key] = d
            return self._variants[key]
        return base


def page_list(sources, o):
    """Lista de (fonte, página) a imprimir."""
    out = []
    for si, src in enumerate(sources):
        n = src.doc.page_count
        if len(sources) > 1 or o["pages"] == "all":
            pages = list(range(n))
        elif o["pages"] == "current":
            pages = [min(src.current, n - 1)]
        elif o["pages"] == "selected":
            pages = sorted(src.selected) or [src.current]
        else:
            pages = ops.parse_ranges(o["range_text"], n) or list(range(n))
        if o["subset"] == "odd":
            pages = [p for p in pages if (p + 1) % 2 == 1]
        elif o["subset"] == "even":
            pages = [p for p in pages if (p + 1) % 2 == 0]
        out += [(si, p) for p in pages]
    return out


def _page_size(sources, item):
    si, p = item
    r = sources[si].doc[p].rect
    return r.width, r.height


# ====================================================================== imposição
class Placement:
    __slots__ = ("si", "page", "dest", "clip", "rot", "border", "label")

    def __init__(self, si, page, dest, clip=None, rot=0, border=False, label=""):
        self.si, self.page, self.dest, self.clip, self.rot, self.border, self.label = si, page, dest, clip, rot, border, label


class Sheet:
    def __init__(self):
        self.items = []
        self.cutmarks = []   # linhas (x0,y0,x1,y1) em pontos
        self.blank = False
        self.footer = ""


def decide_orientation(sources, items, o):
    if o["orientation"] in ("portrait", "landscape"):
        return o["orientation"]
    if not items:
        return "portrait"
    w, h = _page_size(sources, items[0])
    page_land = w > h
    if o["mode"] == "multiple":
        rows, cols = _nup_grid(o)
        cells_wide = cols > rows
        return "landscape" if (cells_wide != page_land) else "portrait"
    if o["mode"] == "booklet":
        return "portrait" if page_land else "landscape"
    if o["mode"] == "poster":
        return "landscape" if page_land else "portrait"
    return "landscape" if page_land and o["auto_rotate"] else "portrait"


def _nup_grid(o):
    if o["nup"] == "custom":
        return max(1, o["nup_rows"]), max(1, o["nup_cols"])
    return NUP_GRID.get(o["nup"], (2, 2))


def _fit(src_w, src_h, cell, mode="fit", custom=100, center=True, auto_rotate=False):
    """Retângulo de destino da página dentro da célula + rotação extra."""
    rot = 0
    cw, ch = cell.width(), cell.height()
    if auto_rotate and (src_w > src_h) != (cw > ch) and abs(src_w - src_h) > 1:
        rot, src_w, src_h = 90, src_h, src_w
    fit = min(cw / src_w, ch / src_h)
    s = {"fit": fit, "actual": 1.0, "shrink": min(1.0, fit), "custom": custom / 100}.get(mode, fit)
    w, h = src_w * s, src_h * s
    if center:
        x, y = cell.x() + (cw - w) / 2, cell.y() + (ch - h) / 2
    else:
        x, y = cell.x(), cell.y()
    return QRectF(x, y, w, h), rot


def impose(sources, o, area_w, area_h):
    """Monta as folhas (cada lado de papel) a partir das opções. Coordenadas em pontos dentro da área imprimível."""
    items = page_list(sources, o)
    footer_h = 14 if o["footer"] else 0
    area = QRectF(0, 0, area_w, area_h - footer_h)
    sheets = []
    mode = o["mode"]
    if mode == "size":
        for si, p in items:
            sh = Sheet()
            w, h = _page_size(sources, (si, p))
            dest, rot = _fit(w, h, area, o["scaling"], o["custom_scale"], o["center"], o["auto_rotate"])
            sh.items.append(Placement(si, p, dest, rot=rot))
            sh.footer = f"{sources[si].name} — página {p + 1}"
            sheets.append(sh)
    elif mode == "multiple":
        rows, cols = _nup_grid(o)
        if area_w > area_h and rows > cols:
            rows, cols = cols, rows
        if area_h > area_w and cols > rows:
            rows, cols = cols, rows
        per = rows * cols
        gap = 6
        cw, ch = (area.width() - gap * (cols - 1)) / cols, (area.height() - gap * (rows - 1)) / rows
        order = []
        for k in range(per):
            if o["nup_order"] in ("h", "hr"):
                r, c = divmod(k, cols)
                if o["nup_order"] == "hr":
                    c = cols - 1 - c
            else:
                c, r = divmod(k, rows)
                if o["nup_order"] == "vr":
                    c = cols - 1 - c
            order.append((r, c))
        for start in range(0, len(items), per):
            sh = Sheet()
            chunk = items[start:start + per]
            for (si, p), (r, c) in zip(chunk, order):
                cell = QRectF(c * (cw + gap), r * (ch + gap), cw, ch)
                w, h = _page_size(sources, (si, p))
                dest, rot = _fit(w, h, cell, "fit", center=True, auto_rotate=o["auto_rotate"])
                sh.items.append(Placement(si, p, dest, rot=rot, border=o["nup_borders"]))
            first, last = chunk[0], chunk[-1]
            sh.footer = f"{sources[first[0]].name} — páginas {first[1] + 1} a {last[1] + 1}"
            sheets.append(sh)
    elif mode == "booklet":
        seq = list(items)
        while len(seq) % 4:
            seq.append(None)
        n = len(seq)
        half = QRectF(0, 0, area.width() / 2, area.height())
        right = QRectF(area.width() / 2, 0, area.width() / 2, area.height())
        for k in range(n // 4):
            for side, (l_idx, r_idx) in (("front", (n - 1 - 2 * k, 2 * k)), ("back", (2 * k + 1, n - 2 - 2 * k))):
                if o["booklet_subset"] != "both" and o["booklet_subset"] != side:
                    continue
                if o["booklet_binding"] == "right":
                    l_idx, r_idx = r_idx, l_idx
                sh = Sheet()
                for idx, cell in ((l_idx, half), (r_idx, right)):
                    it = seq[idx]
                    if it is None:
                        continue
                    w, h = _page_size(sources, it)
                    dest, rot = _fit(w, h, cell, "fit", center=True, auto_rotate=o["auto_rotate"])
                    sh.items.append(Placement(it[0], it[1], dest, rot=rot))
                sh.footer = f"Livreto — folha {k + 1} ({'frente' if side == 'front' else 'verso'})"
                sh.blank = not sh.items
                sheets.append(sh)
    elif mode == "poster":
        s = o["poster_scale"] / 100
        ov = o["poster_overlap"] * MM
        aw, ah = area.width(), area.height()
        sx, sy = max(aw - ov, 10), max(ah - ov, 10)
        for si, p in items:
            w, h = _page_size(sources, (si, p))
            W, H = w * s, h * s
            nx, ny = max(1, math.ceil((W - ov) / sx)), max(1, math.ceil((H - ov) / sy))
            for ty in range(ny):
                for tx in range(nx):
                    x0, y0 = tx * sx, ty * sy
                    x1, y1 = min(x0 + aw, W), min(y0 + ah, H)
                    clip = pymupdf.Rect(x0 / s, y0 / s, x1 / s, y1 / s)
                    sh = Sheet()
                    label = f"{sources[si].name} — pág. {p + 1} — linha {ty + 1}, coluna {tx + 1} ({ny}×{nx})" \
                        if o["poster_labels"] else ""
                    sh.items.append(Placement(si, p, QRectF(0, 0, x1 - x0, y1 - y0), clip=clip, label=label))
                    if o["poster_cutmarks"]:
                        if tx > 0:
                            sh.cutmarks.append((ov, 0, ov, y1 - y0))
                        if ty > 0:
                            sh.cutmarks.append((0, ov, x1 - x0, ov))
                    sh.footer = label
                    sheets.append(sh)
    if o["reverse"] and mode != "booklet":
        sheets.reverse()
    return sheets


# ====================================================================== desenho
def draw_sheet(painter, sheet, sources, o, k, origin, area_w_pt, area_h_pt, preview=False, sheet_no=1, total=1):
    """Desenha a folha no dispositivo. k = pixels por ponto; origin = canto da área imprimível (px)."""
    gray = o["gray"]
    annots = o["content"] != "doc"
    ox, oy = origin
    max_px = 2600 if preview else 9000
    for pl in sheet.items:
        src = sources[pl.si]
        doc = src.variant(o["content"])
        page = doc[pl.page]
        dest = QRectF(ox + pl.dest.x() * k, oy + pl.dest.y() * k, pl.dest.width() * k, pl.dest.height() * k)
        clip = pl.clip if pl.clip is not None else page.rect
        src_w = clip.width if pl.rot == 0 else clip.height
        zoom = dest.width() / max(src_w, 1)
        if preview:
            zoom = min(zoom * 1.6, 6)  # nitidez na tela
        zoom = min(zoom, max_px / max(clip.width, clip.height, 1))
        m = pymupdf.Matrix(zoom, zoom).prerotate(pl.rot)
        try:
            pix = page.get_pixmap(matrix=m, clip=clip, annots=annots, alpha=False,
                                  colorspace=pymupdf.csGRAY if gray else pymupdf.csRGB)
            fmt = QImage.Format_Grayscale8 if gray else QImage.Format_RGB888
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            painter.drawImage(dest, img)
        except Exception:
            painter.fillRect(dest, QColor("#f2f2f2"))
        if pl.border:
            painter.setPen(QPen(QColor(0, 0, 0), max(1.0, 0.6 * k)))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(dest)
        if pl.label:
            f = QFont("Segoe UI")
            f.setPixelSize(max(6, int(7 * k)))
            painter.setFont(f)
            painter.setPen(QColor(60, 60, 60))
            painter.drawText(QRectF(ox + 4 * k, oy + 2 * k, area_w_pt * k, 12 * k), Qt.AlignLeft | Qt.AlignTop, pl.label)
    for x0, y0, x1, y1 in sheet.cutmarks:
        painter.setPen(QPen(QColor(120, 120, 120), max(1.0, 0.5 * k), Qt.DashLine))
        painter.drawLine(QPointF(ox + x0 * k, oy + y0 * k), QPointF(ox + x1 * k, oy + y1 * k))
    if o["watermark"]:
        painter.save()
        f = QFont("Segoe UI", 1, QFont.Bold)
        f.setPixelSize(int(min(area_w_pt, area_h_pt) * 0.13 * k))
        painter.setFont(f)
        painter.setPen(QColor(200, 30, 30, 55) if not gray else QColor(0, 0, 0, 50))
        painter.translate(ox + area_w_pt * k / 2, oy + area_h_pt * k / 2)
        painter.rotate(-40)
        painter.drawText(QRectF(-area_w_pt * k, -area_h_pt * k / 4, area_w_pt * 2 * k, area_h_pt * k / 2),
                         Qt.AlignCenter, o["watermark"])
        painter.restore()
    if o["footer"]:
        f = QFont("Segoe UI")
        f.setPixelSize(max(6, int(7 * k)))
        painter.setFont(f)
        painter.setPen(QColor(90, 90, 90))
        txt = f"{sheet.footer}    •    folha {sheet_no} de {total}    •    impresso em {datetime.now():%d/%m/%Y %H:%M}"
        painter.drawText(QRectF(ox, oy + (area_h_pt - 11) * k, area_w_pt * k, 11 * k), Qt.AlignCenter, txt)


# ====================================================================== impressoras
def printers():
    infos = QPrinterInfo.availablePrinters()
    default = QPrinterInfo.defaultPrinterName()
    return infos, default


def printer_state_text(info):
    if info is None:
        return "Gera um arquivo PDF com o layout escolhido"
    try:
        st = info.state()
        txt = {QPrinter.Idle: "Pronta", QPrinter.Active: "Imprimindo", QPrinter.Aborted: "Trabalho cancelado",
               QPrinter.Error: "Erro"}.get(st, "Pronta")
    except Exception:
        txt = "Pronta"
    extra = []
    if info.isRemote():
        extra.append("rede")
    if info.supportedDuplexModes() and any(m in (QPrinter.DuplexLongSide, QPrinter.DuplexShortSide, QPrinter.DuplexAuto)
                                           for m in info.supportedDuplexModes()):
        extra.append("frente e verso")
    if sys.platform == "win32":
        try:
            import win32print
            h = win32print.OpenPrinter(info.printerName())
            jobs = win32print.EnumJobs(h, 0, 99, 1)
            win32print.ClosePrinter(h)
            if jobs:
                extra.append(f"{len(jobs)} trabalho(s) na fila")
        except Exception:
            pass
    return txt + (f" • {', '.join(extra)}" if extra else "")


# ====================================================================== diálogo
class PrintManager(QDialog):
    def __init__(self, win, sources, title="Imprimir"):
        super().__init__(win)
        self.win, self.sources = win, sources
        self.setWindowTitle(title)
        self.resize(1180, 760)
        self.sheet_idx = 0
        self.sheets = []
        self._driver_printer = None
        self._layout_cache = {}
        self._timer = QTimer(self, singleShot=True, interval=120, timeout=self._rebuild)
        self._build()
        self._load(self._last_opts())
        self._rebuild()

    # ---------------------------------------------------------------- interface
    def _build(self):
        root = QHBoxLayout(self)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setFixedWidth(500)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left = QWidget()
        L = QVBoxLayout(left)
        L.setSpacing(10)
        L.setContentsMargins(0, 0, 12, 0)
        left_scroll.setWidget(left)
        root.addWidget(left_scroll)

        # impressora
        g = QGroupBox("Impressora")
        gl = QGridLayout(g)
        self.printer = QComboBox()
        infos, default = printers()
        self.infos = {i.printerName(): i for i in infos}
        for i in infos:
            self.printer.addItem(icons.icon("print"), i.printerName() + ("  (padrão)" if i.printerName() == default else ""),
                                 i.printerName())
        self.printer.addItem(icons.icon("createpdf"), "Salvar como arquivo PDF", PDF_PRINTER)
        gl.addWidget(self.printer, 0, 0, 1, 3)
        props = QPushButton("Propriedades…")
        props.setToolTip("Configurações do driver da impressora (bandeja, qualidade, acabamento…)")
        props.clicked.connect(self._driver_props)
        queue = QPushButton("Fila de impressão")
        queue.clicked.connect(self._open_queue)
        manage = QPushButton("Impressoras")
        manage.setToolTip("Abrir as impressoras do Windows (adicionar, remover, padrão)")
        manage.clicked.connect(lambda: self._start("ms-settings:printers"))
        gl.addWidget(props, 1, 0)
        gl.addWidget(queue, 1, 1)
        gl.addWidget(manage, 1, 2)
        self.status = QLabel()
        self.status.setObjectName("Muted")
        gl.addWidget(self.status, 2, 0, 1, 3)
        L.addWidget(g)

        # predefinições
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Predefinição:"))
        self.preset = QComboBox()
        self._fill_presets()
        self.preset.activated.connect(self._apply_preset)
        pr.addWidget(self.preset, 1)
        sp = QToolButton()
        icons.bind(sp, "save")
        sp.setToolTip("Salvar as opções atuais como predefinição")
        sp.clicked.connect(self._save_preset)
        dp = QToolButton()
        icons.bind(dp, "trash")
        dp.setToolTip("Excluir predefinição")
        dp.clicked.connect(self._del_preset)
        pr.addWidget(sp)
        pr.addWidget(dp)
        L.addLayout(pr)

        # cópias / cor / frente e verso
        g = QGroupBox("Cópias e cor")
        gl = QGridLayout(g)
        self.copies = QSpinBox()
        self.copies.setRange(1, 999)
        self.collate = QCheckBox("Agrupar cópias")
        self.collate.setToolTip("Imprime 1,2,3 – 1,2,3 em vez de 1,1 – 2,2 – 3,3")
        self.gray = QCheckBox("Imprimir em escala de cinza (preto e branco)")
        self.duplex = QComboBox()
        for label, val in [("Somente frente", "none"), ("Frente e verso — virar na borda longa", "long"),
                           ("Frente e verso — virar na borda curta", "short"),
                           ("Frente e verso manual (vira o papel à mão)", "manual")]:
            self.duplex.addItem(label, val)
        gl.addWidget(QLabel("Cópias:"), 0, 0)
        gl.addWidget(self.copies, 0, 1)
        gl.addWidget(self.collate, 0, 2)
        gl.addWidget(self.gray, 1, 0, 1, 3)
        gl.addWidget(QLabel("Lados:"), 2, 0)
        gl.addWidget(self.duplex, 2, 1, 1, 2)
        L.addWidget(g)

        # páginas
        g = QGroupBox("Páginas a imprimir")
        gl = QGridLayout(g)
        self.pg_group = QButtonGroup(self)
        self.pg_all = QRadioButton("Todas")
        self.pg_cur = QRadioButton("Página atual")
        self.pg_sel = QRadioButton("Páginas selecionadas nas miniaturas")
        self.pg_rng = QRadioButton("Intervalo:")
        self.range = QLineEdit()
        self.range.setPlaceholderText("ex.: 1-3, 5, 8-10")
        for i, b in enumerate((self.pg_all, self.pg_cur, self.pg_sel, self.pg_rng)):
            self.pg_group.addButton(b, i)
        gl.addWidget(self.pg_all, 0, 0)
        gl.addWidget(self.pg_cur, 0, 1)
        gl.addWidget(self.pg_sel, 1, 0, 1, 2)
        gl.addWidget(self.pg_rng, 2, 0)
        gl.addWidget(self.range, 2, 1)
        self.subset = QComboBox()
        for label, val in [("Todas as páginas do intervalo", "all"), ("Somente ímpares", "odd"), ("Somente pares", "even")]:
            self.subset.addItem(label, val)
        self.reverse = QCheckBox("Inverter ordem das páginas")
        gl.addWidget(QLabel("Subconjunto:"), 3, 0)
        gl.addWidget(self.subset, 3, 1)
        gl.addWidget(self.reverse, 4, 0, 1, 2)
        multi = len(self.sources) > 1
        sel_ok = bool(self.sources and self.sources[0].selected) and not multi
        self.pg_sel.setEnabled(sel_ok)
        for w in (self.pg_cur, self.pg_rng, self.range):
            w.setEnabled(not multi)
        if multi:
            note = QLabel(f"{len(self.sources)} arquivos serão impressos na sequência.")
            note.setObjectName("Muted")
            gl.addWidget(note, 5, 0, 1, 2)
        L.addWidget(g)

        # dimensionamento
        g = QGroupBox("Dimensionamento e manipulação de páginas")
        gl = QVBoxLayout(g)
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_btns = {}
        for key, label, ic in [("size", "Tamanho", "fit_page"), ("multiple", "Várias", "thumbs"),
                               ("booklet", "Livreto", "readmode"), ("poster", "Pôster", "fullscreen")]:
            b = QToolButton()
            b.setText(label)
            icons.bind(b, ic)
            b.setIconSize(icons_size())
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setMinimumWidth(78)
            self.mode_group.addButton(b)
            self.mode_btns[key] = b
            mode_row.addWidget(b)
        gl.addLayout(mode_row)
        self.mode_stack = QStackedWidget()
        gl.addWidget(self.mode_stack)
        # tamanho
        w = QWidget()
        wl = QGridLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        self.scaling = QComboBox()
        for label, val in [("Ajustar à área de impressão", "fit"), ("Tamanho real (100%)", "actual"),
                           ("Reduzir páginas grandes", "shrink"), ("Escala personalizada", "custom")]:
            self.scaling.addItem(label, val)
        self.custom_scale = QSpinBox()
        self.custom_scale.setRange(5, 800)
        self.custom_scale.setSuffix(" %")
        self.auto_rotate = QCheckBox("Girar automaticamente conforme a orientação")
        self.center = QCheckBox("Centralizar na folha")
        wl.addWidget(self.scaling, 0, 0)
        wl.addWidget(self.custom_scale, 0, 1)
        wl.addWidget(self.auto_rotate, 1, 0, 1, 2)
        wl.addWidget(self.center, 2, 0, 1, 2)
        self.mode_stack.addWidget(w)
        # várias
        w = QWidget()
        wl = QGridLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        self.nup = QComboBox()
        for v in ("2", "4", "6", "9", "16"):
            self.nup.addItem(f"{v} páginas por folha", v)
        self.nup.addItem("Personalizado", "custom")
        self.nup_rows = QSpinBox()
        self.nup_rows.setRange(1, 10)
        self.nup_cols = QSpinBox()
        self.nup_cols.setRange(1, 10)
        self.nup_order = QComboBox()
        for label, val in [("Horizontal (→ ↓)", "h"), ("Horizontal invertido (← ↓)", "hr"),
                           ("Vertical (↓ →)", "v"), ("Vertical invertido (↓ ←)", "vr")]:
            self.nup_order.addItem(label, val)
        self.nup_borders = QCheckBox("Imprimir borda nas páginas")
        wl.addWidget(self.nup, 0, 0, 1, 4)
        wl.addWidget(QLabel("Linhas:"), 1, 0)
        wl.addWidget(self.nup_rows, 1, 1)
        wl.addWidget(QLabel("Colunas:"), 1, 2)
        wl.addWidget(self.nup_cols, 1, 3)
        wl.addWidget(QLabel("Ordem:"), 2, 0)
        wl.addWidget(self.nup_order, 2, 1, 1, 3)
        wl.addWidget(self.nup_borders, 3, 0, 1, 4)
        self.mode_stack.addWidget(w)
        # livreto
        w = QWidget()
        wl = QGridLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        self.booklet_subset = QComboBox()
        for label, val in [("Frente e verso", "both"), ("Somente frente", "front"), ("Somente verso", "back")]:
            self.booklet_subset.addItem(label, val)
        self.booklet_binding = QComboBox()
        for label, val in [("Encadernação à esquerda", "left"), ("Encadernação à direita", "right")]:
            self.booklet_binding.addItem(label, val)
        tip = QLabel("Dobre as folhas ao meio para formar o livreto. Com impressora sem frente e verso, imprima "
                     "“Somente frente”, recoloque as folhas e imprima “Somente verso”.")
        tip.setWordWrap(True)
        tip.setObjectName("Muted")
        wl.addWidget(QLabel("Lados:"), 0, 0)
        wl.addWidget(self.booklet_subset, 0, 1)
        wl.addWidget(QLabel("Encadernação:"), 1, 0)
        wl.addWidget(self.booklet_binding, 1, 1)
        wl.addWidget(tip, 2, 0, 1, 2)
        self.mode_stack.addWidget(w)
        # pôster
        w = QWidget()
        wl = QGridLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        self.poster_scale = QSpinBox()
        self.poster_scale.setRange(110, 1000)
        self.poster_scale.setSuffix(" %")
        self.poster_overlap = QSpinBox()
        self.poster_overlap.setRange(0, 50)
        self.poster_overlap.setSuffix(" mm")
        self.poster_labels = QCheckBox("Rótulos de posição em cada folha")
        self.poster_cutmarks = QCheckBox("Marcas de corte na sobreposição")
        wl.addWidget(QLabel("Escala:"), 0, 0)
        wl.addWidget(self.poster_scale, 0, 1)
        wl.addWidget(QLabel("Sobreposição:"), 1, 0)
        wl.addWidget(self.poster_overlap, 1, 1)
        wl.addWidget(self.poster_labels, 2, 0, 1, 2)
        wl.addWidget(self.poster_cutmarks, 3, 0, 1, 2)
        self.mode_stack.addWidget(w)
        L.addWidget(g)

        # papel
        g = QGroupBox("Papel e orientação")
        gl = QGridLayout(g)
        self.paper = QComboBox()
        self.orient = QComboBox()
        for label, val in [("Automática", "auto"), ("Retrato", "portrait"), ("Paisagem", "landscape")]:
            self.orient.addItem(label, val)
        self.quality = QComboBox()
        for label, val in [("Rascunho (150 dpi)", 150), ("Normal (300 dpi)", 300), ("Alta (600 dpi)", 600)]:
            self.quality.addItem(label, val)
        self.margin = QSpinBox()
        self.margin.setRange(0, 50)
        self.margin.setSuffix(" mm")
        gl.addWidget(QLabel("Papel:"), 0, 0)
        gl.addWidget(self.paper, 0, 1)
        gl.addWidget(QLabel("Orientação:"), 1, 0)
        gl.addWidget(self.orient, 1, 1)
        gl.addWidget(QLabel("Qualidade:"), 2, 0)
        gl.addWidget(self.quality, 2, 1)
        gl.addWidget(QLabel("Margem extra:"), 3, 0)
        gl.addWidget(self.margin, 3, 1)
        L.addWidget(g)

        # conteúdo e extras
        g = QGroupBox("Conteúdo")
        gl = QGridLayout(g)
        self.content = QComboBox()
        for label, val in [("Documento e marcações", "annots"),
                           ("Somente o documento", "doc"), ("Documento e campos de formulário", "forms")]:
            self.content.addItem(label, val)
        self.footer = QCheckBox("Rodapé com arquivo, página e data")
        self.footer.setToolTip("Imprime no rodapé o nome do arquivo, a página e a data/hora da impressão")
        self.watermark = QLineEdit()
        self.watermark.setPlaceholderText("ex.: CÓPIA, CONFIDENCIAL (vazio = sem marca)")
        self.content.setToolTip("“Documento e marcações” inclui comentários, carimbos e assinaturas")
        gl.addWidget(QLabel("Imprimir:"), 0, 0)
        gl.addWidget(self.content, 0, 1)
        gl.addWidget(self.footer, 1, 0, 1, 2)
        gl.addWidget(QLabel("Marca d'água:"), 2, 0)
        gl.addWidget(self.watermark, 2, 1)
        L.addWidget(g)
        L.addStretch()

        # pré-visualização
        right = QVBoxLayout()
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 420)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setObjectName("Canvas")
        self.preview.setStyleSheet("background: #d9d9d9; border-radius: 8px;")
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.prev_btn = QToolButton()
        icons.bind(self.prev_btn, "prev")
        self.next_btn = QToolButton()
        icons.bind(self.next_btn, "next")
        self.sheet_lbl = QLabel()
        self.sheet_lbl.setAlignment(Qt.AlignCenter)
        self.prev_btn.clicked.connect(lambda: self._go(-1))
        self.next_btn.clicked.connect(lambda: self._go(1))
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.sheet_lbl, 1)
        nav.addWidget(self.next_btn)
        right.addLayout(nav)
        self.summary = QLabel()
        self.summary.setAlignment(Qt.AlignCenter)
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        right.addWidget(self.summary)
        btns = QHBoxLayout()
        self.save_pdf_btn = QPushButton("Salvar como PDF…")
        self.save_pdf_btn.clicked.connect(lambda: self._run(to_pdf=True))
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.print_btn = QPushButton("Imprimir")
        self.print_btn.setObjectName("Primary")
        self.print_btn.clicked.connect(lambda: self._run())
        btns.addWidget(self.save_pdf_btn)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(self.print_btn)
        right.addLayout(btns)
        root.addLayout(right, 1)

        # sinais
        self.printer.currentIndexChanged.connect(self._printer_changed)
        for wdg in (self.duplex, self.subset, self.scaling, self.nup, self.nup_order, self.booklet_subset,
                    self.booklet_binding, self.paper, self.orient, self.content, self.quality):
            wdg.currentIndexChanged.connect(self._changed)
        for wdg in (self.copies, self.custom_scale, self.nup_rows, self.nup_cols, self.poster_scale,
                    self.poster_overlap, self.margin):
            wdg.valueChanged.connect(self._changed)
        for wdg in (self.collate, self.gray, self.reverse, self.auto_rotate, self.center, self.nup_borders,
                    self.poster_labels, self.poster_cutmarks, self.footer):
            wdg.toggled.connect(self._changed)
        self.range.textChanged.connect(lambda _: (self.pg_rng.setChecked(True), self._changed()))
        self.watermark.textChanged.connect(self._changed)
        self.pg_group.idToggled.connect(lambda *_: self._changed())
        self.mode_group.buttonToggled.connect(lambda *_: self._changed())

    # ---------------------------------------------------------------- opções <-> interface
    def _set_combo(self, combo, value):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    def _load(self, o):
        o = {**DEFAULT_OPTS, **(o or {})}
        self._loading = True
        if o["printer"]:
            self._set_combo(self.printer, o["printer"])
        else:
            self._set_combo(self.printer, QPrinterInfo.defaultPrinterName() or PDF_PRINTER)
        self._fill_papers(o["paper"])
        self.copies.setValue(o["copies"])
        self.collate.setChecked(o["collate"])
        self.gray.setChecked(o["gray"])
        self._set_combo(self.duplex, o["duplex"])
        {"all": self.pg_all, "current": self.pg_cur, "selected": self.pg_sel, "range": self.pg_rng}.get(
            o["pages"], self.pg_all).setChecked(True)
        self.range.blockSignals(True)
        self.range.setText(o["range_text"])
        self.range.blockSignals(False)
        self._set_combo(self.subset, o["subset"])
        self.reverse.setChecked(o["reverse"])
        self.mode_btns.get(o["mode"], self.mode_btns["size"]).setChecked(True)
        self._set_combo(self.scaling, o["scaling"])
        self.custom_scale.setValue(o["custom_scale"])
        self.auto_rotate.setChecked(o["auto_rotate"])
        self.center.setChecked(o["center"])
        self._set_combo(self.nup, o["nup"])
        self.nup_rows.setValue(o["nup_rows"])
        self.nup_cols.setValue(o["nup_cols"])
        self._set_combo(self.nup_order, o["nup_order"])
        self.nup_borders.setChecked(o["nup_borders"])
        self._set_combo(self.booklet_subset, o["booklet_subset"])
        self._set_combo(self.booklet_binding, o["booklet_binding"])
        self.poster_scale.setValue(o["poster_scale"])
        self.poster_overlap.setValue(o["poster_overlap"])
        self.poster_labels.setChecked(o["poster_labels"])
        self.poster_cutmarks.setChecked(o["poster_cutmarks"])
        self._set_combo(self.orient, o["orientation"])
        self._set_combo(self.quality, o["quality"])
        self.margin.setValue(o["extra_margin"])
        self._set_combo(self.content, o["content"])
        self.footer.setChecked(o["footer"])
        self.watermark.setText(o["watermark"])
        self._loading = False
        self._printer_changed()

    def opts(self):
        mode = next(k for k, b in self.mode_btns.items() if b.isChecked()) if any(
            b.isChecked() for b in self.mode_btns.values()) else "size"
        pages = {0: "all", 1: "current", 2: "selected", 3: "range"}.get(self.pg_group.checkedId(), "all")
        return dict(
            printer=self.printer.currentData(), copies=self.copies.value(), collate=self.collate.isChecked(),
            pages=pages, range_text=self.range.text(), subset=self.subset.currentData(),
            reverse=self.reverse.isChecked(), mode=mode, scaling=self.scaling.currentData(),
            custom_scale=self.custom_scale.value(), auto_rotate=self.auto_rotate.isChecked(),
            center=self.center.isChecked(), nup=self.nup.currentData(), nup_rows=self.nup_rows.value(),
            nup_cols=self.nup_cols.value(), nup_order=self.nup_order.currentData(),
            nup_borders=self.nup_borders.isChecked(), booklet_subset=self.booklet_subset.currentData(),
            booklet_binding=self.booklet_binding.currentData(), poster_scale=self.poster_scale.value(),
            poster_overlap=self.poster_overlap.value(), poster_labels=self.poster_labels.isChecked(),
            poster_cutmarks=self.poster_cutmarks.isChecked(), orientation=self.orient.currentData(),
            paper=self.paper.currentData(), duplex=self.duplex.currentData(), gray=self.gray.isChecked(),
            content=self.content.currentData(), quality=self.quality.currentData(),
            footer=self.footer.isChecked(), watermark=self.watermark.text().strip(),
            extra_margin=self.margin.value())

    def _changed(self, *_):
        if getattr(self, "_loading", False):
            return
        o = self.opts()
        self.mode_stack.setCurrentIndex(["size", "multiple", "booklet", "poster"].index(o["mode"]))
        self.custom_scale.setEnabled(o["scaling"] == "custom")
        custom = o["nup"] == "custom"
        self.nup_rows.setEnabled(custom)
        self.nup_cols.setEnabled(custom)
        self.collate.setEnabled(o["copies"] > 1)
        if o["mode"] == "booklet" and o["duplex"] == "long" and self._duplex_supported():
            self._set_combo(self.duplex, "short")
        self.sheet_idx = 0
        self._timer.start()

    # ---------------------------------------------------------------- impressora / papel
    def _info(self):
        name = self.printer.currentData()
        return None if name == PDF_PRINTER else self.infos.get(name)

    def _duplex_supported(self):
        info = self._info()
        if info is None:
            return False
        modes = info.supportedDuplexModes()
        return any(m in (QPrinter.DuplexLongSide, QPrinter.DuplexShortSide, QPrinter.DuplexAuto) for m in modes)

    def _fill_papers(self, want=""):
        info = self._info()
        self.paper.blockSignals(True)
        cur = want or self.paper.currentData()
        self.paper.clear()
        sizes = []
        if info is not None:
            try:
                sizes = [(s.id(), s.name()) for s in info.supportedPageSizes()]
            except Exception:
                sizes = []
        if not sizes:
            sizes = [(pid, label) for pid, label in PAPERS]
        seen = set()
        for pid, label in sizes:
            if pid in seen:
                continue
            seen.add(pid)
            nice = dict(PAPERS).get(pid, label)
            self.paper.addItem(nice, int(pid.value) if hasattr(pid, "value") else int(pid))
        default = None
        if info is not None:
            try:
                d = info.defaultPageSize().id()
                default = int(d.value) if hasattr(d, "value") else int(d)
            except Exception:
                pass
        target = cur if cur not in (None, "") else (default if default is not None else int(QPageSize.A4.value))
        i = self.paper.findData(target)
        if i < 0:
            i = self.paper.findData(int(QPageSize.A4.value))
        self.paper.setCurrentIndex(max(i, 0))
        self.paper.blockSignals(False)

    def _printer_changed(self, *_):
        info = self._info()
        self._driver_printer = None
        self._layout_cache.clear()
        if not getattr(self, "_loading", False):
            self._fill_papers()
        self.status.setText(printer_state_text(info))
        dup = self._duplex_supported()
        for i in range(self.duplex.count()):
            val = self.duplex.itemData(i)
            item = self.duplex.model().item(i)
            item.setEnabled(val in ("none", "manual") or dup)
        if not dup and self.duplex.currentData() in ("long", "short"):
            self._set_combo(self.duplex, "none")
        is_pdf = info is None
        self.print_btn.setText("Salvar PDF…" if is_pdf else "Imprimir")
        self.copies.setEnabled(not is_pdf)
        self._changed()

    def _page_layout(self, orientation):
        """(tamanho do papel em pt, retângulo imprimível em pt) para a impressora/papel/orientação."""
        o = self.opts()
        key = (o["printer"], o["paper"], orientation)
        if key in self._layout_cache:
            return self._layout_cache[key]
        ps = QPageSize(QPageSize.PageSizeId(o["paper"])) if o["paper"] is not None else QPageSize(QPageSize.A4)
        orient = QPageLayout.Landscape if orientation == "landscape" else QPageLayout.Portrait
        info = self._info()
        if info is None:
            lay = QPageLayout(ps, orient, QMarginsF(0, 0, 0, 0))
        else:
            pr = self._driver_printer or QPrinter(info, QPrinter.HighResolution)
            pr.setPageSize(ps)
            pr.setPageOrientation(orient)
            lay = pr.pageLayout()
        full = lay.fullRectPoints()
        paint = lay.paintRectPoints()
        res = (QSizeF(full.width(), full.height()), QRectF(paint))
        self._layout_cache[key] = res
        return res

    def _driver_props(self):
        info = self._info()
        if info is None:
            QMessageBox.information(self, "Imprimir", "Escolha uma impressora para abrir as propriedades do driver.")
            return
        pr = self._driver_printer or QPrinter(info, QPrinter.HighResolution)
        o = self.opts()
        pr.setPageSize(QPageSize(QPageSize.PageSizeId(o["paper"])))
        dlg = QPrintDialog(pr, self)
        dlg.setWindowTitle("Propriedades da impressora")
        if dlg.exec() == QDialog.Accepted:
            self._driver_printer = pr
            self._layout_cache.clear()
            try:
                pid = pr.pageLayout().pageSize().id()
                self._set_combo(self.paper, int(pid.value) if hasattr(pid, "value") else int(pid))
            except Exception:
                pass
            self._set_combo(self.duplex, {QPrinter.DuplexLongSide: "long", QPrinter.DuplexShortSide: "short"}.get(
                pr.duplex(), self.duplex.currentData()))
            self.gray.setChecked(pr.colorMode() == QPrinter.GrayScale)
            if pr.copyCount() > 1:
                self.copies.setValue(pr.copyCount())
            self._changed()

    def _open_queue(self):
        info = self._info()
        if info is None or sys.platform != "win32":
            self._start("ms-settings:printers")
            return
        subprocess.Popen(["rundll32.exe", "printui.dll,PrintUIEntry", "/o", "/n", info.printerName()],
                         creationflags=0x08000000)

    def _start(self, target):
        if sys.platform == "win32":
            os.startfile(target)

    # ---------------------------------------------------------------- predefinições
    def _presets(self):
        try:
            return json.loads(cfg.qs.value("print/presets", "{}") or "{}")
        except ValueError:
            return {}

    def _last_opts(self):
        try:
            o = json.loads(cfg.qs.value("print/last", "{}") or "{}")
        except ValueError:
            o = {}
        o.update(pages="all", range_text="", copies=1)
        if self.sources and self.sources[0].selected and len(self.sources[0].selected) > 1:
            o["pages"] = "selected"
        return o

    def _fill_presets(self):
        self.preset.clear()
        self.preset.addItem("Últimas opções usadas", "__last__")
        builtin = {"Rascunho econômico (2 por folha, P&B)": dict(mode="multiple", nup="2", gray=True, quality=150),
                   "Livreto": dict(mode="booklet", duplex="short"),
                   "Frente e verso": dict(duplex="long"),
                   "Somente o documento (sem comentários)": dict(content="doc")}
        for name, o in builtin.items():
            self.preset.addItem(icons.icon("star"), name, json.dumps(o))
        for name, o in self._presets().items():
            self.preset.addItem(icons.icon("save"), name, json.dumps(o))

    def _apply_preset(self, i):
        data = self.preset.itemData(i)
        if data == "__last__":
            self._load(self._last_opts())
        else:
            base = self.opts()
            base.update(json.loads(data))
            self._load(base)
        self._rebuild()

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Salvar predefinição", "Nome da predefinição:")
        if ok and name.strip():
            p = self._presets()
            o = self.opts()
            o.pop("range_text", None)
            p[name.strip()] = o
            cfg.qs.setValue("print/presets", json.dumps(p))
            self._fill_presets()
            self.preset.setCurrentIndex(self.preset.findText(name.strip()))

    def _del_preset(self):
        name = self.preset.currentText()
        p = self._presets()
        if name in p and QMessageBox.question(self, "Predefinição", f"Excluir “{name}”?") == QMessageBox.Yes:
            del p[name]
            cfg.qs.setValue("print/presets", json.dumps(p))
            self._fill_presets()

    # ---------------------------------------------------------------- montagem e prévia
    def _compute(self):
        o = self.opts()
        items = page_list(self.sources, o)
        orientation = decide_orientation(self.sources, items, o)
        paper, paint = self._page_layout(orientation)
        m = o["extra_margin"] * MM
        area = paint.adjusted(m, m, -m, -m)
        sheets = impose(self.sources, o, area.width(), area.height())
        return o, orientation, paper, area, sheets

    def _rebuild(self):
        try:
            o, orientation, paper, area, sheets = self._compute()
        except Exception as e:
            self.summary.setText(f"Não foi possível montar a impressão: {e}")
            return
        self.sheets, self._geom = sheets, (o, orientation, paper, area)
        self.sheet_idx = min(self.sheet_idx, max(len(sheets) - 1, 0))
        n_pages = len(page_list(self.sources, o))
        sides = len(sheets)
        paper_sheets = math.ceil(sides / 2) if o["duplex"] != "none" or o["mode"] == "booklet" and o["booklet_subset"] == "both" else sides
        mm = f"{paper.width() / MM:.0f} × {paper.height() / MM:.0f} mm"
        self.summary.setText(f"{n_pages} página(s) do documento  •  {sides} lado(s) impresso(s)  •  "
                             f"{paper_sheets * o['copies']} folha(s) de papel  •  {self.paper.currentText().split(' (')[0]} "
                             f"{mm}, {'paisagem' if orientation == 'landscape' else 'retrato'}")
        self._render_preview()

    def _go(self, step):
        if self.sheets:
            self.sheet_idx = max(0, min(len(self.sheets) - 1, self.sheet_idx + step))
            self._render_preview()

    def _render_preview(self):
        o, orientation, paper, area = self._geom
        total = len(self.sheets)
        self.sheet_lbl.setText(f"Folha {self.sheet_idx + 1} de {total}" if total else "Nada a imprimir")
        self.prev_btn.setEnabled(self.sheet_idx > 0)
        self.next_btn.setEnabled(self.sheet_idx < total - 1)
        W = max(self.preview.width() - 30, 200)
        H = max(self.preview.height() - 30, 200)
        k = min(W / paper.width(), H / paper.height())
        img = QImage(int(paper.width() * k) + 8, int(paper.height() * k) + 8, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(QRectF(4, 6, paper.width() * k, paper.height() * k), QColor(0, 0, 0, 50))
        p.fillRect(QRectF(1, 1, paper.width() * k, paper.height() * k), QColor("white"))
        p.setPen(QPen(QColor(150, 180, 230), 1, Qt.DashLine))
        p.drawRect(QRectF(1 + area.x() * k, 1 + area.y() * k, area.width() * k, area.height() * k))
        if self.sheets:
            sh = self.sheets[self.sheet_idx]
            draw_sheet(p, sh, self.sources, o, k, (1 + area.x() * k, 1 + area.y() * k), area.width(), area.height(),
                       preview=True, sheet_no=self.sheet_idx + 1, total=total)
        p.end()
        self.preview.setPixmap(QPixmap.fromImage(img))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_geom", None):
            self._timer.start()

    # ---------------------------------------------------------------- impressão
    def _job_sequence(self, o, sheets):
        """Ordem final das folhas, com cópias e agrupamento (respeitando frente e verso)."""
        duplex = o["duplex"] in ("long", "short") or (o["mode"] == "booklet" and o["booklet_subset"] == "both"
                                                     and o["duplex"] != "none")
        seq = list(sheets)
        copies = o["copies"]
        if duplex and len(seq) % 2 and copies > 1:
            blank = Sheet()
            blank.blank = True
            seq.append(blank)
        unit = 2 if duplex else 1
        units = [seq[i:i + unit] for i in range(0, len(seq), unit)]
        if copies <= 1:
            return seq
        if o["collate"]:
            return [s for _ in range(copies) for s in seq]
        return [s for u in units for _ in range(copies) for s in u]

    def _remember(self):
        o = self.opts()
        cfg.qs.setValue("print/last", json.dumps(o))

    def _run(self, to_pdf=False):
        if not self.sheets:
            QMessageBox.information(self, "Imprimir", "Nenhuma página selecionada para imprimir.")
            return
        o, orientation, paper, area = self._geom
        to_pdf = to_pdf or o["printer"] == PDF_PRINTER
        self._remember()
        try:
            if to_pdf:
                self._save_pdf(o, orientation, paper, area)
            else:
                self._print(o, orientation, area)
        except Exception as e:
            from . import errors
            errors.report(self, f"A impressão falhou: {e}", e, "Imprimir")

    def _progress(self, total, label):
        dlg = QProgressDialog(label, "Cancelar", 0, total, self)
        dlg.setWindowTitle("Imprimir")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        return dlg

    def _paint_all(self, painter, device_new_page, seq, o, k, origin, area, prog, offset=0, total=None):
        total = total or len(seq)
        for n, sh in enumerate(seq):
            if prog.wasCanceled():
                return False
            if n > 0:
                device_new_page()
            if not sh.blank:
                idx = self.sheets.index(sh) if sh in self.sheets else n
                draw_sheet(painter, sh, self.sources, o, k, origin, area.width(), area.height(),
                           sheet_no=idx + 1, total=len(self.sheets))
            prog.setValue(offset + n + 1)
            QApplication.processEvents()
        return True

    def _print(self, o, orientation, area):
        info = self._info()
        pr = self._driver_printer or QPrinter(info, QPrinter.HighResolution)
        if pr.outputFormat() == QPrinter.NativeFormat and pr.printerName() != info.printerName():
            pr.setPrinterName(info.printerName())
        pr.setPageSize(QPageSize(QPageSize.PageSizeId(o["paper"])))
        pr.setPageOrientation(QPageLayout.Landscape if orientation == "landscape" else QPageLayout.Portrait)
        pr.setColorMode(QPrinter.GrayScale if o["gray"] else QPrinter.Color)
        dup = {"long": QPrinter.DuplexLongSide, "short": QPrinter.DuplexShortSide}.get(o["duplex"], QPrinter.DuplexNone)
        if o["mode"] == "booklet" and o["duplex"] in ("long", "short"):
            dup = QPrinter.DuplexShortSide
        pr.setDuplex(dup)
        pr.setCopyCount(1)
        pr.setFullPage(False)
        names = ", ".join(s.name for s in self.sources)
        pr.setDocName(names[:120])
        pr.setResolution(o["quality"])
        res = pr.resolution()
        k = res / 72
        # origem: a área imprimível (painter começa nela) + margem extra
        paint = pr.pageLayout().paintRectPoints()
        origin = ((area.x() - paint.x()) * k, (area.y() - paint.y()) * k)
        seq = self._job_sequence(o, self.sheets)
        if o["duplex"] == "manual":
            fronts = [s for i, s in enumerate(seq) if i % 2 == 0]
            backs = [s for i, s in enumerate(seq) if i % 2 == 1]
            if len(backs) < len(fronts):
                b = Sheet()
                b.blank = True
                backs.append(b)
            passes = [("frentes", fronts), ("versos", backs)]
        else:
            passes = [("", seq)]
        total = sum(len(p[1]) for p in passes)
        prog = self._progress(total, "Enviando para a impressora…")
        done = 0
        for label, part in passes:
            if label == "versos":
                prog.hide()
                r = QMessageBox.question(self, "Frente e verso manual",
                                         "As frentes foram enviadas para a impressora.\n\nQuando terminar, pegue as folhas "
                                         "impressas, vire-as e recoloque na bandeja (lado em branco para a impressão, "
                                         "mesma ordem) e clique em Sim para imprimir os versos.",
                                         QMessageBox.Yes | QMessageBox.Cancel)
                if r != QMessageBox.Yes:
                    break
                prog.show()
            painter = QPainter()
            if not painter.begin(pr):
                raise RuntimeError("Não foi possível iniciar a impressão nesta impressora.")
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            ok = self._paint_all(painter, pr.newPage, part, o, k, origin, area, prog, done, total)
            if not ok:
                pr.abort()
                painter.end()
                prog.close()
                return
            painter.end()
            done += len(part)
        prog.close()
        self.win.statusBar().showMessage(f"{len(seq)} folha(s) enviada(s) para {info.printerName()}.", 8000)
        self.accept()

    def _save_pdf(self, o, orientation, paper, area):
        base = os.path.splitext(self.sources[0].name)[0] + "_impressao.pdf"
        start = os.path.join(cfg.qs.value("last_dir", os.path.expanduser("~")) or os.path.expanduser("~"), base)
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar como PDF", start, "PDF (*.pdf)")
        if not fn:
            return
        if not fn.lower().endswith(".pdf"):
            fn += ".pdf"
        w = QPdfWriter(fn)
        w.setResolution(o["quality"])
        lay = QPageLayout(QPageSize(QPageSize.PageSizeId(o["paper"])),
                          QPageLayout.Landscape if orientation == "landscape" else QPageLayout.Portrait,
                          QMarginsF(0, 0, 0, 0))
        w.setPageLayout(lay)
        w.setTitle(", ".join(s.name for s in self.sources))
        w.setCreator("Lumen PDF")
        k = w.resolution() / 72
        seq = self._job_sequence(dict(o, copies=1), self.sheets)
        prog = self._progress(len(seq), "Gerando PDF…")
        painter = QPainter(w)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        ok = self._paint_all(painter, w.newPage, seq, o, k, (area.x() * k, area.y() * k), area, prog)
        painter.end()
        prog.close()
        if ok:
            self.win.statusBar().showMessage(f"PDF de impressão salvo em {fn}", 8000)
            if QMessageBox.question(self, "Salvar como PDF", f"Arquivo salvo:\n{fn}\n\nAbrir agora?") == QMessageBox.Yes:
                self.win.open_path(fn)
            self.accept()


def icons_size():
    from PySide6.QtCore import QSize
    return QSize(22, 22)


# ====================================================================== impressão rápida (sem janela)
def quick_print_options():
    """Opções da impressão rápida: padrão ou as últimas usadas no gerenciador (Preferências › Impressão)."""
    o = dict(DEFAULT_OPTS)
    if cfg.get("quick_print_mode") == "last":
        try:
            o.update(json.loads(cfg.qs.value("print/last", "{}") or "{}"))
        except ValueError:
            pass
    o.update(pages="all", range_text="", subset="all", copies=max(1, int(o.get("copies") or 1)))
    if o.get("duplex") == "manual":
        o["duplex"] = "none"
    return o


def find_printer(name=""):
    if name:
        for info in QPrinterInfo.availablePrinters():
            if info.printerName().lower() == name.lower():
                return info
    info = QPrinterInfo.defaultPrinter()
    if info.isNull():
        avail = QPrinterInfo.availablePrinters()
        if avail:
            return avail[0]
        raise RuntimeError("Nenhuma impressora instalada no Windows.")
    return info


def quick_print(sources, printer_name="", opts=None, printer=None):
    """Imprime direto, sem mostrar janela (usado pelo Outlook, pelo botão direito do Windows e pelo /p)."""
    o = opts or quick_print_options()
    test_dir = os.environ.get("LUMEN_PRINT_TO_PDF")  # testes automatizados: "imprime" em arquivo PDF
    if printer is None and test_dir:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        import time as _t
        printer.setOutputFileName(os.path.join(test_dir, f"{os.path.splitext(sources[0].name)[0]}_impresso_{_t.time_ns()}.pdf"))
    if printer is None:
        info = find_printer(printer_name)
        printer = QPrinter(info, QPrinter.HighResolution)
        name = info.printerName()
    else:
        name = printer.printerName() or "PDF"
    if o.get("paper"):
        try:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId(int(o["paper"]))))
        except Exception:
            pass
    items = page_list(sources, o)
    orientation = decide_orientation(sources, items, o)
    printer.setPageOrientation(QPageLayout.Landscape if orientation == "landscape" else QPageLayout.Portrait)
    printer.setColorMode(QPrinter.GrayScale if o["gray"] else QPrinter.Color)
    dup = {"long": QPrinter.DuplexLongSide, "short": QPrinter.DuplexShortSide}.get(o["duplex"], QPrinter.DuplexNone)
    printer.setDuplex(dup)
    printer.setCopyCount(1)
    printer.setFullPage(False)
    printer.setResolution(int(o.get("quality") or 300))
    printer.setDocName(", ".join(s.name for s in sources)[:120])
    paint = printer.pageLayout().paintRectPoints()
    m = o["extra_margin"] * MM
    area = QRectF(paint).adjusted(m, m, -m, -m)
    sheets = impose(sources, o, area.width(), area.height())
    if not sheets:
        return 0, name
    seq = []
    copies = o["copies"]
    seq = [s for _ in range(copies) for s in sheets] if o["collate"] or copies == 1 else \
        [s for s in sheets for _ in range(copies)]
    k = printer.resolution() / 72
    origin = ((area.x() - paint.x()) * k, (area.y() - paint.y()) * k)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(f"Não foi possível imprimir em “{name}”.")
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    for n, sh in enumerate(seq):
        if n:
            printer.newPage()
        draw_sheet(painter, sh, sources, o, k, origin, area.width(), area.height(),
                   sheet_no=sheets.index(sh) + 1, total=len(sheets))
        QApplication.processEvents()
    painter.end()
    return len(seq), name
