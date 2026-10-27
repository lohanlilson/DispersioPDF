"""Uma aba de documento: documento aberto, histórico de desfazer, visualizador e painéis."""
import os

import pymupdf
from PySide6.QtCore import Qt, Signal, QThread, QTimer
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


_RUNNING = set()   # tarefas em segundo plano ainda vivas (paradas com segurança ao fechar o programa)


def _track(th):
    _RUNNING.add(th)
    th.finished.connect(lambda th=th: _RUNNING.discard(th))
    return th


def stop_background():
    for th in list(_RUNNING):
        th.requestInterruption()
    for th in list(_RUNNING):
        th.wait(5000)


import atexit as _atexit
_atexit.register(stop_background)


class _PayThread(QThread):
    done = Signal(object)

    def __init__(self, data, password):
        super().__init__()
        self.data, self.password = data, password

    def run(self):
        try:
            import pymupdf
            from . import pagamentos
            d = pymupdf.open(stream=self.data, filetype="pdf")
            if d.needs_pass and self.password:
                d.authenticate(self.password)
            self.done.emit(pagamentos.scan(d, cancel=self.isInterruptionRequested))
            d.close()
        except Exception:
            self.done.emit([])


class _OrientThread(QThread):
    done = Signal(object)
    MAX_PAGES = 40

    def __init__(self, data, password):
        super().__init__()
        self.data, self.password = data, password

    def run(self):
        """O OCR segura a trava do Python: roda num processo à parte para a janela não engasgar."""
        import json, subprocess, sys, tempfile, time
        tmp = tempfile.mkdtemp(prefix="lumen-pos-")
        src, out = os.path.join(tmp, "doc.pdf"), os.path.join(tmp, "res.json")
        proc = None
        try:
            with open(src, "wb") as f:
                f.write(self.data)
            if getattr(sys, "frozen", False):
                cmd = [sys.executable]
            else:
                cmd = [sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")]
            cmd += ["--orient-scan", src, out, str(self.MAX_PAGES), cfg.get("ocr_lang") or "por"]
            flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=flags)
            proc.stdin.write(((self.password or "") + "\n").encode("utf-8"))
            proc.stdin.close()
            while proc.poll() is None:
                if self.isInterruptionRequested():
                    proc.kill()
                    return
                time.sleep(0.1)
            with open(out) as f:
                self.done.emit({int(k): v for k, v in json.load(f).items()})
        except Exception:
            self.done.emit({})
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class OrientBar(QFrame):
    """Aviso: páginas de lado ou de cabeça para baixo, com botão para endireitar."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.fixes = {}
        self.setObjectName("OrientBar")
        self.setStyleSheet("QFrame#OrientBar{background:#fff6dd; border:1px solid #c58a00; border-radius:8px;}"
                           "QFrame#OrientBar QLabel{color:#222; background:transparent;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        ic = QLabel("<span style='font-size:18px; color:#c58a00'>⟳</span>")
        self.text = QLabel()
        self.text.setWordWrap(True)
        fix = QPushButton("Endireitar")
        fix.clicked.connect(self._apply)
        close = QPushButton("×")
        close.setFlat(True)
        close.setFixedWidth(30)
        close.setStyleSheet("font-size:18px; color:#555; border:none;")
        close.clicked.connect(self.hide)
        for w in (ic, self.text, fix, close):
            lay.addWidget(w, 1 if w is self.text else 0)
        self.hide()

    def show_fixes(self, fixes):
        self.fixes = fixes
        if not fixes:
            self.hide()
            return
        pages = sorted(fixes)
        lst = ", ".join(str(p + 1) for p in pages[:12]) + ("…" if len(pages) > 12 else "")
        self.text.setText(f"<b>{'A página' if len(pages) == 1 else 'As páginas'} {lst}</b> "
                          f"{'está' if len(pages) == 1 else 'estão'} de lado ou de cabeça para baixo.")
        self.show()

    def _apply(self):
        t = self.tab
        t.checkpoint()
        for p, r in self.fixes.items():
            if p < t.doc.page_count:
                t.doc[p].set_rotation(r)
        t.changed(structure=True)
        t.titleChanged.emit()
        t.statusMsg.emit(f"{len(self.fixes)} página(s) endireitada(s). Dá para desfazer (Ctrl+Z).")
        self.hide()


class TranslateBar(QFrame):
    """Documento em outro idioma: oferece traduzir (offline e gratuito)."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.setObjectName("TrBar")
        self.setStyleSheet("QFrame#TrBar{background:#f1ecfe; border:1px solid #7c3aed; border-radius:8px;}"
                           "QFrame#TrBar QLabel{color:#222; background:transparent;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        ic = QLabel("<span style='font-size:17px; color:#7c3aed'>文A</span>")
        self.text = QLabel()
        self.btn = QPushButton()
        self.btn.clicked.connect(lambda: self.tab.window().run_tool("translate"))
        close = QPushButton("×")
        close.setFlat(True)
        close.setFixedWidth(30)
        close.setStyleSheet("font-size:18px; color:#555; border:none;")
        close.clicked.connect(self.hide)
        for w in (ic, self.text, self.btn, close):
            lay.addWidget(w, 1 if w is self.text else 0)
        self.hide()

    def offer(self, src, dst):
        from . import traducao
        self.text.setText(f"Este documento está em <b>{traducao.NAMES.get(src, src)}</b>.")
        self.btn.setText(f"Traduzir para o {traducao.NAMES.get(dst, dst)}" if dst in ("pt", "es") else
                         f"Traduzir para {traducao.NAMES.get(dst, dst)}")
        self.show()


class PaymentsBar(QFrame):
    """Faixa com o boleto, Pix ou chave de NF-e encontrado: resumo, conferência e botão de copiar."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.items = []
        self.setObjectName("PayBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self._copy)
        self.all_btn = QPushButton()
        self.all_btn.clicked.connect(lambda: self.tab.window().run_tool("payments"))
        close = QPushButton("×")
        close.setFlat(True)
        close.setFixedWidth(30)
        close.setStyleSheet("font-size:18px; color:#555; border:none;")
        close.setToolTip("Fechar")
        close.clicked.connect(self.hide)
        for w in (self.icon, self.text, self.copy_btn, self.all_btn, close):
            lay.addWidget(w, 1 if w is self.text else 0)
        self.hide()

    def show_items(self, items):
        self.items = items
        if not items:
            self.hide()
            return
        main = next((i for i in items if not i.ok), items[0])
        bad = not main.ok
        bg, fg = ("#fde8e9", "#d7373f") if bad else ("#eef3fc", "#1473e6")
        self.setStyleSheet(f"QFrame#PayBar{{background:{bg}; border:1px solid {fg}; border-radius:8px;}}"
                           f"QFrame#PayBar QLabel{{color:#222; background:transparent;}}")
        self.icon.setText(f"<span style='font-size:18px; color:{fg}'>{'⚠' if bad else '▥'}</span>")
        html = f"<b>{main.title}</b>"
        if main.summary:
            html += " · " + main.summary
        if main.source == "texto e código":
            html += " · <span style='color:#2d9d78'>✔ confere com o código de barras</span>" if main.kind != "pix" \
                else " · <span style='color:#2d9d78'>✔ confere com o QR Code</span>"
        if bad:
            html += f"<br><span style='color:#b0262e'>{main.problem}</span>"
        self.text.setText(html)
        self.main = main
        self.copy_btn.setText(main.copy_label)
        self.copy_btn.setVisible(main.ok)
        n = len(items)
        self.all_btn.setText(f"Ver todos ({n})" if n > 1 else "Detalhes")
        self.show()

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.main.copy)
        self.tab.statusMsg.emit(self.main.copy_label.replace("Copiar", "Copiado:") + " – " + self.main.copy[:60])


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
    AUTOSAVE_MS = 8000   # salva sozinho 8 s depois da última alteração

    # "modified" dispara o salvamento automático: toda alteração passa por aqui
    @property
    def modified(self):
        return self._modified

    @modified.setter
    def modified(self, v):
        self._modified = bool(v)
        t = self.__dict__.get("_autosave_timer")
        if t is not None:
            if v and self.can_autosave():
                t.start(self.AUTOSAVE_MS)
            elif not v:
                t.stop()

    def __init__(self, data, path=None, password=None, settings=None):
        super().__init__()
        self.path = path
        self.password = password
        self.doc = ops.open_bytes(data, password)
        self.original_bytes = data  # arquivo como está em disco (usado para validar assinaturas)
        self.sig_results = []
        self.undo_stack, self.redo_stack = [], []
        self._modified = False
        self._backed_up = False        # versão anterior já guardada nesta sessão (o salvamento automático guarda só uma)
        self._autosave_error = False   # falhou (arquivo em uso / somente leitura): para até o próximo salvar manual
        self.has_signatures = self._detect_signatures()
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self.autosave)

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
        self.pay_bar = PaymentsBar(self)
        view_col.addWidget(self.pay_bar)
        self.orient_bar = OrientBar(self)
        view_col.addWidget(self.orient_bar)
        self.translate_bar = TranslateBar(self)
        view_col.addWidget(self.translate_bar)
        self.pay_items = None        # None = ainda não procurou
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
        self.scan_payments()
        self.check_orientation()
        self.check_language()

    # ------------------------------------------------------------ boletos, Pix e notas
    def scan_payments(self):
        """Procura boleto, Pix e chave de NF-e em segundo plano (no arquivo como foi aberto)."""
        self.pay_bar.hide()
        if not cfg.get("detect_payments"):
            return
        self._pay_thread = _track(_PayThread(self.original_bytes, self.password))
        self._pay_thread.done.connect(self._pay_done)
        self._pay_thread.start()

    def _pay_done(self, items):
        self.pay_items = items
        if cfg.get("detect_payments"):
            self.pay_bar.show_items(items)

    def check_orientation(self):
        """Procura páginas de lado / de cabeça para baixo em segundo plano e oferece endireitar."""
        self.orient_bar.hide()
        if not cfg.get("detect_orientation"):
            return
        self._orient_thread = _track(_OrientThread(self.original_bytes, self.password))
        self._orient_thread.done.connect(self._orient_done)
        self._orient_thread.start()

    def _orient_done(self, fixes):
        # só vale se ninguém mexeu na rotação dessas páginas enquanto procurava
        fixes = {p: r for p, r in fixes.items() if p < self.doc.page_count and self.doc[p].rotation != r}
        if cfg.get("detect_orientation"):
            self.orient_bar.show_fixes(fixes)

    def doc_language(self, pages=6):
        from . import traducao
        txt = " ".join(self.doc[p].get_text("text") for p in range(min(pages, self.doc.page_count)))
        return traducao.detect(txt[:20000])

    def check_language(self):
        self.translate_bar.hide()
        if not cfg.get("offer_translation"):
            return
        from . import traducao
        try:
            src = self.doc_language(3)
        except Exception:
            src = None
        dst = cfg.get("translate_to") or traducao.system_language()
        if src and src != dst:
            self.translate_bar.offer(src, dst)

    def goto_rect(self, page, rect=None):
        frac = 0.0
        if rect:
            h = self.doc[page].rect.height or 1
            frac = max(0.0, rect[1] / h - 0.08)
        self.view.goto(page, frac)

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
    def checkpoint(self, page=None, annot=None):
        """Ponto de desfazer. Rápido quando a alteração mexe só em comentários de uma página:
        page= (só acrescenta anotações) guarda quais já existiam; page= e annot= (mover, apagar, cor, nota)
        guarda só os objetos daquela anotação. A cópia do documento inteiro, lenta em PDFs grandes,
        fica para as demais alterações (e para o refazer)."""
        entry = None
        if page is not None:
            try:
                entry = ("objetos", page, self._annot_snapshot(page, annot)) if annot else \
                    ("anotacoes", page, {a.xref for a in self.doc[page].annots()})
            except Exception:
                entry = None
        self.undo_stack.append(entry if entry is not None else self.doc.tobytes())
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _annot_snapshot(self, page, xref):
        """Objetos de uma anotação (ela, o balão, as aparências) e a lista de anotações da página."""
        doc = self.doc
        pg = doc[page]
        objs = {}

        def take(x):
            if not x or x <= 0 or x in objs:
                return
            objs[x] = (doc.xref_object(x, compressed=False), doc.xref_stream(x) if doc.xref_is_stream(x) else None)

        take(xref)
        a = pg.load_annot(xref)
        popup = a.popup_xref if a else 0
        take(popup)
        for x in (xref, popup):
            if x:
                t, v = doc.xref_get_key(x, "AP/N")
                if t == "xref":
                    take(int(v.split()[0]))
        annots = doc.xref_get_key(pg.xref, "Annots")
        if annots[0] == "xref":
            take(int(annots[1].split()[0]))
        return objs, annots

    def _annot_restore(self, page, snap):
        objs, annots = snap
        doc = self.doc
        for x, (src, stream) in objs.items():
            doc.update_object(x, src)
            if stream is not None:
                doc.update_stream(x, stream)
        if annots[0] != "xref":
            doc.xref_set_key(doc[page].xref, "Annots", annots[1] if annots[0] != "null" else "null")

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
        self._autosave_timer.stop()
        for name in ("_pay_thread", "_orient_thread"):
            th = getattr(self, name, None)
            if th is not None and th.isRunning():
                th.requestInterruption()
                th.wait(5000)
        self.view.queue.clear()          # nada de desenhar páginas depois que o documento for fechado
        self.view._timer.stop()
        if self.pane:
            self.pane.cleanup()

    def undo(self):
        if not self.undo_stack:
            return
        top = self.undo_stack.pop()
        self.redo_stack.append(self.doc.tobytes())
        if isinstance(top, tuple):
            kind, page, data = top
            if kind == "objetos":
                self._annot_restore(page, data)
            else:
                pg = self.doc[page]
                for xref in [a.xref for a in pg.annots() if a.xref not in data]:
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
    def can_autosave(self):
        """Salvar sem perguntar: opção ligada, documento com arquivo, sem assinatura digital e sem falha anterior."""
        return bool(cfg.get("autosave") and self.path and not self.has_signatures and not self._autosave_error
                    and os.path.isdir(os.path.dirname(os.path.abspath(self.path))))

    def autosave(self):
        if not (self.modified and self.can_autosave()):
            return False
        from PySide6.QtWidgets import QApplication
        busy = QApplication.activeModalWidget() is not None or QApplication.mouseButtons() != Qt.NoButton \
            or getattr(self.view, "busy", False)
        if busy:   # no meio de um diálogo, arraste ou operação: tenta de novo daqui a pouco
            self._autosave_timer.start(3000)
            return False
        return self.save(auto=True)

    def save(self, path=None, auto=False):
        path = path or self.path
        if not path:
            return False if auto else self.save_as()
        if self.has_signatures and self.modified and not auto:
            r = QMessageBox.warning(self, "Documento assinado",
                                    "Este documento possui assinatura digital. Salvar as alterações invalidará "
                                    "a assinatura. Deseja continuar?", QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return False
        data = self.doc.tobytes(garbage=3, deflate=True)
        if not auto or not self._backed_up:
            try:
                from . import backups
                backups.backup(path)   # versão anterior guardada (Arquivo › Versões anteriores)
                self._backed_up = True
            except Exception:
                pass
        tmp = path + ".tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            if not auto:
                raise
            self._autosave_error = True
            self.statusMsg.emit("Não foi possível salvar automaticamente (o arquivo pode estar aberto em outro programa "
                                "ou ser somente leitura). Use Salvar ou Salvar como.")
            return False
        self.original_bytes = data
        self.path = path
        self._autosave_error = False
        self.modified = False
        self.titleChanged.emit()
        if auto:
            from datetime import datetime
            self.statusMsg.emit(f"Salvo automaticamente às {datetime.now():%H:%M}")
        else:
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
            try:
                pages = ops.parse_ranges(txt, self.doc.page_count)
            except ValueError:
                QMessageBox.warning(self, "Lumen PDF", f"Intervalo de páginas inválido: “{txt}”.\n\nUse, por exemplo: 1-3, 7")
                return
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
