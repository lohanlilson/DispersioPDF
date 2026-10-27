"""Painéis laterais, barra de ferramentas rápidas, painel 'Todas as ferramentas' e organizador de páginas."""
import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QPainter, QAction
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QLineEdit, QPushButton, QMenu,
                               QAbstractItemView, QScrollArea, QFrame, QButtonGroup, QComboBox, QDialog,
                               QInputDialog, QColorDialog, QSizePolicy, QFileDialog, QMessageBox, QSlider)

from . import icons, theme, ops


def tool_button(name, tip, checkable=False, text=None, size=20):
    b = QToolButton()
    icons.bind(b, name)
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    return b


def render_thumb(page, width):
    z = (width - 4) / max(page.rect.width, page.rect.height / 1.42)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False, annots=True)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    out = QPixmap(img.width() + 4, img.height() + 4)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.fillRect(2, 3, img.width(), img.height(), QColor(0, 0, 0, 40))
    p.drawImage(1, 1, img)
    p.setPen(QColor(0, 0, 0, 60))
    p.drawRect(0, 0, img.width() + 1, img.height() + 1)
    p.end()
    return out


# ------------------------------------------------------------------ catálogo de ferramentas
CATALOG = [
    ("Comentar", [
        ("note", "note", "Adicionar nota"), ("highlight", "highlight", "Destacar texto"),
        ("underline", "underline", "Sublinhar"), ("strikeout", "strike", "Tachar"),
        ("freetext", "freetext", "Caixa de texto"), ("ink", "ink", "Desenhar à mão livre"),
        ("rect", "rect", "Retângulo"), ("ellipse", "ellipse", "Elipse"), ("arrow", "arrow", "Seta"),
        ("line", "line", "Linha"), ("stamp", "stamp", "Carimbos"),
        ("comments_summary", "comments", "Resumo dos comentários"), ("flatten", "flatten", "Nivelar comentários"),
        ("export_comments", "comments", "Exportar comentários (FDF)"), ("import_comments", "comments", "Importar comentários (FDF)"),
    ]),
    ("Medir", [
        ("measure", "line", "Medir distância"), ("measure_area", "rect", "Medir área"),
        ("measure_scale", "info", "Escala das medidas"),
    ]),
    ("Editar", [
        ("edittext", "edittext", "Editar texto"), ("find_replace", "search", "Localizar e substituir"),
        ("addtext", "addtext", "Adicionar texto"), ("image_edit", "image", "Mover / trocar imagens"),
        ("image", "image", "Adicionar imagem"), ("link", "link", "Adicionar link"),
        ("autolink", "link", "Criar links de sites e e-mails"), ("snapshot", "imagefile", "Capturar área como imagem"),
        ("watermark", "watermark", "Marca d'água"), ("pagenum", "pagenum", "Cabeçalho, rodapé e numeração"),
        ("background", "blank", "Cor de fundo"), ("crop", "crop", "Cortar páginas"),
        ("properties", "info", "Propriedades do documento"),
    ]),
    ("Organizar páginas", [
        ("organize", "organize", "Organizar páginas"), ("rotate", "rotate_cw", "Girar páginas"),
        ("delete_pages", "trash", "Excluir páginas"), ("insert_blank", "insertpage", "Inserir página em branco"),
        ("insert_file", "createpdf", "Inserir de arquivo"), ("extract", "extract", "Extrair páginas"),
        ("split", "split", "Dividir documento"), ("merge", "merge", "Combinar arquivos"),
        ("remove_blank", "trash", "Remover páginas em branco"), ("deskew", "rotate_cw", "Endireitar páginas (de lado, invertidas ou tortas)"),
    ]),
    ("Converter e exportar", [
        ("export_word", "word", "Exportar para Word"), ("export_excel", "excel", "Exportar para Excel"),
        ("export_image", "imagefile", "Exportar como imagem"), ("export_text", "textfile", "Exportar como texto"),
        ("create_pdf", "createpdf", "Criar PDF (imagens / Office)"), ("compress", "compress", "Comprimir PDF"),
        ("ocr", "ocr", "Reconhecer texto (OCR)"), ("pdfa", "createpdf", "Salvar como PDF/A (arquivamento)"),
        ("extract_images", "imagefile", "Extrair imagens"),
    ]),
    ("Proteger", [
        ("protect", "lock", "Proteger com senha"), ("unprotect", "unlock", "Remover senha"),
        ("redact", "redact", "Ocultar área (tarja)"), ("redact_search", "search", "Localizar e ocultar"),
        ("redact_apply", "redact", "Aplicar ocultações"), ("sanitize", "clean", "Remover informações ocultas"),
    ]),
    ("Assinar", [
        ("signature", "sign", "Preencher e assinar"), ("create_signature", "edit", "Criar / alterar assinatura"),
        ("certsign", "certificate", "Assinar com certificado digital"),
        ("validate_sigs", "certificate", "Validar assinaturas"),
    ]),
    ("Formulários", [
        ("detect_fields", "form", "Detectar campos automaticamente"),
        ("form_fill", "form", "Preencher formulário"), ("field_text", "textfield", "Campo de texto"),
        ("field_check", "checkbox", "Caixa de seleção"), ("field_combo", "form", "Lista suspensa"),
    ]),
    ("Mais ferramentas", [
        ("payments", "barcode", "Boletos, Pix e notas fiscais"),
        ("compare", "compare", "Comparar arquivos"), ("read_aloud", "speaker", "Ler em voz alta"),
        ("attach", "attach", "Anexar arquivo"), ("print", "print", "Imprimir"),
        ("print_batch", "print", "Imprimir vários arquivos"),
    ]),
]

