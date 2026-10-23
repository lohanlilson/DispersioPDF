"""Janela principal: abas (Início + documentos), barra superior, painel de ferramentas e controlador."""
import os
import sys
import tempfile
from datetime import datetime

import pymupdf
from PySide6.QtCore import Qt, QSize, QSettings, QThread, Signal, QTimer, QStandardPaths
from PySide6.QtGui import QAction, QKeySequence, QPainter, QImage, QColor, QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabBar, QStackedWidget,
                               QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QInputDialog,
                               QProgressDialog, QGridLayout, QListWidget, QListWidgetItem, QButtonGroup,
                               QToolButton, QApplication, QColorDialog, QStatusBar, QFrame, QMenu)

from . import ops, theme, icons, dialogs, signing, system, __version__, resource, AUTHOR, EMAIL, COPYRIGHT
from .doctab import DocTab
from .panels import ToolPanel, OrganizeDialog, tool_button, ALL_TOOLS, list_annots

APP = "Lumen PDF"
MODE_TOOLS = {"note", "highlight", "underline", "strikeout", "freetext", "ink", "rect", "ellipse", "arrow",
              "line", "stamp", "edittext", "addtext", "image", "link", "redact", "crop", "signature",
              "field_text", "field_check", "field_combo", "certsign", "select", "hand"}
NEEDS_DOC_EXCEPT = {"merge", "create_pdf", "compare", "open", "create_signature"}


class Worker(QThread):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancel = False

    def run(self):
        try:
            self.done.emit(self.fn(self))
        except Exception as e:
            self.failed.emit(str(e))


class HomePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("HomePage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 32, 48, 24)
        lay.setSpacing(14)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(resource("assets", "logo.png")).pixmap(44, 44))
        brand.addWidget(logo)
        name = QLabel(f"<span style='font-size:20px;font-weight:700'>{APP}</span>")
        brand.addWidget(name)
        brand.addStretch()
        lay.addLayout(brand)
        self.hello = QLabel()
        self.hello.setObjectName("Title")
        lay.addWidget(self.hello)
        sub = QLabel("Ferramentas recomendadas")
        sub.setObjectName("Muted")
        lay.addWidget(sub)
        grid = QGridLayout()
        self.grid = grid
        self.cards = []
        grid.setSpacing(12)
        cards = [("open", "open", "Abrir arquivo", "Visualize e comente PDFs"),
                 ("edittext", "edit", "Editar PDF", "Edite textos e imagens"),
                 ("merge", "merge", "Combinar arquivos", "Junte vários arquivos em um PDF"),
                 ("export_word", "convert", "Converter PDF", "Para Word, Excel ou imagem"),
                 ("signature", "sign", "Preencher e assinar", "Assine e preencha formulários"),
                 ("certsign", "certificate", "Certificado digital", "Assinatura A1/A3 ICP-Brasil"),
                 ("ocr", "ocr", "Escanear e OCR", "Torne digitalizados pesquisáveis"),
                 ("compress", "compress", "Comprimir PDF", "Reduza o tamanho do arquivo"),
                 ("organize", "organize", "Organizar páginas", "Reordene, gire e exclua"),
                 ("protect", "lock", "Proteger", "Senhas e permissões"),
                 ("redact", "redact", "Ocultar", "Tarje informações sigilosas"),
                 ("compare", "compare", "Comparar arquivos", "Encontre diferenças entre versões")]
        for n, (key, ic, title, desc) in enumerate(cards):
            b = QPushButton(f"  {title}\n  {desc}")
            b.setObjectName("Card")
            icons.bind(b, ic)
            b.setIconSize(QSize(28, 28))
            b.setMinimumHeight(70)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.win.home_tool(k))
            b.setMinimumWidth(170)
            self.cards.append(b)
            grid.addWidget(b, n // 4, n % 4)
        lay.addLayout(grid)
        head = QHBoxLayout()
        rl = QLabel("Recentes")
        rl.setStyleSheet("font-size:16px; font-weight:600; margin-top:12px;")
        head.addWidget(rl)
        head.addStretch()
        clr = QPushButton("Limpar lista")
        clr.clicked.connect(self._clear)
        head.addWidget(clr)
        lay.addLayout(head)
        self.recent = QListWidget()
        self.recent.setIconSize(QSize(22, 22))
        self.recent.itemActivated.connect(lambda it: self.win.open_path(it.data(Qt.UserRole)))
        self.recent.itemClicked.connect(lambda it: self.win.open_path(it.data(Qt.UserRole)))
        lay.addWidget(self.recent, 1)
        foot = QLabel(f"{APP} {__version__}  •  Desenvolvido por {AUTHOR}  •  "
                      f"<a href='mailto:{EMAIL}'>{EMAIL}</a>")
        foot.setObjectName("Muted")
        foot.setWordWrap(True)
        foot.setOpenExternalLinks(True)
        lay.addWidget(foot)
        self.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.reflow(self.width())

    def reflow(self, width):
        cols = max(1, min(4, (width - 96) // 240))
        if getattr(self, "_cols", None) != cols:
            self._cols = cols
            for b in self.cards:
                self.grid.removeWidget(b)
            for n, b in enumerate(self.cards):
                self.grid.addWidget(b, n // cols, n % cols)

    def _clear(self):
        self.win.settings.setValue("recent", [])
        self.refresh()

    def refresh(self):
        self.hello.setText(f"Bem-vindo(a), {self.win.settings.value('author', 'Usuário')}")
        self.recent.clear()
        for p in self.win.recent_files():
            exists = os.path.exists(p)
            when = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%d/%m/%Y %H:%M") if exists else "não encontrado"
            it = QListWidgetItem(icons.icon("textfile"), f"{os.path.basename(p)}\n{os.path.dirname(p)}  ·  {when}")
            it.setData(Qt.UserRole, p)
            if not exists:
                it.setForeground(QColor(theme.current["muted"]))
            self.recent.addItem(it)
        if not self.recent.count():
            it = QListWidgetItem("Nenhum arquivo recente. Abra um PDF ou arraste-o para esta janela.")
            it.setFlags(Qt.NoItemFlags)
            self.recent.addItem(it)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("LumenPDF", "LumenPDF")
        theme.apply(self.settings.value("dark", "false") == "true")
        self.setWindowTitle(APP)
        self.resize(1400, 880)
        self.setMinimumSize(560, 480)  # permite encaixar em meia tela (Windows Snap)
        self.setAcceptDrops(True)
        self.tts = None
        self.pending_tool = None

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.tabbar = QTabBar()
        self.tabbar.setTabsClosable(True)
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDocumentMode(True)
        self.tabbar.addTab(icons.icon("home"), "Início")
        self.tabbar.setTabButton(0, QTabBar.RightSide, None)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.tabbar.tabCloseRequested.connect(self.close_tab)
        self.tabbar.tabMoved.connect(self._tab_moved)
        root.addWidget(self.tabbar)

        self.stack = QStackedWidget()
        self.home = HomePage(self)
        from PySide6.QtWidgets import QScrollArea
        home_scroll = QScrollArea()
        home_scroll.setWidgetResizable(True)
        home_scroll.setFrameShape(QFrame.NoFrame)
        home_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        home_scroll.setWidget(self.home)
        self.home_scroll = home_scroll
        self.stack.addWidget(home_scroll)
        self.doc_area = QWidget()
        da = QVBoxLayout(self.doc_area)
        da.setContentsMargins(0, 0, 0, 0)
        da.setSpacing(0)
        da.addWidget(self._build_topbar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.tools = ToolPanel()
        self.tools.triggered.connect(self.run_tool)
        body.addWidget(self.tools)
        self.docs = QStackedWidget()
        body.addWidget(self.docs, 1)
        da.addLayout(body, 1)
        self.stack.addWidget(self.doc_area)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self._build_menu()
        self.tab_widgets = [None]  # índice 0 = Início
        from .updater import Updater
        self.updater = Updater(self)

    # ------------------------------------------------------------ construção
    def _build_topbar(self):
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 4, 12, 4)
        lay.setSpacing(4)
        menu_btn = tool_button("menu", "Menu")
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        self._menu_btn = menu_btn
        lay.addWidget(menu_btn)
        self._compact_hide, self._narrow_hide = [], []
        self.top_tabs = QButtonGroup(self)
        for key, label in [("all", "Todas as ferramentas"), ("edit", "Editar"), ("convert", "Converter"), ("sign", "Assinar")]:
            b = QToolButton()
            b.setText(label)
            b.setObjectName("TopTab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._top_tab(k))
            self.top_tabs.addButton(b)
            if key != "all":
                self._compact_hide.append(b)
            lay.addWidget(b)
            if key == "all":
                b.setChecked(True)
        lay.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Localizar texto  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(110)
        self.search.setMaximumWidth(320)
        from PySide6.QtWidgets import QSizePolicy
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._search_icon = self.search.addAction(icons.icon("search"), QLineEdit.LeadingPosition)
        self.search.returnPressed.connect(self._search)
        self.search.textChanged.connect(lambda t: self.cur() and not t and self.cur().view.search(""))
        lay.addWidget(self.search)
        self.search_prev = tool_button("up", "Resultado anterior (Shift+F3)", size=16)
        self.search_next = tool_button("down", "Próximo resultado (F3)", size=16)
        self.search_prev.clicked.connect(lambda: self.cur() and self.cur().view.next_hit(-1))
        self.search_next.clicked.connect(lambda: self.cur() and self.cur().view.next_hit(1))
        lay.addWidget(self.search_prev)
        lay.addWidget(self.search_next)
        lay.addStretch()
        for ic, tip, fn in [("undo", "Desfazer (Ctrl+Z)", self.undo), ("redo", "Refazer (Ctrl+Y)", self.redo),
                            ("save", "Salvar (Ctrl+S)", self.save), ("print", "Imprimir (Ctrl+P)", lambda: self.run_tool("print")),
                            ("speaker", "Ler em voz alta", lambda: self.run_tool("read_aloud")),
                            ("readmode", "Modo de leitura (Ctrl+H)", self.toggle_read_mode),
                            ("moon", "Tema escuro", self.toggle_dark)]:
            b = tool_button(ic, tip)
            b.clicked.connect(fn)
            if ic in ("speaker", "readmode", "moon", "redo"):
                self._narrow_hide.append(b)
            lay.addWidget(b)
        return bar

    def _build_menu(self):
        mb = self.menuBar()

        def act(menu, text, fn, shortcut=None, icon_name=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if icon_name:
                a.setIcon(icons.icon(icon_name))
            a.triggered.connect(fn)
            menu.addAction(a)
            return a

        m = mb.addMenu("&Arquivo")
        act(m, "Abrir…", self.open_dialog, "Ctrl+O", "open")
        self.recent_menu = m.addMenu("Abrir recente")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        act(m, "Criar PDF…", lambda: self.run_tool("create_pdf"), None, "createpdf")
        act(m, "Combinar arquivos…", lambda: self.run_tool("merge"), None, "merge")
        m.addSeparator()
        act(m, "Salvar", self.save, "Ctrl+S", "save")
        act(m, "Salvar como…", self.save_as, "Ctrl+Shift+S", "saveas")
        act(m, "Exportar para", lambda: None).setEnabled(False)
        for k in ("export_word", "export_excel", "export_image", "export_text"):
            act(m, "    " + ALL_TOOLS[k][1], lambda _=False, kk=k: self.run_tool(kk), None, ALL_TOOLS[k][0])
        m.addSeparator()
        act(m, "Proteger com senha…", lambda: self.run_tool("protect"), None, "lock")
        act(m, "Propriedades…", lambda: self.run_tool("properties"), "Ctrl+D", "info")
        act(m, "Imprimir…", lambda: self.run_tool("print"), "Ctrl+P", "print")
        m.addSeparator()
        act(m, "Fechar aba", lambda: self.close_tab(self.tabbar.currentIndex()), "Ctrl+W")
        act(m, "Sair", self.close, "Ctrl+Q")
        self._menu_btn.setMenu(m)

        m = mb.addMenu("&Editar")
        act(m, "Desfazer", self.undo, "Ctrl+Z", "undo")
        act(m, "Refazer", self.redo, "Ctrl+Y", "redo")
        m.addSeparator()
        act(m, "Copiar", lambda: self.cur() and self.cur().view.copy_selection(), None, "copy")
        act(m, "Selecionar tudo", lambda: self.cur() and self.cur().view.select_all())
        m.addSeparator()
        act(m, "Localizar…", self.focus_search, "Ctrl+F", "search")
        act(m, "Próximo resultado", lambda: self.cur() and self.cur().view.next_hit(1), "F3")
        act(m, "Resultado anterior", lambda: self.cur() and self.cur().view.next_hit(-1), "Shift+F3")
        m.addSeparator()
        act(m, "Editar texto e imagens", lambda: self.run_tool("edittext"), "Ctrl+E", "edittext")
        act(m, "Preferências…", self.preferences, "Ctrl+K")

        m = mb.addMenu("E&xibir")
        act(m, "Ampliar", lambda: self.cur() and self.cur().view.zoom_step(1.25), "Ctrl++", "zoom_in")
        act(m, "Ampliar ", lambda: self.cur() and self.cur().view.zoom_step(1.25), "Ctrl+=")
        act(m, "Reduzir", lambda: self.cur() and self.cur().view.zoom_step(0.8), "Ctrl+-", "zoom_out")
        act(m, "Tamanho real (100%)", lambda: self.cur() and self.cur().view.set_zoom(1.0), "Ctrl+1")
        act(m, "Ajustar página", lambda: self.cur() and self.cur().view.set_fit("fit_page"), "Ctrl+0", "fit_page")
        act(m, "Ajustar largura", lambda: self.cur() and self.cur().view.set_fit("fit_width"), "Ctrl+2", "fit_width")
        m.addSeparator()
        act(m, "Ir para página…", self.goto_dialog, "Ctrl+Shift+N")
        act(m, "Primeira página", lambda: self.cur() and self.cur().view.goto(0), "Home")
        act(m, "Última página", lambda: self.cur() and self.cur().view.goto(10 ** 6), "End")
        m.addSeparator()
        act(m, "Miniaturas de página", lambda: self.cur() and self.cur().side.show_panel(0), "F4", "thumbs")
        act(m, "Marcadores", lambda: self.cur() and self.cur().side.show_panel(1), None, "bookmark")
        act(m, "Comentários", lambda: self.cur() and self.cur().side.show_panel(2), None, "comments")
        act(m, "Anexos", lambda: self.cur() and self.cur().side.show_panel(3), None, "attach")
        act(m, "Painel de ferramentas", lambda: self.tools.setVisible(not self.tools.isVisible()), "Shift+F4", "tools")
        m.addSeparator()
        act(m, "Modo de leitura", self.toggle_read_mode, "Ctrl+H", "readmode")
        act(m, "Tela cheia", self.toggle_fullscreen, "F11", "fullscreen")
        act(m, "Tema escuro", self.toggle_dark, "Ctrl+Shift+D", "moon")
        act(m, "Inverter cores das páginas", self.toggle_invert)
        act(m, "Girar exibição (página atual) ↻", lambda: self.run_tool("rotate_current"), "Ctrl+Shift++")

        m = mb.addMenu("&Ferramentas")
        from .panels import CATALOG
        for section, items in CATALOG:
            sm = m.addMenu(section)
            for key, ic, label in items:
                act(sm, label, lambda _=False, k=key: self.run_tool(k), None, ic)

        m = mb.addMenu("Aj&uda")
        act(m, "Atalhos de teclado", self.shortcuts_help, "F1")
        if system.IS_WINDOWS:
            act(m, "Definir como leitor de PDF padrão…", lambda: self.check_default_app(force=True))
        act(m, "Verificar atualizações…", lambda: self.updater.check(silent=False))
        auto = QAction("Verificar atualizações automaticamente", self, checkable=True)
        auto.setChecked(self.settings.value("auto_update", "true") != "false")
        auto.toggled.connect(lambda on: self.settings.setValue("auto_update", "true" if on else "false"))
        m.addAction(auto)
        m.addSeparator()
        act(m, "Enviar sugestão ou relatar problema…", lambda: __import__("PySide6.QtGui", fromlist=["QDesktopServices"]).QDesktopServices.openUrl(
            __import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl(f"mailto:{EMAIL}?subject={APP} {__version__}")))
        act(m, f"Sobre o {APP}", self.about)

        for key, sc in [("select", "V"), ("hand", "H"), ("highlight", "Ctrl+Shift+H"), ("note", "Ctrl+6")]:
            a = QAction(self)
            a.setShortcut(QKeySequence(sc))
            a.setShortcutContext(Qt.WindowShortcut)
            a.triggered.connect(lambda _=False, k=key: self.run_tool(k))
            self.addAction(a)

    # ------------------------------------------------------------ abas
    def cur(self):
        i = self.tabbar.currentIndex()
        return self.tab_widgets[i] if 0 <= i < len(self.tab_widgets) else None

    def resizeEvent(self, e):
        """Layout responsivo: permite encaixar a janela em meia tela (Windows Snap)."""
        super().resizeEvent(e)
        w = self.width()
        self.home.reflow(w)
        for b in self._compact_hide:
            b.setVisible(w >= 1000)
        for b in self._narrow_hide:
            b.setVisible(w >= 820)
        auto_hide = w < 1100
        if auto_hide != getattr(self, "_tools_auto_hidden", False):
            self._tools_auto_hidden = auto_hide
            self.tools.setVisible(not auto_hide)

    def _tab_changed(self, i):
        if i <= 0 or i >= len(getattr(self, "tab_widgets", [])):
            self.stack.setCurrentWidget(self.home_scroll)
            self.home.refresh()
            self.setWindowTitle(APP)
            return
        tab = self.tab_widgets[i]
        self.stack.setCurrentWidget(self.doc_area)
        self.docs.setCurrentWidget(tab)
        self.setWindowTitle(f"{tab.title()} — {APP}")
        QTimer.singleShot(0, tab.nav.reposition)

    def _tab_moved(self, a, b):
        if a == 0 or b == 0:  # mantém Início na primeira posição
            self.tabbar.blockSignals(True)
            self.tabbar.moveTab(b, a)
            self.tabbar.blockSignals(False)
            return
        w = self.tab_widgets.pop(a)
        self.tab_widgets.insert(b, w)

    def _retitle(self, tab):
        i = self.tab_widgets.index(tab)
        self.tabbar.setTabText(i, tab.title())
        self.tabbar.setTabToolTip(i, tab.path or "")
        if self.cur() is tab:
            self.setWindowTitle(f"{tab.title()} — {APP}")

    def add_tab(self, tab):
        tab.titleChanged.connect(lambda t=tab: self._retitle(t))
        tab.statusMsg.connect(lambda m: self.statusBar().showMessage(m, 6000))
        tab.view.request_tool = lambda name, **kw: self.run_tool(name, **kw)
        self.docs.addWidget(tab)
        self.tab_widgets.append(tab)
        i = self.tabbar.addTab(tab.title())
        close = QToolButton()
        icons.bind(close, "close")
        close.setIconSize(QSize(12, 12))
        close.setFixedSize(20, 20)
        close.setToolTip("Fechar")
        close.clicked.connect(lambda _=False, t=tab: self.close_tab(self.tab_widgets.index(t)))
        self.tabbar.setTabButton(i, QTabBar.RightSide, close)
        self._retitle(tab)
        self.tabbar.setCurrentIndex(i)
        if self.pending_tool:
            t, self.pending_tool = self.pending_tool, None
            QTimer.singleShot(150, lambda: self.run_tool(t))

    def close_tab(self, i):
        if i <= 0:
            return False
        tab = self.tab_widgets[i]
        if tab.modified:
            r = QMessageBox.question(self, "Salvar alterações", f"Deseja salvar as alterações em \"{tab.title()[2:]}\"?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not tab.save()):
                return False
        self.tabbar.removeTab(i)
        self.tab_widgets.pop(i)
        self.docs.removeWidget(tab)
        tab.doc.close()
        tab.deleteLater()
        return True

    def closeEvent(self, e):
        while len(self.tab_widgets) > 1:
            self.tabbar.setCurrentIndex(len(self.tab_widgets) - 1)
            if not self.close_tab(len(self.tab_widgets) - 1):
                e.ignore()
                return
        e.accept()

    # ------------------------------------------------------------ abrir / arquivos recentes
    def recent_files(self):
        r = self.settings.value("recent", []) or []
        return [r] if isinstance(r, str) else list(r)

    def _add_recent(self, path):
        r = [p for p in self.recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        self.settings.setValue("recent", [path] + r[:19])

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        for p in self.recent_files()[:12]:
            self.recent_menu.addAction(os.path.basename(p), lambda pp=p: self.open_path(pp)).setToolTip(p)

    def open_dialog(self):
        fns, _ = QFileDialog.getOpenFileNames(self, "Abrir", self.settings.value("last_dir", os.path.expanduser("~")),
                                              "PDF (*.pdf);;Imagens e outros (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.xps *.epub *.cbz *.svg);;Todos (*.*)")
        for fn in fns:
            self.open_path(fn)
        return bool(fns)

    def open_path(self, path):
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, APP, f"Arquivo não encontrado:\n{path}")
            return
        for i, t in enumerate(self.tab_widgets):
            if t and t.path and os.path.normcase(os.path.abspath(t.path)) == os.path.normcase(os.path.abspath(path)):
                self.tabbar.setCurrentIndex(i)
                return
        self.settings.setValue("last_dir", os.path.dirname(path))
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf"):
                out = os.path.join(tempfile.mkdtemp(), os.path.splitext(os.path.basename(path))[0] + ".pdf")
                ops.office_to_pdf(path, out)
                data, save_path = open(out, "rb").read(), None
            elif ext != ".pdf":
                with pymupdf.open(path) as src:
                    data, save_path = src.convert_to_pdf(), None
            else:
                with open(path, "rb") as f:
                    data, save_path = f.read(), path
            pwd = None
            probe = pymupdf.open(stream=data, filetype="pdf")
            if probe.needs_pass:
                while True:
                    pwd, ok = QInputDialog.getText(self, "Documento protegido",
                                                   f"\"{os.path.basename(path)}\" está protegido. Senha:",
                                                   QLineEdit.Password)
                    if not ok:
                        return
                    if probe.authenticate(pwd):
                        break
                    QMessageBox.warning(self, APP, "Senha incorreta.")
            probe.close()
            tab = DocTab(data, save_path, pwd, self.settings)
            if save_path is None:
                tab.modified = True
                tab._suggested = os.path.splitext(path)[0] + ".pdf"
            self.add_tab(tab)
            if save_path:
                self._add_recent(path)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Não foi possível abrir o arquivo:\n{e}")

    def open_bytes(self, data, name):
        tab = DocTab(data, None, None, self.settings)
        tab.modified = True
        self.add_tab(tab)
        tab.path = None
        self.tabbar.setTabText(self.tabbar.currentIndex(), "● " + name)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.open_path(u.toLocalFile())

    def home_tool(self, key):
        if key == "open":
            self.open_dialog()
        elif key in NEEDS_DOC_EXCEPT:
            self.run_tool(key)
        else:
            self.pending_tool = key
            if not self.open_dialog():
                self.pending_tool = None

    # ------------------------------------------------------------ ações gerais
    def save(self):
        t = self.cur()
        if t:
            if not t.path and getattr(t, "_suggested", None):
                fn, _ = QFileDialog.getSaveFileName(self, "Salvar como", t._suggested, "PDF (*.pdf)")
                if fn and t.save(fn):
                    self._add_recent(fn)
                return
            if t.save():
                self._add_recent(t.path)

    def save_as(self):
        t = self.cur()
        if t and t.save_as():
            self._add_recent(t.path)

    def undo(self):
        if self.cur():
            self.cur().undo()

    def redo(self):
        if self.cur():
            self.cur().redo()

    def focus_search(self):
        if self.cur():
            self.search.setFocus()
            self.search.selectAll()

    def _search(self):
        t = self.cur()
        if not t:
            return
        txt = self.search.text().strip()
        if t.view.hit_list and getattr(t.view, "_last_search", None) == txt:
            t.view.next_hit(1)
            return
        t.view._last_search = txt
        n = t.view.search(txt)
        self.statusBar().showMessage(f"{n} ocorrência(s) de \"{txt}\"" if n else f"\"{txt}\" não encontrado", 6000)

    def _top_tab(self, key):
        self.tools.setVisible(True)
        self.tools.set_tab(key)

    def goto_dialog(self):
        t = self.cur()
        if t:
            n, ok = QInputDialog.getInt(self, "Ir para página", f"Página (1-{t.doc.page_count}):",
                                        t.view.current_page() + 1, 1, t.doc.page_count)
            if ok:
                t.view.goto(n - 1)

    def toggle_dark(self):
        theme.apply(not theme.is_dark)
        self.settings.setValue("dark", "true" if theme.is_dark else "false")
        self.tabbar.setTabIcon(0, icons.icon("home"))
        self._search_icon.setIcon(icons.icon("search"))
        for t in self.tab_widgets[1:]:
            t.view.apply_theme()
            t.rail.set_color(t.rail._color)
            t.side.comments.rebuild()
            t.side.attachments.rebuild()
            t.side.thumbs.list.viewport().update()
        self.home.refresh()

    def toggle_invert(self):
        for t in self.tab_widgets[1:]:
            t.view.invert = not t.view.invert
            t.view.refresh()

    def toggle_read_mode(self):
        hide = self.tools.isVisible() or self.menuBar().isVisible()
        self.tools.setVisible(not hide)
        self.doc_area.layout().itemAt(0).widget().setVisible(not hide)
        for t in self.tab_widgets[1:]:
            t.rail.setVisible(not hide)
            t.side.setVisible(not hide)
        self.statusBar().showMessage("Modo de leitura: Ctrl+H para sair" if hide else "", 4000)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def preferences(self):
        d = dialogs.PreferencesDialog(self, self.settings, ops.ocr_languages())
        if d.exec():
            self.settings.setValue("author", d.author.text() or "Usuário")
            self.settings.setValue("ocr_lang", d.ocr.currentText())
            self.settings.setValue("default_zoom", d.zoom.currentText())
            self.settings.setValue("tessdata", d.tess.text())
            if d.tess.text():
                os.environ["TESSDATA_PREFIX"] = d.tess.text()
            for t in self.tab_widgets[1:]:
                t.view.author = d.author.text() or "Usuário"
            self.home.refresh()

    def shortcuts_help(self):
        html = """<h3>Atalhos de teclado</h3><table cellpadding=4>
        <tr><td><b>Ctrl+O</b></td><td>Abrir</td><td><b>Ctrl+S</b></td><td>Salvar</td></tr>
        <tr><td><b>Ctrl+P</b></td><td>Imprimir</td><td><b>Ctrl+W</b></td><td>Fechar aba</td></tr>
        <tr><td><b>Ctrl+F / F3</b></td><td>Localizar / próximo</td><td><b>Ctrl+Z / Ctrl+Y</b></td><td>Desfazer / refazer</td></tr>
        <tr><td><b>Ctrl + roda</b></td><td>Zoom</td><td><b>Ctrl+0 / Ctrl+2</b></td><td>Ajustar página / largura</td></tr>
        <tr><td><b>V / H</b></td><td>Selecionar / Mão</td><td><b>Ctrl+Shift+H</b></td><td>Destacar</td></tr>
        <tr><td><b>Ctrl+E</b></td><td>Editar texto</td><td><b>Ctrl+H</b></td><td>Modo de leitura</td></tr>
        <tr><td><b>F4</b></td><td>Miniaturas</td><td><b>Delete</b></td><td>Excluir comentário selecionado</td></tr>
        <tr><td><b>Esc</b></td><td>Voltar à seleção</td><td><b>F11</b></td><td>Tela cheia</td></tr></table>"""
        dialogs.HtmlDialog(self, "Atalhos", html).exec()

    def about(self):
        box = QMessageBox(self)
        box.setWindowTitle(f"Sobre o {APP}")
        box.setIconPixmap(QIcon(resource("assets", "logo.png")).pixmap(96, 96))
        box.setText(f"<h2 style='margin:0'>{APP}</h2><p>Versão {__version__}</p>"
                    f"<p>Leitor e editor de PDF.</p>"
                    f"<p><b>Desenvolvedor:</b> {AUTHOR}<br>"
                    f"<b>Contato:</b> <a href='mailto:{EMAIL}'>{EMAIL}</a></p>"
                    f"<p style='color:gray'>{COPYRIGHT}. Todos os direitos reservados.<br>"
                    f"Componentes: PyMuPDF {pymupdf.VersionBind}, PySide6 (Qt), pyHanko.</p>")
        box.setTextFormat(Qt.RichText)
        box.exec()

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def check_default_app(self, force=False):
        """Pergunta (no primeiro uso) se o Lumen PDF deve ser o leitor padrão de PDF."""
        if not system.IS_WINDOWS:
            return
        if not force:
            # pergunta uma única vez (no primeiro uso); depois só pelo menu Ajuda
            if self.settings.value("default_asked", "false") == "true" or system.is_default_pdf():
                return
            self.settings.setValue("default_asked", "true")
        if system.is_default_pdf():
            QMessageBox.information(self, APP, "O Lumen PDF já é o seu leitor de PDF padrão.")
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP)
        box.setIconPixmap(QIcon(resource("assets", "logo.png")).pixmap(64, 64))
        box.setText("<b>Usar o Lumen PDF como leitor de PDF padrão?</b>")
        box.setInformativeText("O Windows vai abrir a tela de Aplicativos padrão. Escolha <b>Lumen PDF</b> "
                               "para a extensão <b>.pdf</b> e clique em <b>Definir padrão</b>.")
        yes = box.addButton("Definir como padrão", QMessageBox.AcceptRole)
        box.addButton("Agora não", QMessageBox.RejectRole)
        from PySide6.QtWidgets import QCheckBox
        never = QCheckBox("Não perguntar novamente")
        box.setCheckBox(never)
        box.exec()
        if never.isChecked():
            self.settings.setValue("ask_default", "false")
        if box.clickedButton() is yes:
            system.open_default_apps_settings()

    # ------------------------------------------------------------ execução de ferramentas
    def _pages_from(self, text, tab):
        return ops.parse_ranges(text, tab.doc.page_count)

    def _run_worker(self, label, fn, on_done, maximum=0):
        dlg = QProgressDialog(label, "Cancelar", 0, maximum, self)
        dlg.setWindowTitle(APP)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        w = Worker(fn)
        w.progress.connect(lambda a, b: (dlg.setMaximum(b), dlg.setValue(a)))
        dlg.canceled.connect(lambda: setattr(w, "cancel", True))

        def finish(res):
            dlg.close()
            on_done(res)

        def fail(msg):
            dlg.close()
            QMessageBox.critical(self, APP, msg)
        w.done.connect(finish)
        w.failed.connect(fail)
        self._worker = w
        w.start()

    def run_tool(self, name, **kw):
        tab = self.cur()
        if tab is None and name not in NEEDS_DOC_EXCEPT:
            if name in ALL_TOOLS or name in MODE_TOOLS:
                self.pending_tool = name
                if not self.open_dialog():
                    self.pending_tool = None
            return
        try:
            self._dispatch(name, tab, **kw)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Erro em \"{ALL_TOOLS.get(name, (None, name))[1]}\":\n{e}")

    def _dispatch(self, name, tab, **kw):
        v = tab.view if tab else None
        simple_modes = {"note", "highlight", "underline", "strikeout", "freetext", "ink", "rect", "ellipse",
                        "arrow", "line", "stamp", "edittext", "addtext", "image", "link", "redact", "crop",
                        "field_text", "field_check", "field_combo", "select", "hand"}
        if name in simple_modes:
            tab.set_mode(name)
            if name == "edittext":
                self.tools.set_tab("edit")
            return
        h = getattr(self, "tool_" + name, None)
        if h is None:
            QMessageBox.information(self, APP, f"Ferramenta \"{name}\" indisponível.")
            return
        h(tab, **kw)

    # --- assinatura e preenchimento
    def _signature_file(self):
        d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "assinatura.png")

    def _load_signature(self):
        fn = self._signature_file()
        return open(fn, "rb").read() if os.path.exists(fn) else None

    def tool_create_signature(self, tab=None, **kw):
        d = dialogs.SignatureDialog(self)
        if d.exec() and d.png:
            with open(self._signature_file(), "wb") as f:
                f.write(d.png)
            for t in self.tab_widgets[1:]:
                t.view.signature_png = d.png
            self.statusBar().showMessage("Assinatura salva. Clique no documento para posicioná-la.", 6000)
            return True
        return False

    def tool_signature(self, tab, **kw):
        tab.view.signature_png = tab.view.signature_png or self._load_signature()
        if not tab.view.signature_png and not self.tool_create_signature(tab):
            return
        tab.set_mode("signature")
        self.tools.set_tab("sign")

    def tool_certsign(self, tab, **kw):
        tab.set_mode("certsign")
        self.tools.set_tab("sign")

    def tool_rect_certsign(self, tab, page, rect, **kw):
        tab.set_mode("select")
        d = dialogs.CertSignDialog(self, self.settings.value("last_pfx", ""), self.settings.value("last_cert", ""),
                                   int(self.settings.value("last_sign_kind", 0)))
        if not d.exec():
            return
        kind = d.kind.currentIndex()
        src = d.pfx.text()
        try:
            if kind == 0:
                wc = d.selected_cert()
                if wc is None:
                    QMessageBox.warning(self, APP, "Nenhum certificado selecionado. Conecte o token ou instale o "
                                                   "certificado A1 no Windows e clique em Atualizar.")
                    return
                from . import wincert
                signer = wincert.make_signer(wc)
                self.settings.setValue("last_cert", wc.der.hex()[-40:])
            elif kind == 1:
                signer = signing.load_pfx(src, d.pwd.text())
                self.settings.setValue("last_pfx", src)
            else:
                signer = signing.load_pkcs11(src, d.pwd.text())
            self.settings.setValue("last_sign_kind", kind)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Não foi possível carregar o certificado:\n{e}")
            return
        pg = tab.doc[page]
        unrot = ops.to_unrot(pg, rect)
        data = tab.doc.tobytes(garbage=3, deflate=True)
        try:
            out = signing.sign_pdf_bytes(data, signer, page, tuple(unrot), pg.mediabox.height,
                                         d.reason.text(), d.location.text())
        except Exception as e:
            QMessageBox.critical(self, APP, f"A assinatura não foi concluída:\n{e}")
            return
        fn = tab.save_copy_bytes(out, "_assinado")
        if fn:
            new = DocTab(out, fn, tab.password, self.settings)
            new.has_signatures = True
            self.add_tab(new)
            self._add_recent(fn)
            QMessageBox.information(self, APP, f"Documento assinado por {signing.cert_subject(signer)}.\nSalvo em:\n{fn}")

    def _sig_results(self, tab, field=None):
        if tab.sig_results and not field:
            return tab.sig_results
        res = [r for r in tab.sig_results if r["field"] == field] if field else []
        if not res:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                res = signing.validate(tab.original_bytes, field)
            finally:
                QApplication.restoreOverrideCursor()
        return res

    def _view_signed(self, tab, info):
        data = signing.signed_revision(tab.original_bytes, info)
        if data:
            self.open_bytes(data, f"Versão assinada por {info['signer'].split(':')[0]}.pdf")

    def tool_validate_sigs(self, tab, **kw):
        dialogs.SignaturesDialog(self, self._sig_results(tab), lambda i: self._view_signed(tab, i)).exec()

    def tool_signature_info(self, tab, field=None, **kw):
        res = self._sig_results(tab, field)
        if not res:
            QMessageBox.information(self, APP, "Este campo de assinatura ainda não foi assinado.")
            return
        dialogs.SignatureInfoDialog(self, res[0], lambda i: self._view_signed(tab, i)).exec()

    # --- edição
    def tool_edit_span(self, tab, page, point, **kw):
        pg = tab.doc[page]
        span = ops.span_at(pg, point)
        if not span:
            self.statusBar().showMessage("Nenhum texto editável neste ponto (para digitalizados, use OCR antes).", 5000)
            return
        d = dialogs.EditTextDialog(self, span)
        if d.exec():
            txt, size, color, font = d.values()
            tab.checkpoint()
            ops.replace_span(pg, span, txt, size, color, font)
            tab.changed([page])

    def tool_add_text_at(self, tab, page, point, **kw):
        d = dialogs.AddTextDialog(self)
        if d.exec():
            txt, size, font, color = d.values()
            if txt:
                tab.checkpoint()
                ops.add_text(tab.doc[page], point, txt, size, font, color)
                tab.changed([page])

    def tool_rect_image(self, tab, page, rect, **kw):
        fn, _ = QFileDialog.getOpenFileName(self, "Adicionar imagem", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.tif)")
        if fn:
            tab.checkpoint()
            ops.add_image(tab.doc[page], rect, fn)
            tab.changed([page])

    def tool_rect_link(self, tab, page, rect, **kw):
        items = ["Abrir endereço web (URL)", "Ir para página deste documento"]
        kind, ok = QInputDialog.getItem(self, "Adicionar link", "Ação do link:", items, 0, False)
        if not ok:
            return
        pg = tab.doc[page]
        unrot = ops.to_unrot(pg, rect)
        if kind == items[0]:
            url, ok = QInputDialog.getText(self, "Link", "URL:", text="https://")
            if not ok or not url:
                return
            link = {"kind": pymupdf.LINK_URI, "from": unrot, "uri": url}
        else:
            n, ok = QInputDialog.getInt(self, "Link", "Página de destino:", 1, 1, tab.doc.page_count)
            if not ok:
                return
            link = {"kind": pymupdf.LINK_GOTO, "from": unrot, "page": n - 1, "to": pymupdf.Point(0, 0)}
        tab.checkpoint()
        pg.insert_link(link)
        del pg
        tab.changed([page])

    def tool_rect_crop(self, tab, page, rect, **kw):
        tab.set_mode("select")
        scope, ok = QInputDialog.getItem(self, "Cortar páginas", "Aplicar a:", ["Página atual", "Todas as páginas",
                                                                               "Remover corte de todas"], 0, False)
        if not ok:
            return
        tab.checkpoint()
        if scope.startswith("Remover"):
            ops.uncrop(tab.doc, range(tab.doc.page_count))
        else:
            ops.crop(tab.doc, [page] if scope == "Página atual" else range(tab.doc.page_count), rect)
        tab.changed(structure=True)

    def _field(self, tab, page, rect, kind):
        name, ok = QInputDialog.getText(self, "Novo campo", "Nome do campo:", text=f"{kind}_{datetime.now():%H%M%S}")
        if not ok or not name:
            return
        choices = None
        if kind == "combo":
            txt, ok = QInputDialog.getText(self, "Opções", "Opções separadas por ponto e vírgula:", text="Sim;Não")
            choices = [c.strip() for c in txt.split(";") if c.strip()]
        tab.checkpoint()
        ops.add_field(tab.doc[page], rect, kind, name, choices)
        tab.changed([page])

    def tool_rect_field_text(self, tab, page, rect, **kw):
        self._field(tab, page, rect, "text")

    def tool_rect_field_check(self, tab, page, rect, **kw):
        self._field(tab, page, rect, "check")

    def tool_rect_field_combo(self, tab, page, rect, **kw):
        self._field(tab, page, rect, "combo")

    def tool_form_fill(self, tab, **kw):
        fields = ops.list_fields(tab.doc)
        if not fields:
            QMessageBox.information(self, APP, "Este documento não possui campos de formulário.\n"
                                               "Use 'Campo de texto' ou 'Caixa de seleção' para criá-los, ou "
                                               "'Adicionar texto' para preencher formulários sem campos.")
            return
        d = dialogs.FormFillDialog(self, fields)
        if d.exec():
            tab.checkpoint()
            for f, val in d.values():
                ops.set_field(tab.doc, f["page"], f["xref"], val)
            tab.changed()

    def tool_watermark(self, tab, **kw):
        d = dialogs.WatermarkDialog(self, tab.doc.page_count)
        if d.exec():
            tab.checkpoint()
            ops.watermark(tab.doc, d.text.text(), self._pages_from(d.pages.text(), tab), d.size.value(),
                          d.angle.value(), d.opacity.value() / 100, d.colorb.color, d.image.text() or None)
            tab.changed()

    def tool_pagenum(self, tab, **kw):
        d = dialogs.PageNumberDialog(self, tab.doc.page_count)
        if d.exec():
            fmt = d.fmt.currentText()
            tab.checkpoint()
            ops.page_numbers(tab.doc, "" if fmt.startswith("(sem") else fmt, d.pos.currentText(), d.size.value(),
                             d.start.value(), self._pages_from(d.pages.text(), tab),
                             header_text=d.header.text(), footer_text=d.footer.text())
            tab.changed()

    def tool_background(self, tab, **kw):
        c = QColorDialog.getColor(QColor("#fffbe6"), self, "Cor de fundo das páginas")
        if c.isValid():
            tab.checkpoint()
            ops.set_background(tab.doc, c.name())
            tab.changed()

    def tool_properties(self, tab, **kw):
        size = len(open(tab.path, "rb").read()) if tab.path and os.path.exists(tab.path) else len(tab.doc.tobytes())
        d = dialogs.PropertiesDialog(self, tab.doc, tab.path, size)
        if d.exec():
            tab.checkpoint()
            md = dict(tab.doc.metadata or {})
            md.update(d.metadata())
            tab.doc.set_metadata({k: md.get(k, "") for k in ("title", "author", "subject", "keywords", "creator",
                                                              "producer", "creationDate", "modDate")})
            tab.changed([])

    # --- comentários
    def tool_comments_summary(self, tab, **kw):
        items = list_annots(tab.doc)
        rows = "".join(f"<tr><td>{a['page'] + 1}</td><td>{a['name']}</td><td>{a['author']}</td>"
                       f"<td>{(a['content'] or '').replace(chr(10), '<br>')}</td></tr>" for a in items)
        html = (f"<h2>Resumo dos comentários</h2><p>{os.path.basename(tab.path or 'Documento')} — {len(items)} comentário(s)</p>"
                f"<table border=1 cellspacing=0 cellpadding=5><tr><th>Pág.</th><th>Tipo</th><th>Autor</th><th>Comentário</th></tr>{rows}</table>")
        dialogs.HtmlDialog(self, "Resumo dos comentários", html, "comentarios.html").exec()

    def tool_flatten(self, tab, **kw):
        if QMessageBox.question(self, APP, "Nivelar torna comentários e campos de formulário parte fixa da página "
                                           "(não poderão mais ser editados). Continuar?") == QMessageBox.Yes:
            tab.checkpoint()
            ops.flatten(tab.doc)
            tab.changed(structure=True)

    def tool_attach(self, tab, **kw):
        tab.side.show_panel(3)
        tab.side.attachments.add()

    # --- organizar
    def tool_organize(self, tab, **kw):
        OrganizeDialog(tab).exec()

    def tool_rotate(self, tab, **kw):
        items = ["Página atual ↻ 90°", "Página atual ↺ 90°", "Todas ↻ 90°", "Todas ↺ 90°", "Todas 180°"]
        sel = tab.side.thumbs.selected_pages()
        if len(sel) > 1:
            items = [f"Páginas selecionadas ({len(sel)}) ↻ 90°", f"Páginas selecionadas ({len(sel)}) ↺ 90°"] + items
        ch, ok = QInputDialog.getItem(self, "Girar páginas", "Girar:", items, 0, False)
        if not ok:
            return
        angle = 180 if "180" in ch else (90 if "↻" in ch else -90)
        pages = sel if ch.startswith("Páginas sel") else (
            list(range(tab.doc.page_count)) if ch.startswith("Todas") else [tab.view.current_page()])
        tab.rotate(pages, angle)

    def tool_rotate_current(self, tab, angle=90, **kw):
        tab.rotate([tab.view.current_page()], angle)

    def tool_delete_pages(self, tab, **kw):
        sel = tab.side.thumbs.selected_pages()
        default = ", ".join(str(p + 1) for p in sel) if sel else str(tab.view.current_page() + 1)
        txt, ok = QInputDialog.getText(self, "Excluir páginas", f"Páginas a excluir (1-{tab.doc.page_count}):", text=default)
        if ok:
            pages = self._pages_from(txt, tab)
            if pages:
                tab.delete_pages(pages)

    def tool_insert_blank(self, tab, **kw):
        tab.insert_blank(tab.view.current_page() + 1)

    def tool_insert_file(self, tab, **kw):
        tab.insert_file_dialog(tab.view.current_page() + 1)

    def tool_extract(self, tab, **kw):
        tab.extract_dialog(tab.side.thumbs.selected_pages() or None)

    def tool_split(self, tab, **kw):
        d = dialogs.SplitDialog(self)
        if not d.exec():
            return
        mode, val = d.values()
        out_dir = QFileDialog.getExistingDirectory(self, "Pasta de destino", os.path.dirname(tab.path or os.path.expanduser("~")))
        if out_dir:
            base = os.path.splitext(os.path.basename(tab.path or "Documento"))[0]
            files = ops.split(tab.doc, mode, val, out_dir, base)
            QMessageBox.information(self, APP, f"{len(files)} arquivo(s) criado(s) em:\n{out_dir}")

    def tool_merge(self, tab=None, **kw):
        fns, _ = QFileDialog.getOpenFileNames(self, "Combinar arquivos (selecione na ordem desejada)",
                                              self.settings.value("last_dir", ""),
                                              "PDF e imagens (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if not fns:
            return
        from .dialogs import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QAbstractItemView
        d = QDialog(self)
        d.setWindowTitle("Combinar arquivos")
        d.resize(520, 420)
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel("Arraste para definir a ordem:"))
        lst = QListWidget()
        lst.setDragDropMode(QAbstractItemView.InternalMove)
        if tab and tab.path:
            fns = [tab.path] + [f for f in fns if f != tab.path]
        for f in fns:
            it = QListWidgetItem(icons.icon("textfile"), os.path.basename(f))
            it.setData(Qt.UserRole, f)
            lst.addItem(it)
        lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Combinar")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if d.exec():
            order = [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]
            merged = ops.merge(order)
            self.open_bytes(merged.tobytes(garbage=3, deflate=True), "Combinado.pdf")

    # --- converter
    def _save_target(self, tab, ext, label):
        base = os.path.splitext(tab.path or os.path.join(os.path.expanduser("~"), "Documento"))[0] + ext
        fn, _ = QFileDialog.getSaveFileName(self, f"Exportar para {label}", base, f"{label} (*{ext})")
        return fn

    def _open_file(self, fn):
        if QMessageBox.question(self, APP, f"Arquivo criado:\n{fn}\n\nDeseja abri-lo?") == QMessageBox.Yes:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(fn))

    def tool_export_word(self, tab, **kw):
        fn = self._save_target(tab, ".docx", "Word")
        if fn:
            data = tab.doc.tobytes()
            self._run_worker("Convertendo para Word…", lambda w: ops.to_docx(data, fn), lambda r: self._open_file(fn))

    def tool_export_excel(self, tab, **kw):
        fn = self._save_target(tab, ".xlsx", "Excel")
        if fn:
            data = tab.doc.tobytes()
            self._run_worker("Extraindo tabelas…", lambda w: ops.to_xlsx(pymupdf.open("pdf", data), fn),
                             lambda r: self._open_file(fn))

    def tool_export_text(self, tab, **kw):
        fn = self._save_target(tab, ".txt", "Texto")
        if fn:
            ops.to_text(tab.doc, fn)
            self._open_file(fn)

    def tool_export_image(self, tab, **kw):
        d = dialogs.ImageExportDialog(self, tab.doc.page_count)
        if not d.exec():
            return
        out = QFileDialog.getExistingDirectory(self, "Pasta de destino", os.path.dirname(tab.path or os.path.expanduser("~")))
        if out:
            base = os.path.splitext(os.path.basename(tab.path or "Documento"))[0]
            files = ops.to_images(tab.doc, out, base, d.fmt.currentText(), int(d.dpi.currentText()),
                                  self._pages_from(d.pages.text(), tab))
            QMessageBox.information(self, APP, f"{len(files)} imagem(ns) exportada(s) para:\n{out}")

    def tool_create_pdf(self, tab=None, **kw):
        fns, _ = QFileDialog.getOpenFileNames(self, "Criar PDF a partir de arquivos", self.settings.value("last_dir", ""),
                                              "Suportados (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.doc *.docx *.xls *.xlsx *.ppt *.pptx *.odt *.rtf *.txt *.xps *.epub *.svg)")
        if not fns:
            return
        office = [f for f in fns if os.path.splitext(f)[1].lower() in (".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf")]

        def work(w):
            parts = []
            tmpdir = tempfile.mkdtemp()
            for f in fns:
                if f in office:
                    out = os.path.join(tmpdir, os.path.basename(f) + ".pdf")
                    ops.office_to_pdf(f, out)
                    parts.append(out)
                elif f.lower().endswith(".txt"):
                    lines = open(f, encoding="utf-8", errors="replace").read().splitlines() or [""]
                    d = pymupdf.open()
                    per_page = 56
                    for k in range(0, len(lines), per_page):
                        page = d.new_page()
                        y = 60
                        for ln in lines[k:k + per_page]:
                            page.insert_text((50, y), ln[:110], fontsize=10, fontname="cour")
                            y += 13
                    out = os.path.join(tmpdir, os.path.basename(f) + ".pdf")
                    d.save(out)
                    parts.append(out)
                else:
                    parts.append(f)
            return ops.merge(parts).tobytes(garbage=3, deflate=True)
        self._run_worker("Criando PDF…", work, lambda data: self.open_bytes(data, "Novo documento.pdf"))

    def tool_compress(self, tab, **kw):
        d = dialogs.CompressDialog(self)
        if not d.exec():
            return
        before = len(tab.doc.tobytes(garbage=1))
        src = tab.doc.tobytes()
        level = d.value()

        def done(data):
            pct = 100 - len(data) * 100 / max(before, 1)
            if QMessageBox.question(self, APP, f"Tamanho: {before / 1024:.0f} KB → {len(data) / 1024:.0f} KB "
                                               f"({pct:.0f}% menor).\nAplicar ao documento?") == QMessageBox.Yes:
                tab.replace_with(data)
        self._run_worker("Comprimindo…", lambda w: ops.compress(pymupdf.open("pdf", src), level), done)

    def tool_ocr(self, tab, **kw):
        if self.settings.value("tessdata"):
            os.environ["TESSDATA_PREFIX"] = self.settings.value("tessdata")
        langs = ops.ocr_languages()
        d = dialogs.OcrDialog(self, langs, tab.doc.page_count, self.settings.value("ocr_lang", "por"))
        if not d.exec() or not langs:
            return
        src = tab.doc.tobytes()
        pages = self._pages_from(d.pages.text(), tab)
        lang, dpi, force = d.lang.currentText(), int(d.dpi.currentText()), d.force.isChecked()

        def work(w):
            doc = pymupdf.open("pdf", src)
            n = ops.ocr(doc, pages, lang, dpi, progress=lambda a, b: (w.progress.emit(a, b), not w.cancel)[1],
                        skip_text_pages=not force)
            return n, doc.tobytes(garbage=3, deflate=True)

        def done(res):
            n, data = res
            tab.replace_with(data)
            QMessageBox.information(self, APP, f"OCR concluído em {n} página(s). O texto agora pode ser pesquisado e copiado.")
        self._run_worker("Reconhecendo texto…", work, done, maximum=len(pages))

    # --- proteger
    def tool_protect(self, tab, **kw):
        d = dialogs.ProtectDialog(self)
        if not d.exec():
            return
        u, o, perms = d.values()
        if not u and not o:
            QMessageBox.warning(self, APP, "Informe ao menos uma senha.")
            return
        data = ops.encrypted_bytes(tab.doc, u, o, perms)
        fn = tab.save_copy_bytes(data, "_protegido")
        if fn:
            QMessageBox.information(self, APP, f"Documento protegido salvo em:\n{fn}")

    def tool_unprotect(self, tab, **kw):
        if not tab.doc.is_encrypted and not (tab.doc.metadata or {}).get("encryption"):
            QMessageBox.information(self, APP, "Este documento não está protegido por senha.")
            return
        tab.replace_with(ops.decrypted_bytes(tab.doc))
        tab.password = None
        QMessageBox.information(self, APP, "Senha removida. Salve o documento para manter a alteração.")

    def tool_redact_search(self, tab, **kw):
        d = dialogs.RedactSearchDialog(self)
        if not d.exec():
            return
        tab.checkpoint()
        preset = d.preset.currentText()
        if preset in ops.PATTERNS:
            n = ops.redact_pattern(tab.doc, ops.PATTERNS[preset])
        else:
            n = ops.redact_search(tab.doc, d.text.text())
        if d.apply_now.isChecked():
            ops.apply_redactions(tab.doc)
        tab.changed()
        self.statusBar().showMessage(f"{n} ocorrência(s) marcada(s) para ocultação.", 8000)

    def tool_redact_apply(self, tab, **kw):
        if QMessageBox.question(self, APP, "Aplicar as ocultações remove definitivamente o conteúdo marcado "
                                           "(texto, imagens e desenhos). Continuar?") == QMessageBox.Yes:
            tab.checkpoint()
            n = ops.apply_redactions(tab.doc)
            tab.changed(structure=True)
            self.statusBar().showMessage(f"Ocultações aplicadas em {n} página(s).", 6000)

    def tool_sanitize(self, tab, **kw):
        if QMessageBox.question(self, APP, "Remover metadados, anexos, JavaScript, miniaturas e texto oculto?") == QMessageBox.Yes:
            tab.checkpoint()
            ops.sanitize(tab.doc)
            tab.changed(structure=True)

    # --- outros
    def tool_compare(self, tab=None, **kw):
        a_doc, a_name = (tab.doc, os.path.basename(tab.path or "Atual")) if tab else (None, None)
        if a_doc is None:
            fa, _ = QFileDialog.getOpenFileName(self, "Arquivo original", "", "PDF (*.pdf)")
            if not fa:
                return
            a_doc, a_name = pymupdf.open(fa), os.path.basename(fa)
        fb, _ = QFileDialog.getOpenFileName(self, "Comparar com (versão revisada)", "", "PDF (*.pdf)")
        if not fb:
            return
        html, n = ops.compare(a_doc, pymupdf.open(fb), a_name, os.path.basename(fb))
        dialogs.HtmlDialog(self, "Comparar arquivos", html, "comparacao.html").exec()

    def tool_print(self, tab, **kw):
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(os.path.basename(tab.path or "Documento"))
        printer.setFromTo(1, tab.doc.page_count)
        dlg = QPrintDialog(printer, self)
        dlg.setOption(QPrintDialog.PrintPageRange, True)
        dlg.setOption(QPrintDialog.PrintCurrentPage, True)
        dlg.setMinMax(1, tab.doc.page_count)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        if printer.printRange() == QPrinter.PageRange:
            pages = range(printer.fromPage() - 1, printer.toPage())
        elif printer.printRange() == QPrinter.CurrentPage:
            pages = [tab.view.current_page()]
        else:
            pages = range(tab.doc.page_count)
        dpi = min(printer.resolution(), 300)
        painter = QPainter(printer)
        first = True
        for p in pages:
            if not first:
                printer.newPage()
            first = False
            pix = tab.doc[p].get_pixmap(dpi=dpi, alpha=False, annots=True)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            area = painter.viewport()
            sz = img.size().scaled(area.size(), Qt.KeepAspectRatio)
            painter.setViewport(area.x() + (area.width() - sz.width()) // 2, area.y(), sz.width(), sz.height())
            painter.setWindow(img.rect())
            painter.drawImage(0, 0, img)
            painter.setViewport(area)
        painter.end()
        self.statusBar().showMessage("Documento enviado para a impressora.", 5000)

    def tool_read_aloud(self, tab, **kw):
        self.tool_speak(tab, text=tab.view.selected_text() or tab.doc[tab.view.current_page()].get_text("text", sort=True))

    def tool_speak(self, tab, text="", **kw):
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
        except ImportError:
            QMessageBox.information(self, APP, "Leitura em voz alta indisponível nesta instalação do Qt.")
            return
        if self.tts is None:
            self.tts = QTextToSpeech(self)
            for loc in self.tts.availableLocales():
                if loc.name().startswith("pt"):
                    self.tts.setLocale(loc)
                    break
        if self.tts.state() == QTextToSpeech.Speaking:
            self.tts.stop()
            return
        if text.strip():
            self.tts.say(text)
            self.statusBar().showMessage("Lendo em voz alta… (clique novamente para parar)", 5000)
