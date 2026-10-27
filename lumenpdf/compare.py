"""Comparação visual de dois documentos (como o "Comparar arquivos" do Acrobat): as duas versões lado a lado,
com o texto removido destacado em vermelho na original e o inserido em verde na revisada, lista de alterações
navegável e rolagem sincronizada. Também usada para mostrar o que mudou depois de uma assinatura."""
import html

import pymupdf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSplitter,
                               QCheckBox, QPushButton, QComboBox, QFileDialog, QApplication)

from . import ops
from .viewer import PdfView

RED = QColor(215, 55, 63, 70)
GREEN = QColor(45, 157, 120, 75)
RED_CUR = QColor(215, 55, 63, 120)
GREEN_CUR = QColor(45, 157, 120, 130)
KIND_LABEL = {"alterado": "Texto alterado", "removido": "Texto removido", "inserido": "Texto inserido"}
KIND_SYMBOL = {"alterado": "✎", "removido": "−", "inserido": "+"}


def report_html(result, name_a, name_b, title="Comparação de arquivos"):
    ch = result["changes"]
    rows = []
    for k, c in enumerate(ch, 1):
        a = f"<span style='background:#ffd7d9;text-decoration:line-through'>{html.escape(c['text_a'])}</span>" if c["text_a"] else ""
        b = f"<span style='background:#c9f2d4'>{html.escape(c['text_b'])}</span>" if c["text_b"] else ""
        rows.append(f"<tr><td>{k}</td><td>{KIND_LABEL[c['kind']]}</td><td>{c['page_a'] + 1}</td>"
                    f"<td>{c['page_b'] + 1}</td><td>{a} {b}</td></tr>")
    return (f"<meta charset='utf-8'><h2>{html.escape(title)}</h2>"
            f"<p><b>{html.escape(name_a)}</b> ({result['pages_a']} pág.) × <b>{html.escape(name_b)}</b> "
            f"({result['pages_b']} pág.) — {len(ch)} alteração(ões) de texto.</p>"
            "<table border=1 cellspacing=0 cellpadding=4 style='border-collapse:collapse'>"
            "<tr><th>#</th><th>Tipo</th><th>Pág. original</th><th>Pág. revisada</th><th>Trecho</th></tr>"
            + "".join(rows) + "</table>")


