"""Área de visualização do documento: rolagem contínua, zoom, seleção de texto, busca e ferramentas de comentário."""
from datetime import datetime

import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, Signal, QUrl
from PySide6.QtGui import (QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QBrush, QCursor,
                           QDesktopServices, QGuiApplication, QKeySequence)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsScene, QGraphicsView, QMenu, QInputDialog,
                               QFileDialog, QMessageBox, QWidget)

from . import ops, theme

GAP = 14
MOVABLE = {pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_SQUARE,
           pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_STAMP, pymupdf.PDF_ANNOT_FILE_ATTACHMENT}
TEXT_MARKUP_MODES = {"highlight", "underline", "strikeout", "squiggly"}
DRAG_RECT_MODES = {"rect", "ellipse", "redact", "freetext", "image", "link", "field_text", "field_check",
                   "field_combo", "crop", "area_highlight", "signature", "certsign"}
STAMPS = [("APROVADO", "#2d9d78"), ("REPROVADO", "#d7373f"), ("CONFIDENCIAL", "#d7373f"),
          ("RASCUNHO", "#1473e6"), ("RECEBIDO", "#2d9d78"), ("PAGO", "#2d9d78"),
          ("CONFERIDO", "#1473e6"), ("CÓPIA", "#6e6e6e"), ("URGENTE", "#e68619")]


class PageItem(QGraphicsItem):
    def __init__(self, view, index):
        super().__init__()
        self.view = view
        self.index = index
        self.w = self.h = 10.0

    def boundingRect(self):
        return QRectF(-6, -6, self.w + 12, self.h + 12)

    def page_rect(self):
        return QRectF(0, 0, self.w, self.h)

    def paint(self, painter, option, widget=None):
        self.view.paint_page(self, painter)


class AutoScrollMarker(QWidget):
    """Marcador da rolagem automática (botão do meio): círculo com setas no ponto de origem."""
    SIZE = 34

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, self.SIZE - 3, self.SIZE - 3)
        p.setPen(QPen(QColor(60, 60, 70, 200), 1.5))
        p.setBrush(QColor(255, 255, 255, 225))
        p.drawEllipse(r)
        c = self.SIZE / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 40, 50))
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tip = QPointF(c + dx * 12, c + dy * 12)
            base = QPointF(c + dx * 6, c + dy * 6)
            ox, oy = -dy * 4, dx * 4
            path = QPainterPath(tip)
            path.lineTo(base.x() + ox, base.y() + oy)
            path.lineTo(base.x() - ox, base.y() - oy)
            path.closeSubpath()
            p.drawPath(path)
        p.drawEllipse(QPointF(c, c), 2, 2)
        p.end()