TAB_SECTIONS = {
    "all": None,
    "edit": ["Editar", "Organizar páginas"],
    "convert": ["Converter e exportar"],
    "sign": ["Assinar", "Formulários", "Proteger"],
}

ALL_TOOLS = {t[0]: (t[1], t[2]) for _, items in CATALOG for t in items}


class ToolPanel(QWidget):
    """Painel esquerdo 'Todas as ferramentas'."""
    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("ToolPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(4)
        self.title = QLabel("Todas as ferramentas")
        self.title.setStyleSheet("font-size:15px; font-weight:600; padding:2px 6px;")
        lay.addWidget(self.title)
        self.filter = QLineEdit()
        self.filter.setObjectName("Search")
        self.filter.setPlaceholderText("Localizar ferramenta")
        self.filter.textChanged.connect(self._filter)
        lay.addWidget(self.filter)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("ToolPanel")
        self.inner.setStyleSheet("border:none;")
        self.inner_lay = QVBoxLayout(self.inner)
        self.inner_lay.setContentsMargins(0, 0, 0, 0)
        self.inner_lay.setSpacing(0)
        self.area.setWidget(self.inner)
        lay.addWidget(self.area)
        self.buttons = []
        self.set_tab("all")

    def set_tab(self, tab):
        titles = {"all": "Todas as ferramentas", "edit": "Editar", "convert": "Converter", "sign": "Assinar"}
        self.title.setText(titles[tab])
        while self.inner_lay.count():
            w = self.inner_lay.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.buttons = []
        allowed = TAB_SECTIONS[tab]
        for section, items in CATALOG:
            if allowed and section not in allowed:
                continue
            lb = QLabel(section.upper())
            lb.setObjectName("Section")
            self.inner_lay.addWidget(lb)
            for key, ic, label in items:
                b = QPushButton("  " + label)
                b.setObjectName("ToolItem")
                b.setIcon(icons.chip(ic, icons.SECTION_COLORS.get(section, "#7c3aed"), 24))
                b.setIconSize(QSize(24, 24))
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, k=key: self.triggered.emit(k))
                self.inner_lay.addWidget(b)
                self.buttons.append((b, lb, label))
        self.inner_lay.addStretch()
        self._filter(self.filter.text())

    def _filter(self, txt):
        txt = txt.lower().strip()
        sections_visible = {}
        for b, lb, label in self.buttons:
            vis = not txt or txt in label.lower()
            b.setVisible(vis)
            sections_visible[lb] = sections_visible.get(lb, False) or vis
        for lb, vis in sections_visible.items():
            lb.setVisible(vis)