class CompareWindow(QWidget):
    def __init__(self, parent, doc_a, name_a, doc_b, name_b, title="Comparar arquivos", intro=""):
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"{title} — Dispersio PDF")
        self.resize(1300, 820)
        self.doc_a, self.doc_b, self.name_a, self.name_b, self.title_ = doc_a, doc_b, name_a, name_b, title
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.result = ops.compare_docs(doc_a, doc_b)
        finally:
            QApplication.restoreOverrideCursor()
        self.changes = self.result["changes"]
        self.cur = -1
        self._syncing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        n = len(self.changes)
        summary = (f"<b>{n} alteração(ões) de texto</b>" if n else "<b>Nenhuma diferença de texto encontrada</b>")
        if self.result["pages_a"] != self.result["pages_b"]:
            summary += f" · páginas: {self.result['pages_a']} → {self.result['pages_b']}"
        head = QLabel((f"{intro}<br>" if intro else "") + summary +
                      "  <span style='background:#ffd7d9'>&nbsp;removido&nbsp;</span> "
                      "<span style='background:#c9f2d4'>&nbsp;inserido&nbsp;</span>")
        head.setWordWrap(True)
        top.addWidget(head, 1)
        self.filter = QComboBox()
        self.filter.addItems(["Todas as alterações", "Texto alterado", "Texto inserido", "Texto removido"])
        self.filter.currentIndexChanged.connect(self._fill_list)
        top.addWidget(self.filter)
        self.sync = QCheckBox("Rolagem sincronizada")
        self.sync.setChecked(True)
        top.addWidget(self.sync)
        prev_b, next_b = QPushButton("◀ Anterior"), QPushButton("Próxima ▶")
        prev_b.clicked.connect(lambda: self.step(-1))
        next_b.clicked.connect(lambda: self.step(1))
        top.addWidget(prev_b)
        top.addWidget(next_b)
        rep = QPushButton("Salvar relatório…")
        rep.clicked.connect(self._save_report)
        top.addWidget(rep)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.views = []
        for doc, name, color in ((doc_a, name_a, "#d7373f"), (doc_b, name_b, "#2d9d78")):
            col = QWidget()
            cl = QVBoxLayout(col)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(4)
            lab = QLabel(f"<span style='color:{color}'>●</span> <b>{html.escape(name)}</b> "
                         f"<span style='color:gray'>({doc.page_count} pág.)</span>")
            cl.addWidget(lab)
            v = PdfView()
            v.before_change = lambda page=None, annot=None: None
            v.after_change = lambda *a, **k: None
            v.request_tool = lambda *a, **k: None
            v.zoom_mode = "fit_width"
            v.set_document(doc)
            v.set_mode("hand")
            cl.addWidget(v, 1)
            split.addWidget(col)
            self.views.append(v)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._row)
        split.addWidget(self.list)
        split.setSizes([520, 520, 260])
        lay.addWidget(split, 1)
        self.views[0].verticalScrollBar().valueChanged.connect(lambda _: self._sync_from(0))
        self.views[1].verticalScrollBar().valueChanged.connect(lambda _: self._sync_from(1))
        self._fill_list()
        self._paint_marks()

    # ------------------------------------------------------------ lista e destaques
    def _visible(self):
        f = self.filter.currentIndex()
        want = {0: None, 1: "alterado", 2: "inserido", 3: "removido"}[f]
        return [k for k, c in enumerate(self.changes) if want is None or c["kind"] == want]

    def _fill_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        self.shown = self._visible()
        for k in self.shown:
            c = self.changes[k]
            txt = f"{KIND_SYMBOL[c['kind']]} {KIND_LABEL[c['kind']]} · pág. {c['page_a'] + 1} → {c['page_b'] + 1}"
            if c["text_a"]:
                txt += f"\n− {c['text_a'][:140]}"
            if c["text_b"]:
                txt += f"\n+ {c['text_b'][:140]}"
            it = QListWidgetItem(txt)
            it.setForeground(QColor({"removido": "#b0282f", "inserido": "#1f7a5c"}.get(c["kind"], "#7a4d00")))
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _paint_marks(self):
        ma, mb = {}, {}
        for k, c in enumerate(self.changes):
            cur = k == self.cur
            for pno, rects in c["rects_a"].items():
                ma.setdefault(pno, []).extend((r, RED_CUR if cur else RED, cur, "fill") for r in rects)
            for pno, rects in c["rects_b"].items():
                mb.setdefault(pno, []).extend((r, GREEN_CUR if cur else GREEN, cur, "fill") for r in rects)
            if c["anchor_a"]:  # texto inserido: mostra na original onde ele entrou
                ma.setdefault(c["anchor_a"][0], []).append((c["anchor_a"][1], QColor("#2d9d78"), cur, "caret"))
            if c["anchor_b"]:  # texto removido: mostra na revisada de onde saiu
                mb.setdefault(c["anchor_b"][0], []).append((c["anchor_b"][1], QColor("#d7373f"), cur, "caret"))
        self.views[0].marks, self.views[1].marks = ma, mb
        for v in self.views:
            v.viewport().update()

    # ------------------------------------------------------------ navegação
    def step(self, d):
        if not self.shown:
            return
        row = self.list.currentRow()
        self.list.setCurrentRow(0 if row < 0 else (row + d) % len(self.shown))

    def _row(self, row):
        if row < 0 or row >= len(self.shown):
            return
        self.cur = self.shown[row]
        c = self.changes[self.cur]
        self._paint_marks()
        self._syncing = True
        try:
            for v, rects, anchor, page in ((self.views[0], c["rects_a"], c["anchor_a"], c["page_a"]),
                                           (self.views[1], c["rects_b"], c["anchor_b"], c["page_b"])):
                if rects:
                    pno = min(rects)
                    self._center(v, pno, rects[pno][0])
                elif anchor:
                    self._center(v, anchor[0], anchor[1])
                else:
                    v.goto(page)
        finally:
            QTimer.singleShot(0, lambda: setattr(self, "_syncing", False))

    @staticmethod
    def _center(v, pno, rect):
        if pno >= len(v.items):
            return
        s = v.scale()
        it = v.items[pno]
        v.centerOn(it.x() + (rect.x0 + rect.x1) / 2 * s, it.y() + (rect.y0 + rect.y1) / 2 * s)
        v._on_scroll()

    def _sync_from(self, i):
        if self._syncing or not self.sync.isChecked():
            return
        self._syncing = True
        try:
            page, frac = self.views[i].position()
            other = self.views[1 - i]
            other.goto(min(page, len(other.items) - 1), frac)
        finally:
            self._syncing = False

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_F3, Qt.Key_N):
            self.step(-1 if e.modifiers() & Qt.ShiftModifier else 1)
        elif e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def _save_report(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", "comparacao.html", "HTML (*.html)")
        if fn:
            with open(fn, "w", encoding="utf-8") as f:
                f.write(report_html(self.result, self.name_a, self.name_b, self.title_))


def open_compare(parent, doc_a, name_a, doc_b, name_b, title="Comparar arquivos", intro=""):
    w = CompareWindow(parent, doc_a, name_a, doc_b, name_b, title, intro)
    w.showMaximized()
    return w