class PdfView(QGraphicsView):
    pageChanged = Signal(int, int)
    zoomChanged = Signal(float)
    modeChanged = Signal(str)
    status = Signal(str)
    selectionChanged = Signal(bool)
    annotSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Canvas")
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        # rolagem automática com o botão do meio do mouse
        self.middle_autoscroll = True
        self._as_active = False
        self._as_origin = None
        self._as_pos = None
        self._as_carry = [0.0, 0.0]
        self._as_marker = AutoScrollMarker(self.viewport())
        self._as_timer = QTimer(self, interval=16, timeout=self._autoscroll_tick)
        self.doc = None
        self.items = []
        self.zoom = 1.0
        self.zoom_mode = "fit_width"
        self.two_page = False
        self.invert = False
        self.base = (self.logicalDpiX() or 96) / 72.0
        self.cache = {}
        self.queue = []
        self._timer = QTimer(self, singleShot=True, interval=0, timeout=self._render_next)
        self._words = {}
        self._links = {}
        self._pages = {}
        self._sizes = {}
        self.marks = {}  # página -> [(retângulo na exibição, QColor, destaque atual?, "fill"|"caret")]
        self.mode = "select"
        self.color = "#ffd400"
        self.colors = {"highlight": "#ffd400", "underline": "#2d9d78", "strikeout": "#d7373f",
                       "squiggly": "#e68619", "note": "#ffd400", "freetext": "#1473e6", "ink": "#d7373f",
                       "rect": "#d7373f", "ellipse": "#d7373f", "line": "#d7373f", "arrow": "#d7373f",
                       "area_highlight": "#ffd400"}
        self.stroke_width = 2.0
        self.opacity = 1.0
        self.author = "Usuário"
        self.signature_png = None
        self.search_hits = {}
        self.hit_list = []
        self.hit_pos = -1
        self.sel = None          # (page, i0, i1) índices de palavras
        self.sel_rects = {}
        self.sel_annot = None    # (page, xref)
        self._press = None
        self._drag_rect = None
        self._ink = []
        self._annot_drag = None
        self.before_change = lambda page=None: None
        self.after_change = lambda pages=None, structure=False: None
        self.request_tool = lambda name, **kw: None
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(lambda *_: self._schedule_visible())
        self._cur_page = 0
        self.apply_theme()

    # ------------------------------------------------------------ documento e layout
    def apply_theme(self):
        self.setBackgroundBrush(QColor(theme.current["canvas"]))
        self.viewport().update()

    def set_document(self, doc, keep_position=False):
        page, frac = self.position() if keep_position and self.doc else (0, 0.0)
        self.doc = doc
        self.scene_.clear()
        self.items = [PageItem(self, i) for i in range(doc.page_count)]
        for it in self.items:
            self.scene_.addItem(it)
        self.cache.clear()
        self._words.clear()
        self._links.clear()
        self._pages = {}
        self._sizes = {}
        self._sigs = {}
        self._fields = {}
        self.sel = None
        self.sel_rects = {}
        self.sel_annot = None
        self.search_hits = {}
        self.hit_list = []
        self.relayout()
        if keep_position:
            self.goto(min(page, doc.page_count - 1), frac)
        else:
            self.goto(0)

    def scale(self):
        return self.zoom * self.base

    def page_size(self, i):
        sz = self._sizes.get(i)
        if sz is None:
            sz = self._sizes[i] = self._fast_size(i)
        return sz

    def _fast_size(self, i):
        """Tamanho exibido da página lido da estrutura do PDF, sem carregar a página (abre PDFs grandes rápido)."""
        try:
            d = self.doc
            if d.is_pdf:
                r = d.page_cropbox(i)
                xref = d.page_xref(i)
                rot = 0
                for key in ("Rotate", "Parent/Rotate", "Parent/Parent/Rotate"):
                    t, v = d.xref_get_key(xref, key)
                    if t == "int":
                        rot = int(v)
                        break
                w, h = abs(r.width), abs(r.height)
                return (h, w) if rot % 180 else (w, h)
        except Exception:
            pass
        r = self._page(i).rect
        return r.width, r.height

    def relayout(self):
        if not self.doc:
            return
        fit = self.zoom_mode in ("fit_width", "fit_page")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff if fit else Qt.ScrollBarAsNeeded)
        if fit:
            self.zoom = self._fit_zoom(self.zoom_mode)
        s = self.scale()
        sizes = [self.page_size(i) for i in range(len(self.items))]
        if self.two_page:
            rows = [list(range(i, min(i + 2, len(sizes)))) for i in range(0, len(sizes), 2)]
        else:
            rows = [[i] for i in range(len(sizes))]
        row_w = [sum(sizes[i][0] * s for i in r) + GAP * (len(r) - 1) for r in rows]
        total_w = max(row_w) if row_w else 0
        y = GAP
        for r, rw in zip(rows, row_w):
            x = (total_w - rw) / 2 + GAP
            h = max(sizes[i][1] * s for i in r)
            for i in r:
                it = self.items[i]
                it.prepareGeometryChange()
                it.w, it.h = sizes[i][0] * s, sizes[i][1] * s
                it.setPos(x, y)
                x += it.w + GAP
            y += h + GAP
        self.scene_.setSceneRect(0, 0, total_w + 2 * GAP, y)
        hb = self.horizontalScrollBar()
        hb.setValue((hb.minimum() + hb.maximum()) // 2)
        self.zoomChanged.emit(self.zoom)
        self._schedule_visible()
        self.viewport().update()

    def _fit_zoom(self, mode):
        sb = 0 if self.verticalScrollBar().isVisible() else self.verticalScrollBar().sizeHint().width()
        vw = max(100, self.viewport().width() - sb - 3 * GAP)
        vh = max(100, self.viewport().height() - 2 * GAP)
        i = min(self._cur_page, self.doc.page_count - 1) if self.doc.page_count else 0
        if not self.doc.page_count:
            return 1.0
        w, h = self.page_size(i)
        if self.two_page:
            w = w * 2 + GAP / self.base
        zw = vw / (w * self.base)
        if mode == "fit_width":
            return max(0.1, min(zw, 8))
        return max(0.1, min(zw, vh / (h * self.base), 8))

    def set_zoom(self, z, mode="custom"):
        page, frac = self.position()
        self.zoom_mode = mode
        self.zoom = max(0.1, min(z, 16.0))
        self.relayout()
        self.goto(page, frac)

    def zoom_step(self, factor):
        steps = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]
        if factor > 1:
            nxt = next((s for s in steps if s > self.zoom + 1e-3), steps[-1])
        else:
            nxt = next((s for s in reversed(steps) if s < self.zoom - 1e-3), steps[0])
        self.set_zoom(nxt)

    def set_fit(self, mode):
        page, frac = self.position()
        self.zoom_mode = mode
        self.relayout()
        self.goto(page, frac if mode != "fit_page" else 0)

    def set_two_page(self, on):
        page, _ = self.position()
        self.two_page = on
        self.relayout()
        self.goto(page)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc and self.zoom_mode != "custom":
            page, frac = self.position()
            self.relayout()
            self.goto(page, frac)
        self.parent_overlay_reposition()

    def parent_overlay_reposition(self):
        cb = getattr(self, "on_resize", None)
        if cb:
            cb()

    # ------------------------------------------------------------ navegação
    def position(self):
        if not self.items:
            return 0, 0.0
        top = self.mapToScene(0, 0).y()
        for it in self.items:
            if it.y() + it.h + GAP / 2 >= top:
                return it.index, max(0.0, (top - it.y()) / it.h)
        return len(self.items) - 1, 0.0

    def goto(self, index, frac=0.0):
        if not self.items:
            return
        index = max(0, min(index, len(self.items) - 1))
        it = self.items[index]
        y = it.y() + frac * it.h - (GAP if frac == 0 else 0)
        self.verticalScrollBar().setValue(int(y))
        self._on_scroll()

    def current_page(self):
        return self._cur_page

    def next_page(self):
        self.goto(self._cur_page + (2 if self.two_page else 1))

    def prev_page(self):
        self.goto(self._cur_page - (2 if self.two_page else 1))

    def _on_scroll(self, *_):
        if not self.items:
            return
        c = self.mapToScene(self.viewport().rect().center()).y()
        cur = 0
        for it in self.items:
            if it.y() <= c:
                cur = it.index
        if self.position()[0] == 0 and self.verticalScrollBar().value() == 0:
            cur = 0
        if cur != self._cur_page:
            self._cur_page = cur
        self.pageChanged.emit(self._cur_page, len(self.items))
        self._schedule_visible()

    def ensure_rect_visible(self, page, disp_rect):
        s = self.scale()
        it = self.items[page]
        r = QRectF(it.x() + disp_rect.x0 * s, it.y() + disp_rect.y0 * s, disp_rect.width * s, disp_rect.height * s)
        self.ensureVisible(r, 60, 120)

    # ------------------------------------------------------------ renderização
    def visible_pages(self):
        vr = self.mapToScene(self.viewport().rect()).boundingRect()
        return [it.index for it in self.items if it.sceneBoundingRect().intersects(vr)]

    def _schedule_visible(self):
        vis = self.visible_pages()
        s = round(self.scale(), 4)
        need = [i for i in vis if self.cache.get(i, (None,))[0] != s]
        if vis:
            lo, hi = max(0, vis[0] - 1), min(len(self.items) - 1, vis[-1] + 1)
            need += [i for i in (lo, hi) if i not in vis and self.cache.get(i, (None,))[0] != s]
        self.queue = need
        keep = set(range(max(0, (vis[0] if vis else 0) - 4), (vis[-1] if vis else 0) + 5))
        if len(self.cache) > 24:
            for k in [k for k in self.cache if k not in keep]:
                del self.cache[k]
        if self.queue:
            self._timer.start()

    def _render_next(self):
        if not self.queue or not self.doc:
            return
        i = self.queue.pop(0)
        if i >= self.doc.page_count:
            return
        s = round(self.scale(), 4)
        dpr = self.devicePixelRatioF()
        try:
            pix = self._page(i).get_pixmap(matrix=pymupdf.Matrix(s * dpr, s * dpr), alpha=False, annots=True)
            if self.invert:
                pix.invert_irect()
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            qpm = QPixmap.fromImage(img)
            qpm.setDevicePixelRatio(dpr)
            self.cache[i] = (s, qpm)
        except Exception as e:
            self.status.emit(f"Erro ao renderizar página {i + 1}: {e}")
        self.items[i].update()
        if self.queue:
            self._timer.start()

    def refresh(self, pages=None):
        self.__dict__["_sigs"] = {}
        self.__dict__["_fields"] = {}
        if pages is None:
            self.cache.clear()
            self._words.clear()
            self._links.clear()
        else:
            for p in pages:
                self.cache.pop(p, None)
                self._words.pop(p, None)
                self._links.pop(p, None)
        self._schedule_visible()
        self.viewport().update()

    def _draw_page_pixmap(self, p, r, cached):
        """Desenha a página 1:1 com os pixels da tela (sem reamostragem), para o texto ficar nítido.
        Só reamostra enquanto a renderização no zoom atual ainda não ficou pronta."""
        scale_, pm = cached
        t = p.worldTransform()
        dpr = pm.devicePixelRatio() or 1.0
        if abs(scale_ - round(self.scale(), 4)) < 1e-6 and t.isAffine() and abs(t.m11() - 1) < 1e-9 \
                and abs(t.m22() - 1) < 1e-9 and abs(t.m12()) < 1e-9 and abs(t.m21()) < 1e-9:
            o = t.map(r.topLeft())
            p.save()
            p.resetTransform()
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.drawPixmap(QPointF(round(o.x() * dpr) / dpr, round(o.y() * dpr) / dpr), pm)
            p.restore()
        else:
            p.drawPixmap(r, pm, QRectF(0, 0, pm.width(), pm.height()))

    def paint_page(self, item, p):
        r = item.page_rect()
        if getattr(self, "page_shadow", True):
            p.fillRect(r.translated(2, 3), QColor(0, 0, 0, 35))
        p.fillRect(r, QColor("#ffffff") if not self.invert else QColor("#111111"))
        cached = self.cache.get(item.index)
        if cached:
            self._draw_page_pixmap(p, r, cached)
        s = self.scale()

        def qr(rect):
            return QRectF(rect.x0 * s, rect.y0 * s, rect.width * s, rect.height * s)

        for k, hr in enumerate(self.search_hits.get(item.index, [])):
            cur = self.hit_list and self.hit_pos >= 0 and self.hit_list[self.hit_pos] == (item.index, k)
            p.fillRect(qr(hr), QColor(255, 140, 0, 130) if cur else QColor(255, 220, 0, 110))
        if cached and getattr(self, "highlight_fields", True):
            for fr, ftype, signed in self.form_fields(item.index):
                if ftype == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                    if not signed:  # campo de assinatura vazio: indica onde assinar
                        p.setPen(QPen(QColor(theme.current["accent"]), 1.2, Qt.DashLine))
                        p.setBrush(QColor(109, 60, 240, 22))
                        p.drawRect(qr(fr))
                        f = p.font()
                        f.setPixelSize(max(9, min(14, int(fr.height * s * 0.28))))
                        p.setFont(f)
                        p.setPen(QColor(theme.current["accent"]))
                        p.drawText(qr(fr), Qt.AlignCenter, "✍ Clique para assinar")
                    continue
                p.fillRect(qr(fr), QColor(204, 215, 255, 95))
        for mr, col, cur, style in self.marks.get(item.index, []):
            if style == "caret":
                x = mr.x1 * s + 1
                p.setPen(QPen(col, 2.2 if not cur else 3.2))
                p.drawLine(QPointF(x, mr.y0 * s - 2), QPointF(x, mr.y1 * s + 2))
                continue
            p.fillRect(qr(mr).adjusted(-1, -1, 1, 1), col)
            if cur:
                p.setPen(QPen(col.darker(160), 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawRect(qr(mr).adjusted(-2.5, -2.5, 2.5, 2.5))
        for sr in self.sel_rects.get(item.index, []):
            p.fillRect(qr(sr), QColor(20, 115, 230, 70))
        if self.sel_annot and self.sel_annot[0] == item.index:
            ar = self._annot_disp_rect(*self.sel_annot)
            if ar is not None:
                if self._annot_drag and self._annot_drag.get("delta"):
                    d = self._annot_drag["delta"]
                    ar = pymupdf.Rect(ar.x0 + d[0], ar.y0 + d[1], ar.x1 + d[0], ar.y1 + d[1])
                p.setPen(QPen(QColor(theme.current["accent"]), 1.5, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(qr(ar).adjusted(-2, -2, 2, 2))
        if self._drag_rect and self._drag_rect[0] == item.index:
            dr = pymupdf.Rect(self._drag_rect[1], self._drag_rect[2]).normalize()
            col = QColor(self.colors.get(self.mode, theme.current["accent"]))
            p.setPen(QPen(col, 1.5, Qt.DashLine if self.mode not in ("rect", "redact") else Qt.SolidLine))
            fill = QColor(col)
            fill.setAlpha(40 if self.mode != "redact" else 90)
            if self.mode == "redact":
                fill = QColor(0, 0, 0, 120)
            p.setBrush(fill)
            if self.mode == "ellipse":
                p.drawEllipse(qr(dr))
            elif self.mode in ("line", "arrow"):
                p.drawLine(QPointF(self._drag_rect[1].x * s, self._drag_rect[1].y * s),
                           QPointF(self._drag_rect[2].x * s, self._drag_rect[2].y * s))
            else:
                p.drawRect(qr(dr))
        if self._ink and self._ink[0] == item.index and len(self._ink[1]) > 1:
            path = QPainterPath(QPointF(self._ink[1][0].x * s, self._ink[1][0].y * s))
            for pt in self._ink[1][1:]:
                path.lineTo(pt.x * s, pt.y * s)
            p.setPen(QPen(QColor(self.colors["ink"]), self.stroke_width * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

    # ------------------------------------------------------------ geometria
    def hit(self, view_pos):
        sp = self.mapToScene(view_pos)
        s = self.scale()
        for it in self.items:
            if it.sceneBoundingRect().contains(sp):
                pt = pymupdf.Point((sp.x() - it.x()) / s, (sp.y() - it.y()) / s)
                w, h = self.page_size(it.index)
                pt = pymupdf.Point(min(max(pt.x, 0), w), min(max(pt.y, 0), h))
                return it.index, pt
        return None, None

    def words(self, i):
        if i not in self._words:
            page = self._page(i)
            m = page.rotation_matrix
            ws = []
            for w in page.get_text("words", sort=True):
                ws.append((pymupdf.Rect(w[:4]) * m, w[4], w[5], w[6]))
            self._words[i] = ws
        return self._words[i]

    def sig_fields(self, i):
        """Campos de assinatura da página (retângulo em coordenadas de exibição, nome do campo)."""
        cache = self.__dict__.setdefault("_sigs", {})
        if i not in cache:
            page = self._page(i)
            out = []
            try:
                for w in page.widgets(types=[pymupdf.PDF_WIDGET_TYPE_SIGNATURE]) or []:
                    out.append(((w.rect * page.rotation_matrix).normalize(), w.field_name))
            except Exception:
                pass
            cache[i] = out
        return cache[i]

    def form_fields(self, i):
        """Campos de formulário da página para o destaque na tela: (retângulo de exibição, tipo, assinado?)."""
        cache = self.__dict__.setdefault("_fields", {})
        if i not in cache:
            page = self._page(i)
            out = []
            try:
                if self.doc.is_form_pdf:
                    for w in page.widgets() or []:
                        signed = bool(getattr(w, "is_signed", False)) if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE else False
                        out.append(((w.rect * page.rotation_matrix).normalize(), w.field_type, signed))
            except Exception:
                pass
            cache[i] = out
        return cache[i]

    def sig_at(self, i, pt):
        for r, name in self.sig_fields(i):
            if r.contains(pt):
                return name
        return None

    def links(self, i):
        if i not in self._links:
            self._pages.pop(i, None)
            self._links[i] = self._page(i).get_links()
        return self._links[i]

    def nearest_word(self, i, pt, strict=False):
        ws = self.words(i)
        best, bd = None, 1e9
        for k, w in enumerate(ws):
            r = w[0]
            if r.contains(pt):
                return k
            dx = max(r.x0 - pt.x, 0, pt.x - r.x1)
            dy = max(r.y0 - pt.y, 0, pt.y - r.y1)
            d = dx + dy * 3
            if d < bd:
                best, bd = k, d
        if strict and bd > 6:
            return None
        return best

    def _annot_disp_rect(self, page, xref):
        a = self._annot(page, xref)
        if a is None:
            return None
        return a.rect * self._page(page).rotation_matrix

    def _page(self, i):
        pg = self._pages.get(i)
        if pg is None or pg.parent is None:
            pg = self.doc[i]
            self._pages[i] = pg
        return pg

    def _annot(self, page, xref):
        try:
            return self._page(page).load_annot(xref)
        except Exception:
            return None

    def annot_at(self, i, pt):
        page = self._page(i)
        m = page.rotation_matrix
        found, best = None, None
        for a in page.annots() or []:
            if a.type[0] == pymupdf.PDF_ANNOT_POPUP:
                continue
            r = (a.rect * m).normalize()
            if (r + (-3, -3, 3, 3)).contains(pt):
                area = r.width * r.height
                if best is None or area <= best:  # a menor (e mais acima) vence
                    found, best = a.xref, area
        return found

    # ------------------------------------------------------------ seleção de texto
    def set_selection(self, page, i0, i1):
        if i0 is None or i1 is None:
            self.clear_selection()
            return
        a, b = sorted((i0, i1))
        self.sel = (page, a, b)
        ws = self.words(page)[a:b + 1]
        lines = {}
        for r, _, bl, ln in ws:
            key = (bl, ln)
            lines[key] = (lines[key] | r) if key in lines else pymupdf.Rect(r)
        self.sel_rects = {page: list(lines.values())}
        self.selectionChanged.emit(True)
        self.viewport().update()

    def clear_selection(self):
        had = self.sel is not None
        self.sel = None
        self.sel_rects = {}
        if had:
            self.selectionChanged.emit(False)
        self.viewport().update()

    def select_all(self):
        p = self._cur_page
        n = len(self.words(p))
        if n:
            self.set_selection(p, 0, n - 1)

    def selected_text(self):
        if not self.sel:
            return ""
        p, a, b = self.sel
        out, last = [], None
        for r, t, bl, ln in self.words(p)[a:b + 1]:
            if last is not None and (bl, ln) != last:
                out.append("\n")
            elif last is not None:
                out.append(" ")
            out.append(t)
            last = (bl, ln)
        return "".join(out)

    def copy_selection(self):
        txt = self.selected_text()
        if txt:
            QGuiApplication.clipboard().setText(txt)
            self.status.emit("Texto copiado.")

    def markup_selection(self, kind):
        if not self.sel:
            return
        p = self.sel[0]
        page = self._page(p)
        quads = [ (r * page.derotation_matrix).quad for r in self.sel_rects[p]]
        self.before_change(page=p)
        fn = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
              "strikeout": page.add_strikeout_annot, "squiggly": page.add_squiggly_annot}[kind]
        a = fn(quads)
        self._style(a, kind, stroke=True)
        a.set_info(content=self.selected_text(), title=self.author)
        a.update()
        self.clear_selection()
        self.after_change([p])

    def redact_selection(self):
        if not self.sel:
            return
        p = self.sel[0]
        page = self._page(p)
        self.before_change(page=p)
        for r in self.sel_rects[p]:
            page.add_redact_annot(ops.to_unrot(page, r), fill=(0, 0, 0))
        self.clear_selection()
        self.after_change([p])
        self.status.emit("Área marcada para ocultação. Use Ocultar > Aplicar para remover definitivamente.")

    # ------------------------------------------------------------ busca
    def search(self, text):
        self.search_hits = {}
        self.hit_list = []
        self.hit_pos = -1
        if text and self.doc:
            for i in range(self.doc.page_count):
                page = self._page(i)
                rects = [r * page.rotation_matrix for r in page.search_for(text)]
                if rects:
                    self.search_hits[i] = rects
                    self.hit_list += [(i, k) for k in range(len(rects))]
        self.viewport().update()
        if self.hit_list:
            start = next((n for n, (pg, _) in enumerate(self.hit_list) if pg >= self._cur_page), 0)
            self.hit_pos = start - 1
            self.next_hit()
        return len(self.hit_list)

    def next_hit(self, step=1):
        if not self.hit_list:
            return
        self.hit_pos = (self.hit_pos + step) % len(self.hit_list)
        pg, k = self.hit_list[self.hit_pos]
        self.ensure_rect_visible(pg, self.search_hits[pg][k])
        self.status.emit(f"Resultado {self.hit_pos + 1} de {len(self.hit_list)}")
        self.viewport().update()

    # ------------------------------------------------------------ modos
    def set_mode(self, mode):
        self.mode = mode
        self.setDragMode(QGraphicsView.ScrollHandDrag if mode == "hand" else QGraphicsView.NoDrag)
        cursors = {"select": Qt.IBeamCursor, "hand": Qt.OpenHandCursor, "edittext": Qt.IBeamCursor,
                   "note": Qt.PointingHandCursor, "addtext": Qt.IBeamCursor, "stamp": Qt.PointingHandCursor}
        self.viewport().setCursor(cursors.get(mode, Qt.CrossCursor if mode not in TEXT_MARKUP_MODES else Qt.IBeamCursor))
        self.modeChanged.emit(mode)
        hints = {
            "highlight": "Selecione o texto para destacar.", "underline": "Selecione o texto para sublinhar.",
            "strikeout": "Selecione o texto para tachar.", "note": "Clique onde deseja adicionar a nota.",
            "freetext": "Arraste para criar a caixa de texto.", "ink": "Desenhe à mão livre.",
            "edittext": "Clique em um trecho de texto para editar.", "addtext": "Clique onde deseja inserir o texto.",
            "redact": "Arraste sobre a área que deseja ocultar.", "signature": "Clique ou arraste para posicionar a assinatura.",
            "certsign": "Arraste para definir a área da assinatura digital.", "crop": "Arraste para definir a área de corte.",
            "stamp": "Clique onde deseja aplicar o carimbo.", "image": "Arraste para definir a área da imagem.",
            "link": "Arraste para definir a área do link.",
        }
        if mode in hints:
            self.status.emit(hints[mode])

    def _style(self, annot, kind, stroke=False, fill=False):
        col = ops.hex_to_rgb(self.colors.get(kind, self.color))
        if stroke:
            annot.set_colors(stroke=col)
        if fill:
            annot.set_colors(stroke=col, fill=col)
        if kind not in TEXT_MARKUP_MODES and kind not in ("note",):
            try:
                annot.set_border(width=self.stroke_width)
            except Exception:
                pass
        annot.set_opacity(self.opacity if kind != "highlight" else min(self.opacity, 1.0))
        annot.set_info(title=self.author)

    # ------------------------------------------------------------ rolagem automática (botão do meio)
    AS_DEAD = 12  # zona morta em pixels ao redor da origem

    def start_autoscroll(self, pos):
        self._as_active = True
        self._as_origin = QPointF(pos)
        self._as_pos = QPointF(pos)
        self._as_moved = False
        self._as_t0 = __import__("time").monotonic()
        self._as_carry = [0.0, 0.0]
        m = self._as_marker
        m.move(int(pos.x() - m.width() / 2), int(pos.y() - m.height() / 2))
        m.show()
        m.raise_()
        self.viewport().setCursor(Qt.SizeAllCursor)
        self.viewport().grabMouse()
        self._as_timer.start()

    def stop_autoscroll(self):
        if not self._as_active:
            return
        self._as_active = False
        self._as_timer.stop()
        self._as_marker.hide()
        self.viewport().releaseMouse()
        cursors = {"select": Qt.IBeamCursor, "hand": Qt.OpenHandCursor, "edittext": Qt.IBeamCursor,
                   "note": Qt.PointingHandCursor, "addtext": Qt.IBeamCursor, "stamp": Qt.PointingHandCursor}
        self.viewport().setCursor(cursors.get(self.mode, Qt.CrossCursor if self.mode not in TEXT_MARKUP_MODES
                                              else Qt.IBeamCursor))

    def _as_speed(self, d):
        a = abs(d) - self.AS_DEAD
        if a <= 0:
            return 0.0
        v = min((a ** 1.35) / 9.0, 160.0)  # px por quadro (~60 fps)
        return v if d > 0 else -v

    def _autoscroll_tick(self):
        if not self._as_active or self._as_pos is None:
            return
        d = self._as_pos - self._as_origin
        for k, (bar, delta) in enumerate(((self.horizontalScrollBar(), d.x()), (self.verticalScrollBar(), d.y()))):
            self._as_carry[k] += self._as_speed(delta)
            step = int(self._as_carry[k])
            if step:
                self._as_carry[k] -= step
                bar.setValue(bar.value() + step)
        dx, dy = d.x(), d.y()
        if abs(dx) <= self.AS_DEAD and abs(dy) <= self.AS_DEAD:
            cur = Qt.SizeAllCursor
        elif abs(dy) >= abs(dx):
            cur = Qt.SizeVerCursor
        else:
            cur = Qt.SizeHorCursor
        if self.viewport().cursor().shape() != cur:
            self.viewport().setCursor(cur)

    def focusOutEvent(self, e):
        self.stop_autoscroll()
        super().focusOutEvent(e)

    # ------------------------------------------------------------ eventos do mouse
    def wheelEvent(self, e):
        if self._as_active:
            self.stop_autoscroll()
            e.accept()
            return
        zoom_key = not (e.modifiers() & Qt.ControlModifier) if getattr(self, "wheel_zoom", False) else \
            bool(e.modifiers() & Qt.ControlModifier)
        if zoom_key:
            self.zoom_step(1.25 if e.angleDelta().y() > 0 else 0.8)
            e.accept()
            return
        super().wheelEvent(e)

    def mousePressEvent(self, e):
        self.setFocus()
        if self._as_active:  # qualquer clique encerra a rolagem automática
            self.stop_autoscroll()
            e.accept()
            return
        if e.button() == Qt.MiddleButton and self.middle_autoscroll and self.doc:
            self.start_autoscroll(e.position())
            e.accept()
            return
        if e.button() != Qt.LeftButton or self.mode == "hand" or not self.doc:
            super().mousePressEvent(e)
            return
        i, pt = self.hit(e.position().toPoint())
        if i is None:
            self.clear_selection()
            self.sel_annot = None
            self.viewport().update()
            return
        self._press = (i, pt, None)
        m = self.mode
        if m == "select":
            name = self.sig_at(i, pt)
            if name and not (e.modifiers() & Qt.ShiftModifier):
                self.request_tool("signature_info", field=name)
                self._press = None
                return
            # link?
            for ln in self.links(i):
                if ln["from"].contains(pt) and not (e.modifiers() & Qt.ShiftModifier):
                    self._follow_link(ln)
                    self._press = None
                    return
            xref = self.annot_at(i, pt)
            if xref:
                self.clear_selection()
                self.sel_annot = (i, xref)
                a = self._annot(i, xref)
                self.annotSelected.emit(a)
                if a and a.type[0] in MOVABLE:
                    self._annot_drag = {"start": pt, "delta": None}
                self.viewport().update()
                return
            self.sel_annot = None
            self.annotSelected.emit(None)
            k = self.nearest_word(i, pt, strict=True)
            if k is None:
                self.clear_selection()
                self._press = (i, pt, "none")
            else:
                self.set_selection(i, k, k)
                self._press = (i, pt, k)
        elif m in TEXT_MARKUP_MODES:
            k = self.nearest_word(i, pt, strict=True)
            if k is not None:
                self.set_selection(i, k, k)
                self._press = (i, pt, k)
            elif m == "highlight":
                self._drag_rect = [i, pt, pt]
                self._press = (i, pt, "area")
        elif m == "ink":
            self._ink = [i, [pt]]
        elif m in DRAG_RECT_MODES or m in ("line", "arrow"):
            self._drag_rect = [i, pt, pt]
        self.viewport().update()

    def mouseMoveEvent(self, e):
        if self._as_active:
            self._as_pos = QPointF(e.position())
            d = self._as_pos - self._as_origin
            if abs(d.x()) > self.AS_DEAD or abs(d.y()) > self.AS_DEAD:
                self._as_moved = True
            e.accept()
            return
        if not self.doc:
            return super().mouseMoveEvent(e)
        i, pt = self.hit(e.position().toPoint())
        if self.mode == "select" and not self._press and i is not None:
            over_sig = self.sig_at(i, pt)
            self.viewport().setToolTip("Clique para ver a validação desta assinatura" if over_sig else "")
            over_link = over_sig or any(ln["from"].contains(pt) for ln in self.links(i))
            self.viewport().setCursor(Qt.PointingHandCursor if over_link else (
                Qt.SizeAllCursor if self.annot_at(i, pt) else Qt.IBeamCursor))
        if not self._press or self.mode == "hand":
            return super().mouseMoveEvent(e)
        pi = self._press[0]
        if i is None or i != pi:
            # projeta o ponto na página inicial
            sp = self.mapToScene(e.position().toPoint())
            it = self.items[pi]
            s = self.scale()
            w, h = self.page_size(pi)
            pt = pymupdf.Point(min(max((sp.x() - it.x()) / s, 0), w), min(max((sp.y() - it.y()) / s, 0), h))
        if self._annot_drag:
            st = self._annot_drag["start"]
            self._annot_drag["delta"] = (pt.x - st.x, pt.y - st.y)
        elif self._ink:
            self._ink[1].append(pt)
        elif self._drag_rect:
            self._drag_rect[2] = pt
        elif len(self._press) == 3 and isinstance(self._press[2], int):
            k = self.nearest_word(pi, pt)
            self.set_selection(pi, self._press[2], k)
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        if self._as_active:
            if e.button() == Qt.MiddleButton:
                import time
                # segurou e arrastou: para ao soltar; clique rápido: continua até o próximo clique
                if self._as_moved or time.monotonic() - self._as_t0 > 0.45:
                    self.stop_autoscroll()
            e.accept()
            return
        if not self._press or self.mode == "hand":
            self._press = None
            return super().mouseReleaseEvent(e)
        i = self._press[0]
        m = self.mode
        try:
            if self._annot_drag:
                d = self._annot_drag.get("delta")
                if d and (abs(d[0]) > 1 or abs(d[1]) > 1):
                    self._move_annot(d)
            elif self._ink:
                pts = self._ink[1]
                if len(pts) > 1:
                    page = self._page(i)
                    self.before_change(page=i)
                    a = page.add_ink_annot([[tuple(p * page.derotation_matrix) for p in pts]])
                    self._style(a, "ink", stroke=True)
                    a.update()
                    self.after_change([i])
            elif self._drag_rect:
                p0, p1 = self._drag_rect[1], self._drag_rect[2]
                rect = pymupdf.Rect(p0, p1).normalize()
                self._finish_drag(i, m, rect, p0, p1)
            elif m == "select" and self._press[2] == "none":
                pass
            elif m in TEXT_MARKUP_MODES and self.sel:
                self.markup_selection(m)
            elif m == "note":
                self._add_note(i, self._press[1])
            elif m == "stamp":
                self._add_stamp(i, self._press[1])
            elif m == "edittext":
                self.request_tool("edit_span", page=i, point=self._press[1])
            elif m == "addtext":
                self.request_tool("add_text_at", page=i, point=self._press[1])
        finally:
            self._press = None
            self._drag_rect = None
            self._ink = []
            self._annot_drag = None
            self.viewport().update()

    def _finish_drag(self, i, m, rect, p0, p1):
        small = rect.width < 4 and rect.height < 4
        page = self._page(i)
        if m in ("line", "arrow"):
            if small:
                return
            self.before_change(page=i)
            a = page.add_line_annot(p0 * page.derotation_matrix, p1 * page.derotation_matrix)
            if m == "arrow":
                a.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
            self._style(a, m, stroke=True)
            a.update()
            self.after_change([i])
            return
        if m in ("signature", "image", "freetext", "certsign", "field_check") and small:
            w, h = {"signature": (180, 60), "image": (200, 150), "freetext": (200, 40),
                    "certsign": (220, 80), "field_check": (14, 14)}[m]
            rect = pymupdf.Rect(p0.x - w / 2 if m != "freetext" else p0.x, p0.y - h / 2 if m != "freetext" else p0.y,
                                0, 0)
            rect.x1, rect.y1 = rect.x0 + w, rect.y0 + h
        elif small:
            return
        unrot = ops.to_unrot(page, rect)
        if m in ("rect", "ellipse"):
            self.before_change(page=i)
            a = page.add_rect_annot(unrot) if m == "rect" else page.add_circle_annot(unrot)
            self._style(a, m, stroke=True)
            a.update()
            self.after_change([i])
        elif m == "area_highlight" or (m == "highlight"):
            self.before_change(page=i)
            a = page.add_highlight_annot(unrot.quad)
            self._style(a, "highlight", stroke=True)
            a.update()
            self.after_change([i])
        elif m == "redact":
            self.before_change(page=i)
            a = page.add_redact_annot(unrot, fill=(0, 0, 0))
            a.set_info(title=self.author)
            a.update()
            self.after_change([i])
        elif m == "freetext":
            text, ok = QInputDialog.getMultiLineText(self, "Caixa de texto", "Texto:")
            if ok and text:
                self.before_change(page=i)
                col = ops.hex_to_rgb(self.colors["freetext"])
                a = page.add_freetext_annot(unrot, text, fontsize=12, fontname="Helv", text_color=col,
                                            border_color=col, border_width=1, fill_color=(1, 1, 1),
                                            rotate=page.rotation)
                a.set_info(title=self.author)
                a.update()
                self.after_change([i])
        elif m == "signature":
            if not self.signature_png:
                self.request_tool("create_signature")
            if self.signature_png:
                self.before_change(page=i)
                a = page.add_stamp_annot(unrot, stamp=self.signature_png)
                a.set_info(title=self.author, content="Assinatura")
                a.update()
                self.after_change([i])
        elif m in ("image", "link", "crop", "certsign", "field_text", "field_check", "field_combo"):
            self.request_tool("rect_" + m, page=i, rect=rect)

    def _move_annot(self, d):
        p, xref = self.sel_annot
        page = self._page(p)
        a = self._annot(p, xref)
        if not a:
            return
        page = self._page(p)
        r = a.rect * page.rotation_matrix
        r = pymupdf.Rect(r.x0 + d[0], r.y0 + d[1], r.x1 + d[0], r.y1 + d[1])
        self.before_change()
        a = self._annot(p, xref)
        a.set_rect(ops.to_unrot(page, r))
        a.update()
        self.after_change([p])

    def mouseDoubleClickEvent(self, e):
        i, pt = self.hit(e.position().toPoint())
        if i is None:
            return
        if self.mode == "select":
            xref = self.annot_at(i, pt)
            if xref:
                self.sel_annot = (i, xref)
                self.edit_annot_contents()
                return
            k = self.nearest_word(i, pt, strict=True)
            if k is not None:  # seleciona a linha/palavra
                ws = self.words(i)
                bl, ln = ws[k][2], ws[k][3]
                same = [n for n, w in enumerate(ws) if (w[2], w[3]) == (bl, ln)]
                self.set_selection(i, same[0], same[-1])
        super().mouseDoubleClickEvent(e)

    def _follow_link(self, ln):
        kind = ln.get("kind")
        if kind == pymupdf.LINK_URI:
            QDesktopServices.openUrl(QUrl(ln["uri"]))
        elif kind in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED) and ln.get("page", -1) >= 0:
            self.goto(ln["page"])

    # ------------------------------------------------------------ anotações
    def _add_note(self, i, pt):
        text, ok = QInputDialog.getMultiLineText(self, "Nota", f"Comentário ({self.author}):")
        if not ok:
            return
        page = self._page(i)
        self.before_change(page=i)
        a = page.add_text_annot(pt * page.derotation_matrix, text, icon="Comment")
        a.set_colors(stroke=ops.hex_to_rgb(self.colors["note"]))
        a.set_info(title=self.author, content=text)
        a.update()
        self.after_change([i])

    def _add_stamp(self, i, pt):
        menu = QMenu(self)
        for label, col in STAMPS:
            menu.addAction(label).setData((label, col))
        menu.addSeparator()
        menu.addAction("Personalizado…").setData(("__custom__", "#1473e6"))
        act = menu.exec(QCursor.pos())
        if not act:
            return
        label, col = act.data()
        if label == "__custom__":
            label, ok = QInputDialog.getText(self, "Carimbo", "Texto do carimbo:")
            if not ok or not label:
                return
        page = self._page(i)
        txt = f"{label.upper()}\n{datetime.now():%d/%m/%Y %H:%M} – {self.author}"
        w = max(150, len(label) * 13 + 30)
        rect = pymupdf.Rect(pt.x - w / 2, pt.y - 25, pt.x + w / 2, pt.y + 25)
        c = ops.hex_to_rgb(col)
        self.before_change(page=i)
        a = page.add_freetext_annot(ops.to_unrot(page, rect), txt, fontsize=13, fontname="Helv", text_color=c,
                                    border_color=c, border_width=2.5, fill_color=(1, 1, 1),
                                    align=pymupdf.TEXT_ALIGN_CENTER, rotate=page.rotation, opacity=0.9)
        a.set_info(title=self.author, subject="Carimbo")
        a.update()
        self.after_change([i])

    def delete_selected_annot(self):
        if not self.sel_annot:
            return
        p, xref = self.sel_annot
        a = self._annot(p, xref)
        if a:
            self.before_change()
            self._page(p).delete_annot(self._annot(p, xref))
            self.sel_annot = None
            self.annotSelected.emit(None)
            self.after_change([p])

    def edit_annot_contents(self):
        if not self.sel_annot:
            return
        p, xref = self.sel_annot
        a = self._annot(p, xref)
        if not a:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Comentário", f"{a.type[1]} — conteúdo:", a.info.get("content", ""))
        if ok:
            self.before_change()
            a = self._annot(p, xref)
            a.set_info(content=text)
            a.update()
            self.after_change([p])

    def recolor_selected_annot(self, hexcolor):
        if not self.sel_annot:
            return
        p, xref = self.sel_annot
        a = self._annot(p, xref)
        if not a:
            return
        self.before_change()
        a = self._annot(p, xref)
        c = ops.hex_to_rgb(hexcolor)
        if a.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT:
            a.update(text_color=c, border_color=c)
        else:
            a.set_colors(stroke=c)
            a.update()
        self.after_change([p])

    # ------------------------------------------------------------ teclado e menu de contexto
    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Copy):
            self.copy_selection()
        elif e.matches(QKeySequence.SelectAll):
            self.select_all()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.sel_annot:
            self.delete_selected_annot()
        elif e.key() == Qt.Key_Escape and self._as_active:
            self.stop_autoscroll()
        elif e.key() == Qt.Key_Escape:
            self.clear_selection()
            self.sel_annot = None
            self.set_mode("select")
        elif e.key() in (Qt.Key_Right,) and self.zoom_mode == "fit_page":
            self.next_page()
        elif e.key() in (Qt.Key_Left,) and self.zoom_mode == "fit_page":
            self.prev_page()
        elif e.key() == Qt.Key_Home and e.modifiers() & Qt.ControlModifier:
            self.goto(0)
        elif e.key() == Qt.Key_End and e.modifiers() & Qt.ControlModifier:
            self.goto(len(self.items) - 1)
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        if not self.doc:
            return
        i, pt = self.hit(e.pos())
        menu = QMenu(self)
        if i is not None and self.annot_at(i, pt):
            self.sel_annot = (i, self.annot_at(i, pt))
            self.viewport().update()
            menu.addAction("Editar comentário…", self.edit_annot_contents)
            cm = menu.addMenu("Cor")
            for name, col in [("Amarelo", "#ffd400"), ("Verde", "#2d9d78"), ("Azul", "#1473e6"),
                              ("Vermelho", "#d7373f"), ("Laranja", "#e68619"), ("Preto", "#000000")]:
                cm.addAction(name, lambda c=col: self.recolor_selected_annot(c))
            menu.addSeparator()
            menu.addAction("Excluir", self.delete_selected_annot)
        elif self.sel:
            menu.addAction("Copiar", self.copy_selection)
            menu.addSeparator()
            menu.addAction("Destacar texto", lambda: self.markup_selection("highlight"))
            menu.addAction("Sublinhar texto", lambda: self.markup_selection("underline"))
            menu.addAction("Tachar texto", lambda: self.markup_selection("strikeout"))
            menu.addSeparator()
            menu.addAction("Ocultar (tarja)", self.redact_selection)
            menu.addAction("Ler em voz alta", lambda: self.request_tool("speak", text=self.selected_text()))
        else:
            menu.addAction("Selecionar tudo", self.select_all)
            menu.addAction("Adicionar nota aqui", lambda: i is not None and self._add_note(i, pt))
            menu.addSeparator()
            menu.addAction("Girar página ↻", lambda: self.request_tool("rotate_current", angle=90))
            menu.addAction("Ajustar largura", lambda: self.set_fit("fit_width"))
            menu.addAction("Ajustar página", lambda: self.set_fit("fit_page"))
            menu.addSeparator()
            menu.addAction("Imprimir…", lambda: self.request_tool("print"))
            menu.addAction("Propriedades do documento…", lambda: self.request_tool("properties"))
        menu.exec(e.globalPos())