class QuickRail(QWidget):
    """Barra vertical flutuante de ferramentas rápidas (à esquerda do documento)."""
    modeRequested = Signal(str)
    toolRequested = Signal(str)
    colorChosen = Signal(str)

    MODES = [("select", "select", "Selecionar (V)"), ("hand", "hand", "Mão (H)"), None,
             ("note", "note", "Adicionar nota"), ("highlight", "highlight", "Destacar texto"),
             ("underline", "underline", "Sublinhar"), ("strikeout", "strike", "Tachar"),
             ("freetext", "freetext", "Caixa de texto"), ("ink", "ink", "Desenhar"),
             ("shapes", "rect", "Formas"), ("stamp", "stamp", "Carimbos"), None,
             ("edittext", "edittext", "Editar texto"), ("signature", "sign", "Preencher e assinar")]

    def __init__(self):
        super().__init__()
        self.setObjectName("QuickRail")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.btns = {}
        self.shape_mode = "rect"
        for m in self.MODES:
            if m is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(f"color:{theme.current['border']};")
                lay.addWidget(sep)
                continue
            key, ic, tip = m
            b = tool_button(ic, tip, checkable=True)
            if key == "shapes":
                menu = QMenu(b)
                for k2, ic2, t2 in [("rect", "rect", "Retângulo"), ("ellipse", "ellipse", "Elipse"),
                                    ("arrow", "arrow", "Seta"), ("line", "line", "Linha")]:
                    a = menu.addAction(icons.icon(ic2), t2)
                    a.triggered.connect(lambda _=False, k=k2, i=ic2, bb=b: self._shape(k, i, bb))
                b.clicked.connect(lambda _=False, bb=b: self.modeRequested.emit(self.shape_mode))
                b.setMenu(menu)
                b.setPopupMode(QToolButton.MenuButtonPopup)
            else:
                b.clicked.connect(lambda _=False, k=key: self.modeRequested.emit(k))
            self.group.addButton(b)
            self.btns[key] = b
            lay.addWidget(b)
        self.color_btn = QToolButton()
        self.color_btn.setToolTip("Cor da ferramenta")
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.clicked.connect(self._pick)
        self.set_color("#ffd400")
        lay.addWidget(self.color_btn, alignment=Qt.AlignHCenter)

    def _shape(self, k, ic, b):
        self.shape_mode = k
        icons._registry.append((b, ic))
        b.setIcon(icons.icon(ic))
        self.modeRequested.emit(k)

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Cor da ferramenta")
        if c.isValid():
            self.set_color(c.name())
            self.colorChosen.emit(c.name())

    def set_color(self, c):
        self._color = c
        self.color_btn.setStyleSheet(f"QToolButton{{background:{c}; border:2px solid {theme.current['panel']};"
                                     f"border-radius:15px; outline:1px solid #999;}}")

    def sync(self, mode):
        key = "shapes" if mode in ("rect", "ellipse", "arrow", "line") else mode
        b = self.btns.get(key)
        if b:
            b.setChecked(True)
        else:
            self.group.setExclusive(False)
            for bb in self.group.buttons():
                bb.setChecked(False)
            self.group.setExclusive(True)


