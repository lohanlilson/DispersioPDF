"""Uma aba de documento: documento aberto, histórico de desfazer, visualizador e painéis."""
import os

import pymupdf
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QInputDialog,
                               QFrame, QLabel, QPushButton)

from . import ops
from .config import cfg
from .viewer import PdfView
from .panels import QuickRail, NavPill, SidePanel

MAX_UNDO = 30


class _SigThread(QThread):
    done = Signal(list)

    def __init__(self, data):
        super().__init__()
        self.data = data

    def run(self):
        try:
            from . import signing
            self.done.emit(signing.validate(self.data))
        except Exception:
            self.done.emit([])


class SignatureBar(QFrame):
    """Faixa no topo do documento com o resumo das assinaturas (como nos leitores profissionais)."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.setObjectName("SigBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.btn = QPushButton("Painel de assinaturas")
        self.btn.clicked.connect(lambda: self.tab.window().run_tool("validate_sigs"))
        lay.addWidget(self.icon)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.btn)
        self.hide()

    def _style(self, level):
        colors = {"ok": ("#e7f6ee", "#2d9d78"), "warn": ("#fff6dd", "#c58a00"), "bad": ("#fde8e9", "#d7373f"),
                  "info": ("#eef3fc", "#1473e6")}
        bg, fg = colors[level]
        self.setStyleSheet(f"QFrame#SigBar{{background:{bg}; border:1px solid {fg}; border-radius:8px;}}"
                           f"QFrame#SigBar QLabel{{color:#222; background:transparent;}}")
        sym = {"ok": "✔", "warn": "⚠", "bad": "✖", "info": "…"}[level]
        self.icon.setText(f"<span style='font-size:18px; color:{fg}'>{sym}</span>")

    def show_checking(self):
        self._style("info")
        self.text.setText("Validando assinaturas…")
        self.btn.hide()
        self.show()

    def show_results(self, results):
        from . import signing
        if not results:
            self.hide()
            return
        levels = [signing.status_of(r)[0] for r in results]
        n = len(results)
        if "bad" in levels:
            lvl, msg = "bad", "Pelo menos uma assinatura é inválida."
        elif all(l == "ok" for l in levels):
            lvl, msg = "ok", ("Assinado e todas as assinaturas são válidas." if n > 1 else "Assinado e a assinatura é válida.")
        else:
            lvl, msg = "warn", ("Assinado — as assinaturas estão íntegras, mas há pontos de atenção."
                                if n > 1 else "Assinado — assinatura íntegra, mas há pontos de atenção.")
        if self.tab.modified:
            msg += " (alterações não salvas não são consideradas)"
        self._style(lvl)
        self.text.setText(f"<b>{msg}</b> {n} assinatura(s). Clique sobre uma assinatura para ver os detalhes.")
        self.btn.show()
        self.show()


class DocTab(QWidget):
    titleChanged = Signal()
    statusMsg = Signal(str)

    def __init__(self, data, path=None, password=None, settings=None):
        super().__init__()
        self.path = path
        self.password = password
        self.doc = ops.open_bytes(data, password)
        self.original_bytes = data  # arquivo como está em disco (usado para validar assinaturas)
        self.sig_results = []
        self.undo_stack, self.redo_stack = [], []
        self.modified = False
        self.has_signatures = self._detect_signatures()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        center = QWidget()
        cl = QHBoxLayout(center)
        cl.setContentsMargins(10, 10, 0, 0)
        cl.setSpacing(8)
        self.rail = QuickRail()
        rail_col = QVBoxLayout()
        rail_col.addWidget(self.rail)
        rail_col.addStretch()
        cl.addLayout(rail_col)
        self.view = PdfView()
        view_col = QVBoxLayout()
        view_col.setSpacing(6)
        self.sig_bar = SignatureBar(self)
        view_col.addWidget(self.sig_bar)
        from PySide6.QtWidgets import QSplitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.view)
        self.pane = None
        view_col.addWidget(self.splitter, 1)
        cl.addLayout(view_col, 1)
        lay.addWidget(center, 1)
        self.side = SidePanel(self)
        lay.addWidget(self.side)
        self.nav = NavPill(self.view)

        self.view.before_change = self.checkpoint
        self.view.after_change = self.changed
        self.view.status.connect(self.statusMsg)
        self.view.modeChanged.connect(self.rail.sync)
        self.view.pageChanged.connect(lambda c, t: self.side.thumbs.highlight(c))
        self.rail.modeRequested.connect(self.set_mode)
        self.rail.colorChosen.connect(self._color)
        self.apply_settings(initial=True)
        self.view.set_document(self.doc)
        self.side.rebuild()
        self.view.set_mode("select")
        self._restore_position()
        panel = {"thumbs": 0, "bookmarks": 1, "comments": 2}.get(cfg.get("open_side_panel"))
        if panel is not None:
            self.side.show_panel(panel)
        self.validate_signatures()

    # ------------------------------------------------------------ preferências
    def apply_settings(self, initial=False):
        v = self.view
        v.author = cfg.get("author")
        for mode, key in [("highlight", "color_highlight"), ("area_highlight", "color_highlight"),
                          ("underline", "color_underline"), ("strikeout", "color_strikeout"),
                          ("squiggly", "color_strikeout"), ("note", "color_note"), ("freetext", "color_freetext"),
                          ("ink", "color_ink"), ("rect", "color_shapes"), ("ellipse", "color_shapes"),
                          ("line", "color_shapes"), ("arrow", "color_shapes")]:
            v.colors[mode] = cfg.get(key)
        v.stroke_width = cfg.get("stroke_width")
        v.opacity = cfg.get("annot_opacity") / 100
        v.wheel_zoom = cfg.get("wheel_zoom")
        v.middle_autoscroll = cfg.get("middle_autoscroll")
        v.highlight_fields = cfg.get("highlight_fields")
        v.page_shadow = cfg.get("page_shadow")
        self.rail.setVisible(cfg.get("show_quick_rail"))
        self.sig_bar_enabled = cfg.get("show_sig_bar")
        if not self.sig_bar_enabled:
            self.sig_bar.hide()
        elif self.sig_results:
            self.sig_bar.show_results(self.sig_results)
        inv = cfg.get("invert_pages")
        if initial:
            z = cfg.get("default_zoom")
            if z == "Ajustar página":
                v.zoom_mode = "fit_page"
            elif z.endswith("%"):
                v.zoom_mode, v.zoom = "custom", float(z[:-1]) / 100
            else:
                v.zoom_mode = "fit_width"
            v.two_page = cfg.get("two_page")
            self.nav.two.blockSignals(True)
            self.nav.two.setChecked(v.two_page)
            self.nav.two.blockSignals(False)
            v.invert = inv
        else:
            v.apply_theme()
            if v.invert != inv:
                v.invert = inv
                v.refresh()
            v.viewport().update()

    def _restore_position(self):
        if not (self.path and cfg.get("remember_position")):
            return
        st = cfg.doc_state(self.path)
        if not st:
            return
        page, zoom, mode = st
        if mode == "custom":
            self.view.set_zoom(zoom)
        elif mode in ("fit_width", "fit_page"):
            self.view.set_fit(mode)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.view.goto(min(page, self.doc.page_count - 1)))

    def save_position(self):
        if self.path and cfg.get("remember_position") and self.view.items:
            cfg.save_doc_state(self.path, self.view.current_page(), self.view.zoom, self.view.zoom_mode)

    # ------------------------------------------------------------ assinaturas
    def validate_signatures(self):
        """Valida as assinaturas em segundo plano e atualiza a faixa no topo do documento."""
        self.sig_bar.hide()
        if not self.has_signatures:
            return
        self.sig_bar.show_checking()
        data = self.original_bytes
        self._sig_thread = _SigThread(data)
        self._sig_thread.done.connect(self._sig_done)
        self._sig_thread.start()

    def _sig_done(self, results):
        self.sig_results = results or []
        if getattr(self, "sig_bar_enabled", True):
            self.sig_bar.show_results(self.sig_results)
        else:
            self.sig_bar.hide()

    # ------------------------------------------------------------ estado
    def title(self):
        name = os.path.basename(self.path) if self.path else "Sem título.pdf"
        return ("● " if self.modified else "") + name

    def _detect_signatures(self):
        try:
            if self.doc.get_sigflags() > 0:
                return True
            if not self.doc.is_form_pdf:  # sem formulário não há campo de assinatura (evita abrir todas as páginas)
                return False
            return any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE
                       for p in self.doc for w in (p.widgets() or []))
        except Exception:
            return False

    def set_mode(self, mode):
        self.view.set_mode(mode)
        col = self.view.colors.get(mode)
        if col:
            self.rail.set_color(col)

    def _color(self, c):
        m = self.view.mode
        self.view.colors[m if m in self.view.colors else "highlight"] = c
        if self.view.sel_annot:
            self.view.recolor_selected_annot(c)

    # ------------------------------------------------------------ desfazer / alterações
    def checkpoint(self, page=None):
        """Ponto de desfazer. Com page=, a alteração só acrescenta anotações nessa página: guarda apenas quais
        já existiam (instantâneo; a cópia do documento inteiro, lenta em PDFs grandes, só é feita ao desfazer)."""
        entry = None
        if page is not None:
            try:
                entry = ("anotacoes", page, {a.xref for a in self.doc[page].annots()})
            except Exception:
                entry = None
        self.undo_stack.append(entry if entry is not None else self.doc.tobytes())
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def changed(self, pages=None, structure=False):
        self.modified = True
        self.view._pages.clear()
        self.view._sizes.clear()
        if structure:
            self.view.set_document(self.doc, keep_position=True)
            self.side.rebuild()
        else:
            self.view.refresh(pages)
            self.side.thumbs.refresh(pages if pages is not None else list(range(self.doc.page_count)))
            self.side.comments.rebuild()
        if self.pane:
            self.pane.document_changed(structure, pages)
        self.titleChanged.emit()

    def _load_bytes(self, data, structure=True):
        self.doc = ops.open_bytes(data, self.password)
        self.view.set_document(self.doc, keep_position=True)
        self.side.rebuild()
        if self.pane:
            self.pane.document_changed(True)

    # ------------------------------------------------------------ divisão de tela
    def toggle_split(self, on=None):
        on = (self.pane is None) if on is None else on
        if on and self.pane is None:
            from .split import SplitPane
            self.pane = SplitPane(self)
            self.pane.closed.connect(lambda: self.toggle_split(False))
            self.splitter.addWidget(self.pane)
            n = self.splitter.width()
            self.splitter.setSizes([n // 2, n - n // 2])
        elif not on and self.pane is not None:
            self.pane.cleanup()
            self.pane.hide()
            self.pane.setParent(None)
            self.pane.deleteLater()
            self.pane = None
        return self.pane is not None

    def cleanup(self):
        if self.pane:
            self.pane.cleanup()

    def undo(self):
        if not self.undo_stack:
            return
        top = self.undo_stack.pop()
        self.redo_stack.append(self.doc.tobytes())
        if isinstance(top, tuple):
            _, page, before = top
            pg = self.doc[page]
            for xref in [a.xref for a in pg.annots() if a.xref not in before]:
                a = pg.load_annot(xref)
                if a:
                    pg.delete_annot(a)
            self.view.sel_annot = None
            self.changed([page])
        else:
            self._load_bytes(top)
        self.modified = True
        self.titleChanged.emit()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.doc.tobytes())
        self._load_bytes(self.redo_stack.pop())
        self.modified = True
        self.titleChanged.emit()

    def replace_with(self, data, mark_modified=True):
        self.checkpoint()
        self._load_bytes(data)
        self.modified = mark_modified
        self.titleChanged.emit()

    # ------------------------------------------------------------ salvar
    def save(self, path=None):
        path = path or self.path
        if not path:
            return self.save_as()
        if self.has_signatures and self.modified:
            r = QMessageBox.warning(self, "Documento assinado",
                                    "Este documento possui assinatura digital. Salvar as alterações invalidará "
                                    "a assinatura. Deseja continuar?", QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return False
        data = self.doc.tobytes(garbage=3, deflate=True)
        self.original_bytes = data
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        self.path = path
        self.modified = False
        self.titleChanged.emit()
        self.statusMsg.emit(f"Salvo em {path}")
        return True

    def save_as(self):
        start = self.path or os.path.join(os.path.expanduser("~"), "Documento.pdf")
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar como", start, "PDF (*.pdf)")
        if not fn:
            return False
        if not fn.lower().endswith(".pdf"):
            fn += ".pdf"
        return self.save(fn)

    def save_copy_bytes(self, data, suffix):
        if suffix == "_assinado":
            suffix = cfg.get("sign_suffix") or "_assinado"
        base = os.path.splitext(self.path or os.path.join(os.path.expanduser("~"), "Documento.pdf"))[0] + suffix + ".pdf"
        if cfg.get("save_copies") == "same_folder" and self.path:
            fn, n = base, 2
            while os.path.exists(fn):
                fn = base[:-4] + f" ({n}).pdf"
                n += 1
        else:
            fn, _ = QFileDialog.getSaveFileName(self, "Salvar", base, "PDF (*.pdf)")
        if fn:
            with open(fn, "wb") as f:
                f.write(data)
        return fn

    # ------------------------------------------------------------ páginas
    def reorder(self, order):
        self.checkpoint()
        ops.reorder(self.doc, order)
        self.changed(structure=True)

    def rotate(self, pages, angle):
        self.checkpoint()
        ops.rotate_pages(self.doc, pages, angle)
        self.changed(structure=True)

    def delete_pages(self, pages):
        if len(set(pages)) >= self.doc.page_count:
            QMessageBox.warning(self, "Excluir páginas", "Não é possível excluir todas as páginas.")
            return
        if cfg.get("confirm_delete_pages") and \
                QMessageBox.question(self, "Excluir páginas", f"Excluir {len(pages)} página(s)?") != QMessageBox.Yes:
            return
        self.checkpoint()
        ops.delete_pages(self.doc, pages)
        self.changed(structure=True)

    def insert_blank(self, at):
        self.checkpoint()
        ops.insert_blank(self.doc, at)
        self.changed(structure=True)
        self.view.goto(at)

    def insert_file_dialog(self, at):
        fn, _ = QFileDialog.getOpenFileName(self, "Inserir de arquivo", "",
                                            "PDF e imagens (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if fn:
            self.checkpoint()
            ops.insert_file(self.doc, fn, at)
            self.changed(structure=True)
            self.view.goto(at)

    def extract_dialog(self, pages=None):
        if not pages:
            txt, ok = QInputDialog.getText(self, "Extrair páginas", f"Páginas (ex.: 1-3, 7) de 1 a {self.doc.page_count}:")
            if not ok:
                return
            pages = ops.parse_ranges(txt, self.doc.page_count)
        if not pages:
            return
        base = os.path.splitext(self.path or "Documento.pdf")[0] + "_extraido.pdf"
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar páginas extraídas", base, "PDF (*.pdf)")
        if fn:
            ops.extract_pages(self.doc, pages, fn)
            self.statusMsg.emit(f"{len(pages)} página(s) extraída(s) para {fn}")
            if QMessageBox.question(self, "Extrair", "Excluir as páginas extraídas deste documento?") == QMessageBox.Yes:
                if len(pages) < self.doc.page_count:
                    self.checkpoint()
                    ops.delete_pages(self.doc, pages)
                    self.changed(structure=True)

    def set_toc(self, toc):
        self.checkpoint()
        self.doc.set_toc(toc)
        self.modified = True
        self.side.bookmarks.rebuild()
        self.titleChanged.emit()
