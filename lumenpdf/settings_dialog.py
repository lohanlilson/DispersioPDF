"""Janela de Preferências (Ctrl+K) — categorias à esquerda, opções à direita."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
                               QWidget, QFormLayout, QLabel, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
                               QLineEdit, QPushButton, QSlider, QFileDialog, QMessageBox, QGroupBox, QColorDialog,
                               QScrollArea, QFrame)

from . import icons, ops, signing
from .config import cfg, DEFAULTS
from .dialogs import ColorButton

ACCENTS = [("Violeta Lumen (padrão)", "#6d3cf0"), ("Azul", "#1473e6"), ("Magenta", "#e8266c"), ("Verde", "#2d9d78"),
           ("Laranja", "#e68619"), ("Vermelho", "#d7373f"), ("Grafite", "#4b4b4b")]


def _combo(items, current):
    """items: lista de (rótulo, valor)."""
    c = QComboBox()
    for label, val in items:
        c.addItem(label, val)
    i = c.findData(current)
    c.setCurrentIndex(max(i, 0))
    return c


def _check(text, key):
    b = QCheckBox(text)
    b.setChecked(cfg.get(key))
    return b


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Preferências")
        self.resize(860, 600)
        self.w = {}  # chave -> widget
        root = QVBoxLayout(self)
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        self.nav.setIconSize(QSize(18, 18))
        self.pages = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)
        for title, ic, builder in [("Geral", "home", self._general), ("Aparência", "moon", self._appearance),
                                   ("Documentos", "fit_page", self._documents), ("Comentários", "comments", self._comments),
                                   ("Assinatura", "certificate", self._signature),
                                   ("Impressão", "print", self._printing), ("OCR e conversão", "ocr", self._convert),
                                   ("Avançado", "gear", self._advanced)]:
            self.nav.addItem(QListWidgetItem(icons.icon(ic), title))
            page = QWidget()
            form = QFormLayout(page)
            form.setLabelAlignment(Qt.AlignRight)
            form.setVerticalSpacing(10)
            head = QLabel(title)
            head.setStyleSheet("font-size:17px; font-weight:600; margin-bottom:6px;")
            form.addRow(head)
            builder(form)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        row = QHBoxLayout()
        reset = QPushButton("Restaurar padrões")
        reset.clicked.connect(self._reset)
        exp = QPushButton("Exportar…")
        exp.clicked.connect(self._export)
        imp = QPushButton("Importar…")
        imp.clicked.connect(self._import)
        for b in (reset, exp, imp):
            row.addWidget(b)
        row.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        root.addLayout(row)

    # ------------------------------------------------------------ páginas
    def _general(self, f):
        from .config import windows_user_name
        saved = str(cfg.qs.value("author", "") or "")
        self.w["author"] = QLineEdit("" if saved in ("", "Usuário") else saved)
        self.w["author"].setPlaceholderText(f"{windows_user_name()} (usuário do Windows)")
        self.w["author"].setToolTip("Deixe em branco para usar o nome do usuário do Windows")
        f.addRow("Seu nome (comentários e boas-vindas):", self.w["author"])
        self.w["window_mode"] = _combo([("Sempre maximizada", "maximized"), ("Tamanho e posição da última vez", "last"),
                                        ("Janela normal", "normal")], cfg.get("window_mode"))
        f.addRow("Ao abrir o programa, a janela fica:", self.w["window_mode"])
        self.w["startup"] = _combo([("Mostrar a tela Início", "home"),
                                    ("Reabrir os documentos da última sessão", "last_session")], cfg.get("startup"))
        f.addRow("Ao iniciar:", self.w["startup"])
        sp = QSpinBox()
        sp.setRange(0, 50)
        sp.setValue(cfg.get("recent_max"))
        self.w["recent_max"] = sp
        f.addRow("Arquivos recentes na lista:", sp)
        self.w["autosave"] = _check("Salvar automaticamente as alterações", "autosave")
        self.w["autosave"].setToolTip("Salva o documento alguns segundos depois de cada alteração e ao fechar, sem perguntar.\n"
                                      "A versão de antes das alterações fica em Arquivo › Versões anteriores.\n"
                                      "Documentos novos (ainda sem arquivo) e documentos assinados continuam pedindo para salvar.")
        f.addRow(self.w["autosave"])
        self.w["confirm_delete_pages"] = _check("Pedir confirmação antes de excluir páginas", "confirm_delete_pages")
        f.addRow(self.w["confirm_delete_pages"])
        self.w["auto_update"] = _check("Verificar atualizações automaticamente ao abrir", "auto_update")
        f.addRow(self.w["auto_update"])
        from . import system
        if system.IS_WINDOWS:
            b = QPushButton("Definir como leitor de PDF padrão…")
            b.clicked.connect(lambda: self.win.check_default_app(force=True))
            f.addRow("Leitor padrão:", b)

    def _appearance(self, f):
        self.w["theme"] = _combo([("Claro", "light"), ("Escuro", "dark"), ("Seguir o Windows", "system")], cfg.get("theme"))
        f.addRow("Tema:", self.w["theme"])
        acc = QComboBox()
        for name, col in ACCENTS:
            acc.addItem(icons.icon("star", col), name, col)
        acc.addItem("Personalizada…", "custom")
        i = acc.findData(cfg.get("accent"))
        self._custom_accent = cfg.get("accent")
        if i < 0:
            acc.setItemText(acc.count() - 1, f"Personalizada ({cfg.get('accent')})")
            i = acc.count() - 1
        acc.setCurrentIndex(i)
        acc.activated.connect(self._accent_pick)
        self.w["accent"] = acc
        f.addRow("Cor de destaque:", acc)
        self.w["ui_size"] = _combo([("Pequeno", "small"), ("Normal", "normal"), ("Grande", "large")], cfg.get("ui_size"))
        f.addRow("Tamanho dos textos da interface:", self.w["ui_size"])
        canvas = cfg.get("canvas_color")
        self.canvas_default = QCheckBox("Usar a cor do tema")
        self.canvas_default.setChecked(not canvas)
        self.canvas_btn = ColorButton(canvas or "#e9e9e9")
        self.canvas_btn.setEnabled(bool(canvas))
        self.canvas_default.toggled.connect(lambda on: self.canvas_btn.setEnabled(not on))
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.canvas_default)
        rl.addWidget(self.canvas_btn)
        rl.addStretch()
        f.addRow("Fundo da área do documento:", row)
        self.w["show_tools_panel"] = _check("Mostrar o painel “Todas as ferramentas”", "show_tools_panel")
        self.w["show_quick_rail"] = _check("Mostrar a barra de ferramentas rápidas ao lado do documento", "show_quick_rail")
        self.w["show_sig_bar"] = _check("Mostrar a faixa de status em documentos assinados", "show_sig_bar")
        self.w["page_shadow"] = _check("Sombra nas páginas", "page_shadow")
        for k in ("show_tools_panel", "show_quick_rail", "show_sig_bar", "page_shadow"):
            f.addRow(self.w[k])
        self.w["open_side_panel"] = _combo([("Nenhum", "none"), ("Miniaturas de página", "thumbs"),
                                            ("Marcadores", "bookmarks"), ("Comentários", "comments")],
                                           cfg.get("open_side_panel"))
        f.addRow("Painel lateral aberto ao abrir um PDF:", self.w["open_side_panel"])

    def _accent_pick(self, i):
        acc = self.w["accent"]
        if acc.itemData(i) == "custom":
            c = QColorDialog.getColor(QColor(self._custom_accent), self, "Cor de destaque")
            if c.isValid():
                self._custom_accent = c.name()
                acc.setItemText(i, f"Personalizada ({c.name()})")

    def _documents(self, f):
        self.w["default_zoom"] = _combo([(z, z) for z in ("Ajustar largura", "Ajustar página", "50%", "75%", "100%",
                                                         "125%", "150%", "200%")], cfg.get("default_zoom"))
        f.addRow("Zoom ao abrir:", self.w["default_zoom"])
        self.w["two_page"] = _check("Exibir duas páginas lado a lado", "two_page")
        self.w["remember_position"] = _check("Reabrir cada documento na página e zoom em que parei", "remember_position")
        self.w["invert_pages"] = _check("Inverter cores das páginas (leitura noturna)", "invert_pages")
        self.w["wheel_zoom"] = _check("Roda do mouse aplica zoom (rolar com Ctrl + roda)", "wheel_zoom")
        self.w["middle_autoscroll"] = _check("Botão do meio do mouse ativa a rolagem automática", "middle_autoscroll")
        self.w["highlight_fields"] = _check("Destacar campos de formulário em azul (não aparece na impressão)", "highlight_fields")
        for k in ("two_page", "remember_position", "invert_pages", "wheel_zoom", "middle_autoscroll", "highlight_fields"):
            f.addRow(self.w[k])

    def _comments(self, f):
        for key, label in [("color_highlight", "Destacar"), ("color_underline", "Sublinhar"), ("color_strikeout", "Tachar"),
                           ("color_note", "Nota"), ("color_freetext", "Caixa de texto"), ("color_ink", "Desenho à mão livre"),
                           ("color_shapes", "Formas (retângulo, elipse, seta, linha)")]:
            self.w[key] = ColorButton(cfg.get(key))
            f.addRow(f"Cor — {label}:", self.w[key])
        sw = QDoubleSpinBox()
        sw.setRange(0.5, 12)
        sw.setSingleStep(0.5)
        sw.setValue(cfg.get("stroke_width"))
        sw.setSuffix(" pt")
        self.w["stroke_width"] = sw
        f.addRow("Espessura das linhas:", sw)
        op = QSpinBox()
        op.setRange(10, 100)
        op.setSuffix(" %")
        op.setValue(cfg.get("annot_opacity"))
        self.w["annot_opacity"] = op
        f.addRow("Opacidade:", op)

    def _signature(self, f):
        self.w["sign_reason"] = QLineEdit(cfg.get("sign_reason"))
        self.w["sign_location"] = QLineEdit(cfg.get("sign_location"))
        f.addRow("Motivo padrão:", self.w["sign_reason"])
        f.addRow("Local padrão:", self.w["sign_location"])
        self.w["sign_tsa"] = _check("Aplicar carimbo de tempo", "sign_tsa")
        f.addRow(self.w["sign_tsa"])
        tsa = QComboBox()
        tsa.setEditable(True)
        for label, url in signing.TSA_SERVERS.items():
            tsa.addItem(label, url)
        i = tsa.findData(cfg.get("sign_tsa_url"))
        if i >= 0:
            tsa.setCurrentIndex(i)
        else:
            tsa.setEditText(cfg.get("sign_tsa_url"))
        self.w["sign_tsa_url"] = tsa
        f.addRow("Servidor de carimbo de tempo:", tsa)
        self.w["sign_ltv"] = _check("Incluir validação de longo prazo (LTV)", "sign_ltv")
        f.addRow(self.w["sign_ltv"])
        self.w["save_copies"] = _combo([("Perguntar onde salvar", "ask"),
                                        ("Salvar automaticamente na mesma pasta do original", "same_folder")],
                                       cfg.get("save_copies"))
        f.addRow("Documento assinado / protegido:", self.w["save_copies"])
        self.w["sign_suffix"] = QLineEdit(cfg.get("sign_suffix"))
        f.addRow("Sufixo do arquivo assinado:", self.w["sign_suffix"])
        sig = QPushButton("Criar ou alterar minha assinatura…")
        sig.clicked.connect(lambda: self.win.run_tool("create_signature"))
        f.addRow("Preencher e assinar:", sig)

    def _printing(self, f):
        info = QLabel("A impressão rápida é usada quando você clica em “Impressão rápida” no Outlook, em "
                      "“Imprimir” no botão direito do Windows (inclusive com vários PDFs selecionados) ou ao "
                      "arrastar um PDF para uma impressora. Ela imprime direto, sem abrir janela.")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        f.addRow(info)
        self.w["quick_print_mode"] = _combo([("Padrão (impressora padrão, ajustar à folha, colorido)", "default"),
                                             ("Últimas opções usadas no gerenciador de impressão", "last")],
                                            cfg.get("quick_print_mode"))
        f.addRow("Impressão rápida usa:", self.w["quick_print_mode"])
        self.w["quick_print_notify"] = _check("Mostrar aviso na área de notificação ao imprimir", "quick_print_notify")
        f.addRow(self.w["quick_print_notify"])

    def _convert(self, f):
        langs = ops.ocr_languages() or ["por"]
        names = {"por": "Português", "eng": "Inglês", "spa": "Espanhol"}
        self.w["ocr_lang"] = _combo([(names.get(l, l), l) for l in langs] + [("Português + Inglês", "por+eng")],
                                    cfg.get("ocr_lang"))
        f.addRow("Idioma do OCR:", self.w["ocr_lang"])
        self.w["ocr_dpi"] = _combo([("200 dpi (mais rápido)", 200), ("300 dpi (recomendado)", 300),
                                    ("400 dpi (mais preciso)", 400)], cfg.get("ocr_dpi"))
        f.addRow("Resolução do OCR:", self.w["ocr_dpi"])
        self.w["compress_level"] = _combo([("Baixa compressão (alta qualidade)", "baixa"), ("Média (recomendado)", "media"),
                                           ("Alta compressão (menor arquivo)", "alta")], cfg.get("compress_level"))
        f.addRow("Compressão padrão:", self.w["compress_level"])
        self.w["image_format"] = _combo([("PNG", "png"), ("JPG", "jpg"), ("TIFF", "tiff")], cfg.get("image_format"))
        self.w["image_dpi"] = _combo([(f"{d} dpi", d) for d in (72, 150, 200, 300, 600)], cfg.get("image_dpi"))
        f.addRow("Exportar imagem — formato:", self.w["image_format"])
        f.addRow("Exportar imagem — resolução:", self.w["image_dpi"])

    def _advanced(self, f):
        self.w["tessdata"] = QLineEdit(cfg.get("tessdata"))
        self.w["tessdata"].setPlaceholderText("(vazio = usar os idiomas que acompanham o programa)")
        f.addRow("Pasta de idiomas do OCR:", self.w["tessdata"])
        from . import errors
        b = QPushButton("Abrir pasta de registros de erro")
        b.clicked.connect(lambda: __import__("PySide6.QtGui", fromlist=["QDesktopServices"]).QDesktopServices.openUrl(
            __import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl.fromLocalFile(errors.log_dir())))
        f.addRow("Diagnóstico:", b)
        c = QPushButton("Limpar posições salvas dos documentos")
        c.clicked.connect(self._clear_docs)
        f.addRow("Privacidade:", c)
        r = QPushButton("Limpar lista de arquivos recentes")
        r.clicked.connect(lambda: (cfg.qs.setValue("recent", []), self.win.home.refresh()))
        f.addRow("", r)

    def _clear_docs(self):
        cfg.qs.remove("docs")
        QMessageBox.information(self, "Preferências", "Posições de leitura apagadas.")

    # ------------------------------------------------------------ salvar
    def _value(self, key, w):
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QComboBox):
            if key == "accent":
                d = w.currentData()
                return self._custom_accent if d == "custom" else d
            if key == "sign_tsa_url":
                d = w.currentData()
                return d if d and w.currentText() == w.itemText(w.currentIndex()) else w.currentText().strip()
            return w.currentData()
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            return w.value()
        if isinstance(w, ColorButton):
            return w.color
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return None

    def _save(self):
        for key, w in self.w.items():
            v = self._value(key, w)
            if key == "author" and not v:
                v = ""  # usa o usuário do Windows
            cfg.set(key, v)
        cfg.set("canvas_color", "" if self.canvas_default.isChecked() else self.canvas_btn.color)
        self.win.apply_settings()
        self.accept()

    def _reset(self):
        if QMessageBox.question(self, "Preferências", "Restaurar todas as preferências para o padrão?") == QMessageBox.Yes:
            cfg.reset()
            self.win.apply_settings()
            self.accept()

    def _export(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Exportar preferências", "LumenPDF-preferencias.ini", "INI (*.ini)")
        if fn:
            cfg.export(fn)

    def _import(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Importar preferências", "", "INI (*.ini)")
        if fn:
            cfg.import_(fn)
            self.win.apply_settings()
            self.accept()
