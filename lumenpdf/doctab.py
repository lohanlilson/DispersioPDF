"""Uma aba de documento: documento aberto, histórico de desfazer, visualizador e painéis."""
import os

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QInputDialog

from . import ops
from .viewer import PdfView
from .panels import QuickRail, NavPill, SidePanel

MAX_UNDO = 30


class DocTab(QWidget):
    titleChanged = Signal()
    statusMsg = Signal(str)

    def __init__(self, data, path=None, password=None, settings=None):
        super().__init__()
        self.path = path
        self.password = password
        self.doc = ops.open_bytes(data, password)
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
        cl.addWidget(self.view, 1)
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
        if settings is not None:
            self.view.author = settings.value("author", "Usuário")
            z = settings.value("default_zoom", "Ajustar largura")
            self.view.zoom_mode = {"Ajustar página": "fit_page", "100%": "custom"}.get(z, "fit_width")
        self.view.set_document(self.doc)
        self.side.rebuild()
        self.view.set_mode("select")

    # ------------------------------------------------------------ estado
    def title(self):
        name = os.path.basename(self.path) if self.path else "Sem título.pdf"
        return ("● " if self.modified else "") + name

    def _detect_signatures(self):
        try:
            return any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and w.field_value
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
    def checkpoint(self):
        self.undo_stack.append(self.doc.tobytes())
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def changed(self, pages=None, structure=False):
        self.modified = True
        self.view._pages.clear()
        if structure:
            self.view.set_document(self.doc, keep_position=True)
            self.side.rebuild()
        else:
            self.view.refresh(pages)
            self.side.thumbs.refresh(pages if pages is not None else list(range(self.doc.page_count)))
            self.side.comments.rebuild()
        self.titleChanged.emit()

    def _load_bytes(self, data, structure=True):
        self.doc = ops.open_bytes(data, self.password)
        self.view.set_document(self.doc, keep_position=True)
        self.side.rebuild()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.doc.tobytes())
        self._load_bytes(self.undo_stack.pop())
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
        base = os.path.splitext(self.path or "Documento.pdf")[0] + suffix + ".pdf"
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
        if QMessageBox.question(self, "Excluir páginas", f"Excluir {len(pages)} página(s)?") != QMessageBox.Yes:
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
