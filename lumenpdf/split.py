"""Divisão de tela: um segundo painel ao lado (ou abaixo) do documento, mostrando outra parte do mesmo
documento ou outro PDF aberto, com rolagem sincronizada opcional."""
import os

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QToolButton, QFileDialog,
                               QMessageBox)

from . import icons
from .viewer import PdfView

SAME = "__same__"
OPEN = "__open__"


class _SourceCombo(QComboBox):
    aboutToPopup = Signal()

    def showPopup(self):
        self.aboutToPopup.emit()
        super().showPopup()


class SplitPane(QWidget):
    closed = Signal()

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.own_doc = None
        self._syncing = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.source = _SourceCombo()
        self.source.setMinimumWidth(160)
        self.source.aboutToPopup.connect(self._fill_sources)
        self.source.activated.connect(self._source_chosen)
        bar.addWidget(self.source, 1)
        self.sync = QCheckBox("Sincronizar rolagem")
        self.sync.setToolTip("Rola os dois painéis juntos")
        bar.addWidget(self.sync)
        self.orient = QToolButton()
        self.orient.setText("⇅")
        self.orient.setToolTip("Alternar entre lado a lado e um acima do outro")
        self.orient.clicked.connect(self._toggle_orientation)
        bar.addWidget(self.orient)
        close = QToolButton()
        icons.bind(close, "close")
        close.setToolTip("Fechar divisão (Ctrl+\\)")
        close.clicked.connect(self.closed.emit)
        bar.addWidget(close)
        lay.addLayout(bar)
        self.view = PdfView()
        lay.addWidget(self.view, 1)
        self.view.verticalScrollBar().valueChanged.connect(lambda _: self._sync_from(self.view, self.tab.view))
        self.tab.view.verticalScrollBar().valueChanged.connect(lambda _: self._sync_from(self.tab.view, self.view))
        self._fill_sources()
        self.show_same()

    # ------------------------------------------------------------ origem do painel
    def _other_tabs(self):
        win = self.tab.window()
        return [t for t in getattr(win, "tab_widgets", [])[1:] if t is not self.tab]

    def _fill_sources(self):
        cur = self.source.currentData()
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItem("Este documento (outra parte)", SAME)
        for t in self._other_tabs():
            self.source.addItem(t.title().lstrip("● "), t)
        self.source.addItem("Abrir outro arquivo…", OPEN)
        idx = self.source.findData(cur) if cur is not None else 0
        self.source.setCurrentIndex(max(idx, 0) if cur != OPEN else 0)
        self.source.blockSignals(False)

    def _source_chosen(self, i):
        data = self.source.itemData(i)
        if data == SAME:
            self.show_same()
        elif data == OPEN:
            fn, _ = QFileDialog.getOpenFileName(self, "Abrir no painel dividido",
                                                os.path.dirname(self.tab.path or os.path.expanduser("~")), "PDF (*.pdf)")
            if fn:
                try:
                    self.show_doc(pymupdf.open(fn), os.path.basename(fn))
                except Exception as e:
                    QMessageBox.warning(self, "Dividir tela", f"Não foi possível abrir o arquivo:\n{e}")
                    self.source.setCurrentIndex(0)
                    self.show_same()
            else:
                self.source.setCurrentIndex(0 if self.own_doc is None else self.source.count() - 1)
        else:
            # cópia somente leitura do outro documento aberto (inclui alterações não salvas)
            self.show_doc(pymupdf.open("pdf", data.doc.tobytes()), data.title().lstrip("● "))

    def _release(self):
        if self.own_doc is not None:
            try:
                self.own_doc.close()
            except Exception:
                pass
            self.own_doc = None

    def show_same(self):
        """Mesmo documento: as edições feitas neste painel entram no desfazer e aparecem nos dois lados."""
        self._release()
        v = self.view
        v.before_change = self.tab.checkpoint
        v.after_change = self.tab.changed
        v.request_tool = self.tab.view.request_tool if hasattr(self.tab.view, "request_tool") else (lambda *a, **k: None)
        self._copy_view_settings()
        page = self.tab.view.current_page()
        v.set_document(self.tab.doc)
        v.set_mode("select")
        v.goto(min(page + 1, self.tab.doc.page_count - 1))
        self.sync.setChecked(False)

    def show_doc(self, doc, name):
        self._release()
        self.own_doc = doc
        v = self.view
        v.before_change = lambda: None
        v.after_change = lambda *a, **k: None
        v.request_tool = lambda *a, **k: None
        self._copy_view_settings()
        v.set_document(doc)
        v.set_mode("select")
        self.source.blockSignals(True)
        if self.source.itemData(self.source.currentIndex()) == OPEN:
            self.source.insertItem(self.source.count() - 1, name, None)
            self.source.setCurrentIndex(self.source.count() - 2)
        self.source.blockSignals(False)
        self.sync.setChecked(True)

    def _copy_view_settings(self):
        src, v = self.tab.view, self.view
        for k in ("author", "wheel_zoom", "middle_autoscroll", "page_shadow", "invert", "zoom_mode", "zoom"):
            if hasattr(src, k):
                setattr(v, k, getattr(src, k))
        v.colors = dict(src.colors)

    def is_same(self):
        return self.own_doc is None

    # ------------------------------------------------------------ sincronização e layout
    def _sync_from(self, a, b):
        if self._syncing or not self.sync.isChecked() or not b.items or not self.isVisible():
            return
        self._syncing = True
        try:
            page, frac = a.position()
            b.goto(min(page, len(b.items) - 1), frac)
        finally:
            self._syncing = False

    def _toggle_orientation(self):
        sp = self.parent()
        if sp is not None and hasattr(sp, "setOrientation"):
            sp.setOrientation(Qt.Vertical if sp.orientation() == Qt.Horizontal else Qt.Horizontal)
            n = sp.width() if sp.orientation() == Qt.Horizontal else sp.height()
            sp.setSizes([n // 2, n // 2])

    def document_changed(self, structure=False, pages=None):
        """Chamado pela aba quando o documento muda (só importa quando o painel mostra o mesmo documento)."""
        if not self.is_same():
            return
        if structure or self.view.doc is not self.tab.doc:
            self.view.set_document(self.tab.doc, keep_position=True)
        else:
            self.view._pages.clear()
            self.view._sizes.clear()
            self.view.refresh(pages)

    def cleanup(self):
        self._release()