class NavPill(QWidget):
    """Controles flutuantes de página e zoom (canto inferior direito)."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setObjectName("NavPill")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(2)
        self.prev = tool_button("up", "Página anterior", size=16)
        self.next = tool_button("down", "Próxima página", size=16)
        self.page = QLineEdit("1")
        self.page.setFixedWidth(42)
        self.page.setAlignment(Qt.AlignCenter)
        self.total = QLabel("/ 1")
        self.zout = tool_button("zoom_out", "Reduzir (Ctrl -)", size=16)
        self.zin = tool_button("zoom_in", "Ampliar (Ctrl +)", size=16)
        self.zoom = QComboBox()
        self.zoom.setEditable(True)
        self.zoom.addItems(["Ajustar largura", "Ajustar página", "50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"])
        self.zoom.setFixedWidth(118)
        self.two = tool_button("twopage", "Duas páginas", checkable=True, size=16)
        for w in (self.prev, self.next, self.page, self.total, self._sep(), self.zout, self.zoom, self.zin,
                  self._sep(), self.two):
            lay.addWidget(w)
        self.prev.clicked.connect(view.prev_page)
        self.next.clicked.connect(view.next_page)
        self.page.returnPressed.connect(lambda: view.goto(int(self.page.text() or 1) - 1) if self.page.text().isdigit() else None)
        self.zout.clicked.connect(lambda: view.zoom_step(0.8))
        self.zin.clicked.connect(lambda: view.zoom_step(1.25))
        self.zoom.activated.connect(self._zoom_choice)
        self.zoom.lineEdit().returnPressed.connect(lambda: self._zoom_text(self.zoom.currentText()))
        self.two.toggled.connect(view.set_two_page)
        view.pageChanged.connect(self.on_page)
        view.zoomChanged.connect(self.on_zoom)
        view.on_resize = self.reposition
        self.adjustSize()

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.VLine)
        s.setStyleSheet(f"color:{theme.current['border']};")
        return s

    def _zoom_choice(self, idx):
        t = self.zoom.itemText(idx)
        if t == "Ajustar largura":
            self.view.set_fit("fit_width")
        elif t == "Ajustar página":
            self.view.set_fit("fit_page")
        else:
            self._zoom_text(t)

    def _zoom_text(self, t):
        try:
            self.view.set_zoom(float(t.replace("%", "").replace(",", ".").strip()) / 100)
        except ValueError:
            pass

    def on_page(self, cur, total):
        if not self.page.hasFocus():
            self.page.setText(str(cur + 1))
        self.total.setText(f"/ {total}")

    def on_zoom(self, z):
        if not self.zoom.lineEdit().hasFocus():
            self.zoom.setEditText(f"{z * 100:.0f}%")

    def reposition(self):
        self.adjustSize()
        vp = self.view.viewport().geometry()
        self.move(vp.right() - self.width() - 18, vp.bottom() - self.height() - 16)
        self.raise_()


# ------------------------------------------------------------------ painéis laterais (direita)
class ThumbList(QListWidget):
    orderChanged = Signal(list)

    def dropEvent(self, e):
        super().dropEvent(e)
        order = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        if order != sorted(order):
            self.orderChanged.emit(order)


class ThumbnailPanel(QWidget):
    def __init__(self, tab, width=130):
        super().__init__()
        self.tab = tab
        self.tw = width
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = ThumbList()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setFlow(QListWidget.TopToBottom if width < 150 else QListWidget.LeftToRight)
        self.list.setWrapping(width >= 150)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Snap)
        self.list.setIconSize(QSize(width, int(width * 1.42)))
        self.list.setSpacing(8)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemClicked.connect(lambda it: self.tab.view.goto(it.data(Qt.UserRole)))
        self.list.orderChanged.connect(self.tab.reorder)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)
        self._pending = []
        self._t = QTimer(self, interval=0, timeout=self._render_some)
        self.list.verticalScrollBar().valueChanged.connect(lambda _: self._pending and self._t.start())

    def selected_pages(self):
        return sorted(it.data(Qt.UserRole) for it in self.list.selectedItems())

    def rebuild(self):
        self.list.clear()
        doc = self.tab.doc
        ph = QPixmap(self.tw, int(self.tw * 1.3))
        ph.fill(QColor("#ffffff"))
        for i in range(doc.page_count):
            it = QListWidgetItem(QIcon(ph), str(i + 1))
            it.setData(Qt.UserRole, i)
            it.setTextAlignment(Qt.AlignHCenter)
            self.list.addItem(it)
        self._pending = list(range(doc.page_count))
        self._t.start()

    def refresh(self, pages):
        for p in pages or []:
            if p not in self._pending:
                self._pending.insert(0, p)
        self._t.start()

    def _visible_rows(self):
        vp = self.list.viewport()
        first = self.list.indexAt(vp.rect().topLeft())
        last = self.list.indexAt(vp.rect().bottomRight())
        a = first.row() if first.isValid() else 0
        b = last.row() if last.isValid() else min(a + 12, self.list.count() - 1)
        return range(max(0, a - 2), min(self.list.count(), b + 3))

    def showEvent(self, e):
        super().showEvent(e)
        if self._pending:
            self._t.start()

    def _render_some(self):
        """Renderiza primeiro as miniaturas visíveis; pausa enquanto o painel está fechado (PDFs grandes)."""
        doc = self.tab.doc
        if not self.isVisible():
            self._t.stop()
            return
        pend = set(self._pending)
        for _ in range(3):
            if not self._pending:
                self._t.stop()
                return
            i = next((r for r in self._visible_rows() if r in pend), None)
            if i is None:
                i = self._pending[0]
            self._pending.remove(i)
            pend.discard(i)
            if i < doc.page_count and i < self.list.count():
                self.list.item(i).setIcon(QIcon(render_thumb(doc[i], self.tw)))

    def highlight(self, page):
        if 0 <= page < self.list.count() and not self.list.hasFocus():
            self.list.setCurrentRow(page)

    def _menu(self, pos):
        pages = self.selected_pages()
        if not pages:
            return
        m = QMenu(self)
        m.addAction(icons.icon("rotate_ccw"), "Girar à esquerda", lambda: self.tab.rotate(pages, -90))
        m.addAction(icons.icon("rotate_cw"), "Girar à direita", lambda: self.tab.rotate(pages, 90))
        m.addSeparator()
        m.addAction(icons.icon("insertpage"), "Inserir página em branco depois", lambda: self.tab.insert_blank(pages[-1] + 1))
        m.addAction(icons.icon("createpdf"), "Inserir de arquivo depois…", lambda: self.tab.insert_file_dialog(pages[-1] + 1))
        m.addAction(icons.icon("extract"), "Extrair páginas…", lambda: self.tab.extract_dialog(pages))
        m.addSeparator()
        m.addAction(icons.icon("trash"), "Excluir páginas", lambda: self.tab.delete_pages(pages))
        m.exec(self.list.mapToGlobal(pos))


class BookmarkPanel(QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        add = tool_button("plus", "Novo marcador na página atual", size=16)
        ren = tool_button("edit", "Renomear", size=16)
        dele = tool_button("trash", "Excluir marcador", size=16)
        add.clicked.connect(self.add)
        ren.clicked.connect(self.rename)
        dele.clicked.connect(self.delete)
        for b in (add, ren, dele):
            bar.addWidget(b)
        bar.addStretch()
        lay.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(lambda it: self.tab.view.goto(max(0, it.data(0, Qt.UserRole)[2] - 1)))
        lay.addWidget(self.tree)

    def rebuild(self):
        self.tree.clear()
        root = self.tree.invisibleRootItem()
        parents = {0: root}
        for entry in self.tab.doc.get_toc(simple=True):
            lvl, title, page = entry[:3]
            parent = parents.get(lvl - 1, root)
            it = QTreeWidgetItem([title])
            it.setData(0, Qt.UserRole, [lvl, title, page])
            parent.addChild(it)
            parents[lvl] = it
            for k in [k for k in parents if k > lvl]:
                del parents[k]
        self.tree.expandToDepth(0)
        if not self.tab.doc.get_toc():
            it = QTreeWidgetItem(["(sem marcadores)"])
            it.setFlags(Qt.NoItemFlags)
            it.setData(0, Qt.UserRole, [1, "", 1])
            self.tree.addTopLevelItem(it)

    def _collect(self):
        toc = []

        def walk(item, lvl):
            for i in range(item.childCount()):
                ch = item.child(i)
                d = ch.data(0, Qt.UserRole)
                if d[1]:
                    toc.append([lvl, ch.text(0), d[2]])
                walk(ch, lvl + 1)
        walk(self.tree.invisibleRootItem(), 1)
        return toc

    def add(self):
        title, ok = QInputDialog.getText(self, "Novo marcador", "Título:", text=f"Página {self.tab.view.current_page() + 1}")
        if ok and title:
            toc = self.tab.doc.get_toc(simple=True)
            toc.append([1, title, self.tab.view.current_page() + 1])
            toc.sort(key=lambda e: e[2]) if all(e[0] == 1 for e in toc) else None
            self.tab.set_toc(toc)

    def rename(self):
        it = self.tree.currentItem()
        if not it or not it.data(0, Qt.UserRole)[1]:
            return
        title, ok = QInputDialog.getText(self, "Renomear", "Título:", text=it.text(0))
        if ok and title:
            it.setText(0, title)
            self.tab.set_toc(self._collect())

    def delete(self):
        it = self.tree.currentItem()
        if not it or not it.data(0, Qt.UserRole)[1]:
            return
        (it.parent() or self.tree.invisibleRootItem()).removeChild(it)
        self.tab.set_toc(self._collect())


ANNOT_ICON = {pymupdf.PDF_ANNOT_TEXT: "note", pymupdf.PDF_ANNOT_HIGHLIGHT: "highlight",
              pymupdf.PDF_ANNOT_UNDERLINE: "underline", pymupdf.PDF_ANNOT_STRIKE_OUT: "strike",
              pymupdf.PDF_ANNOT_SQUIGGLY: "squiggly", pymupdf.PDF_ANNOT_FREE_TEXT: "freetext",
              pymupdf.PDF_ANNOT_INK: "ink", pymupdf.PDF_ANNOT_SQUARE: "rect", pymupdf.PDF_ANNOT_CIRCLE: "ellipse",
              pymupdf.PDF_ANNOT_LINE: "arrow", pymupdf.PDF_ANNOT_STAMP: "stamp", pymupdf.PDF_ANNOT_REDACT: "redact"}
ANNOT_NAME = {pymupdf.PDF_ANNOT_TEXT: "Nota", pymupdf.PDF_ANNOT_HIGHLIGHT: "Destaque",
              pymupdf.PDF_ANNOT_UNDERLINE: "Sublinhado", pymupdf.PDF_ANNOT_STRIKE_OUT: "Tachado",
              pymupdf.PDF_ANNOT_SQUIGGLY: "Ondulado", pymupdf.PDF_ANNOT_FREE_TEXT: "Caixa de texto",
              pymupdf.PDF_ANNOT_INK: "Desenho", pymupdf.PDF_ANNOT_SQUARE: "Retângulo",
              pymupdf.PDF_ANNOT_CIRCLE: "Elipse", pymupdf.PDF_ANNOT_LINE: "Linha", pymupdf.PDF_ANNOT_STAMP: "Carimbo",
              pymupdf.PDF_ANNOT_REDACT: "Ocultação"}


def list_annots(doc):
    out = []
    for p in range(doc.page_count):
        for a in doc[p].annots() or []:
            t = a.type[0]
            if t in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_WIDGET):
                continue
            info = a.info
            out.append(dict(page=p, xref=a.xref, type=t, name=ANNOT_NAME.get(t, a.type[1]),
                            author=info.get("title", ""), content=info.get("content", ""),
                            date=info.get("modDate", "")))
    return out


class CommentsPanel(QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.filter = QLineEdit()
        self.filter.setObjectName("Search")
        self.filter.setPlaceholderText("Pesquisar comentários")
        self.filter.textChanged.connect(self.rebuild)
        lay.addWidget(self.filter)
        self.count = QLabel()
        self.count.setObjectName("Muted")
        lay.addWidget(self.count)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._go)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)

    def rebuild(self):
        # só lê as anotações (que exige abrir cada página) quando o painel estiver visível
        if not self.isVisible():
            self._dirty = True
            return
        self._dirty = False
        self.list.clear()
        f = self.filter.text().lower()
        items = [a for a in list_annots(self.tab.doc) if not f or f in (a["content"] + a["author"] + a["name"]).lower()]
        self.count.setText(f"{len(items)} comentário(s)")
        for a in items:
            txt = f"{a['name']} · pág. {a['page'] + 1}  —  {a['author']}"
            if a["content"]:
                txt += f"\n{a['content'][:160]}"
            it = QListWidgetItem(icons.icon(ANNOT_ICON.get(a["type"], "comments")), txt)
            it.setData(Qt.UserRole, (a["page"], a["xref"]))
            self.list.addItem(it)

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_dirty", True):
            self.rebuild()

    def _go(self, it):
        p, xref = it.data(Qt.UserRole)
        v = self.tab.view
        v.sel_annot = (p, xref)
        r = v._annot_disp_rect(p, xref)
        if r is not None:
            v.ensure_rect_visible(p, r)
        v.viewport().update()

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        self._go(it)
        m = QMenu(self)
        m.addAction("Editar…", self.tab.view.edit_annot_contents)
        m.addAction("Excluir", self.tab.view.delete_selected_annot)
        m.exec(self.list.mapToGlobal(pos))


class AttachmentsPanel(QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        add = tool_button("plus", "Anexar arquivo", size=16)
        sav = tool_button("save", "Salvar anexo", size=16)
        dele = tool_button("trash", "Remover anexo", size=16)
        add.clicked.connect(self.add)
        sav.clicked.connect(self.save)
        dele.clicked.connect(self.delete)
        for b in (add, sav, dele):
            bar.addWidget(b)
        bar.addStretch()
        lay.addLayout(bar)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.save())
        lay.addWidget(self.list)

    def rebuild(self):
        self.list.clear()
        for a in ops.attachments(self.tab.doc):
            it = QListWidgetItem(icons.icon("attach"), f"{a['name']}  ({a.get('size', 0) / 1024:.1f} KB)")
            it.setData(Qt.UserRole, a["name"])
            self.list.addItem(it)

    def add(self):
        fns, _ = QFileDialog.getOpenFileNames(self, "Anexar arquivos")
        if fns:
            self.tab.checkpoint()
            for fn in fns:
                ops.add_attachment(self.tab.doc, fn)
            self.tab.changed()
            self.rebuild()

    def save(self):
        it = self.list.currentItem()
        if not it:
            return
        name = it.data(Qt.UserRole)
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar anexo", name)
        if fn:
            ops.save_attachment(self.tab.doc, name, fn)

    def delete(self):
        it = self.list.currentItem()
        if it:
            self.tab.checkpoint()
            self.tab.doc.embfile_del(it.data(Qt.UserRole))
            self.tab.changed()
            self.rebuild()


class SidePanel(QWidget):
    """Painel da direita com páginas empilhadas + trilho de ícones."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.body = QWidget()
        self.body.setObjectName("SidePanel")
        self.body.setAttribute(Qt.WA_StyledBackground, True)
        self.body.setFixedWidth(220)
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(6, 8, 6, 6)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:600; font-size:14px; padding:2px 4px;")
        bl.addWidget(self.title)
        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        bl.addWidget(self.stack)
        self.thumbs = ThumbnailPanel(tab)
        self.bookmarks = BookmarkPanel(tab)
        self.comments = CommentsPanel(tab)
        self.attachments = AttachmentsPanel(tab)
        self.rail = QWidget()
        self.rail.setObjectName("Rail")
        self.rail.setAttribute(Qt.WA_StyledBackground, True)
        rl = QVBoxLayout(self.rail)
        rl.setContentsMargins(4, 8, 4, 8)
        rl.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(False)
        self.pages = []
        for w, ic, title in [(self.thumbs, "thumbs", "Miniaturas de página"), (self.bookmarks, "bookmark", "Marcadores"),
                             (self.comments, "comments", "Comentários"), (self.attachments, "attach", "Anexos")]:
            self.stack.addWidget(w)
            b = tool_button(ic, title, checkable=True)
            b.clicked.connect(lambda checked, ww=w, t=title, bb=b: self._toggle(ww, t, bb, checked))
            self.group.addButton(b)
            rl.addWidget(b)
            self.pages.append((w, title, b))
        rl.addStretch()
        outer.addWidget(self.body)
        outer.addWidget(self.rail)
        self.body.hide()

    def _toggle(self, w, title, btn, checked):
        for _, _, b in self.pages:
            if b is not btn:
                b.setChecked(False)
        if checked:
            self.stack.setCurrentWidget(w)
            self.title.setText(title)
            self.body.show()
        else:
            self.body.hide()

    def show_panel(self, index):
        w, t, b = self.pages[index]
        b.setChecked(True)
        self._toggle(w, t, b, True)

    def rebuild(self):
        self.thumbs.rebuild()
        self.bookmarks.rebuild()
        self.comments.rebuild()
        self.attachments.rebuild()


class OrganizeDialog(QDialog):
    """Visualização em grade para organizar páginas (arrastar, girar, excluir, inserir, extrair)."""

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.setWindowTitle("Organizar páginas")
        self.resize(1100, 720)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        acts = [("rotate_ccw", "Girar à esquerda", lambda: self._do(lambda p: tab.rotate(p, -90))),
                ("rotate_cw", "Girar à direita", lambda: self._do(lambda p: tab.rotate(p, 90))),
                ("trash", "Excluir", lambda: self._do(tab.delete_pages)),
                ("insertpage", "Página em branco", lambda: self._do(lambda p: tab.insert_blank((p[-1] + 1) if p else tab.doc.page_count), need=False)),
                ("createpdf", "Inserir arquivo", lambda: self._do(lambda p: tab.insert_file_dialog((p[-1] + 1) if p else tab.doc.page_count), need=False)),
                ("extract", "Extrair", lambda: self._do(tab.extract_dialog, refresh=False)),
                ("split", "Dividir", lambda: tab.window().run_tool("split"))]
        for ic, label, fn in acts:
            b = tool_button(ic, label, text=label, size=18)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch()
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(100, 260)
        self.size.setValue(170)
        self.size.setFixedWidth(140)
        self.size.valueChanged.connect(self._resize_icons)
        bar.addWidget(QLabel("Tamanho"))
        bar.addWidget(self.size)
        lay.addLayout(bar)
        self.panel = ThumbnailPanel(tab, width=170)
        self.panel.list.setStyleSheet(f"QListWidget{{background:{theme.current['canvas']}; border-radius:8px;}}")
        self.panel.list.itemClicked.disconnect()
        self.panel.list.itemDoubleClicked.connect(lambda it: (tab.view.goto(it.data(Qt.UserRole)), self.accept()))
        self.panel.list.orderChanged.disconnect()
        self.panel.list.orderChanged.connect(self._reorder)
        lay.addWidget(self.panel)
        tip = QLabel("Arraste as páginas para reordenar • Ctrl/Shift para selecionar várias • duplo clique para abrir")
        tip.setObjectName("Muted")
        lay.addWidget(tip)
        self.panel.rebuild()

    def _resize_icons(self, v):
        self.panel.tw = v
        self.panel.list.setIconSize(QSize(v, int(v * 1.42)))
        self.panel.rebuild()

    def _reorder(self, order):
        self.tab.reorder(order)
        self.panel.rebuild()

    def _do(self, fn, need=True, refresh=True):
        pages = self.panel.selected_pages()
        if need and not pages:
            QMessageBox.information(self, "Organizar", "Selecione uma ou mais páginas.")
            return
        fn(pages)
        if refresh:
            self.panel.rebuild()
