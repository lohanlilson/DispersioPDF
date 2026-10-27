"""Telas: pesquisar artigos científicos e ler/salvar a tradução de um documento."""
from __future__ import annotations

import html
import os

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFrame, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QComboBox, QSpinBox,
                               QCheckBox, QListWidget, QListWidgetItem, QTextBrowser, QApplication, QMessageBox,
                               QProgressDialog, QFileDialog, QButtonGroup, QRadioButton, QWidget)

from . import artigos, traducao
from .config import cfg


class _Job(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)
    item = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self._cancel = False

    @property
    def cancel(self):
        return self._cancel or self.isInterruptionRequested()

    @cancel.setter
    def cancel(self, v):
        self._cancel = v

    def run(self):
        try:
            self.done.emit(self.fn(self))
        except Exception as e:
            self.failed.emit(str(e))


def _looks_english(q):
    w = q.lower().split()
    en = {"the", "of", "and", "in", "on", "for", "with", "to", "a", "an", "dog", "dogs", "cat", "cats", "animal", "animals",
          "cruelty", "abuse", "study", "review", "disease", "treatment", "children", "health"}
    pt = {"de", "da", "do", "das", "dos", "e", "em", "para", "com", "maus", "tratos", "cães", "gatos", "saúde", "doença"}
    return sum(x in en for x in w) > sum(x in pt for x in w) or (not any(c in q for c in "ãõçáéíóúâêô") and sum(x in pt for x in w) == 0
                                                                 and any(x in en for x in w))


def _keep(owner, job):
    from .doctab import _track     # parado com segurança se o programa fechar no meio
    owner._jobs = [j for j in getattr(owner, "_jobs", []) if j.isRunning()] + [job]
    return _track(job)


# ------------------------------------------------------------------ pacotes de idioma
def ensure_models(parent, path):
    """Baixa os pacotes de tradução que faltam (pergunta antes). True se tudo pronto."""
    miss = traducao.missing(path)
    if not miss:
        return True
    names = ", ".join(f"{traducao.NAMES.get(a, a)} → {traducao.NAMES.get(b, b)}" for a, b in miss)
    if QMessageBox.question(parent, "Tradução", f"Para traduzir sem internet, o Dispersio PDF precisa baixar uma vez o pacote "
                            f"de idioma ({names}), cerca de {65 * len(miss)} MB.\n\nBaixar agora?") != QMessageBox.Yes:
        return False
    for pair in miss:
        dlg = QProgressDialog(f"Baixando pacote {traducao.NAMES.get(pair[0])} → {traducao.NAMES.get(pair[1])}…",
                              "Cancelar", 0, 100, parent)
        dlg.setWindowTitle("Tradução")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        job = _keep(parent, _Job(lambda j, p=pair: traducao.download(p, lambda a, b: j.progress.emit(a, b),
                                                                     lambda: j.cancel)))
        job.progress.connect(lambda a, b: (dlg.setMaximum(max(b, 1)), dlg.setValue(min(a, max(b, 1)))))
        dlg.canceled.connect(lambda: setattr(job, "cancel", True))
        res = {}
        job.done.connect(lambda r: (res.setdefault("ok", r), dlg.close()))
        job.failed.connect(lambda e: (res.setdefault("err", e), dlg.close()))
        job.start()
        dlg.exec()
        job.wait()
        if "err" in res or job.cancel:
            if not job.cancel:
                QMessageBox.warning(parent, "Tradução", f"Não foi possível baixar o pacote de idioma:\n{res.get('err')}")
            return False
    return True


def route_or_warn(parent, src, dst):
    try:
        path = traducao.route(src, dst)
    except Exception:
        path = None
    if path is None:
        QMessageBox.information(parent, "Tradução", f"Ainda não há tradução gratuita de {traducao.NAMES.get(src, src)} "
                                f"para {traducao.NAMES.get(dst, dst)}.")
    return path


# ------------------------------------------------------------------ pesquisa de artigos
class ArticleCard(QFrame):
    """Um resultado: título, autores, revista, selos; resumo (traduzido) e ações para navegar."""

    def __init__(self, dlg, a):
        super().__init__()
        self.dlg, self.a = dlg, a
        self.setObjectName("ArtCard")
        self.setStyleSheet("QFrame#ArtCard{border:1px solid palette(mid); border-radius:10px;}"
                           "QLabel#Badge{border-radius:8px; padding:1px 7px; font-size:11px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)
        t = QLabel(f"<b style='font-size:14px'>{html.escape(a.title)}</b>")
        t.setWordWrap(True)
        t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(t)
        meta = " · ".join(x for x in [a.authors_short, a.venue, str(a.year or "")] if x)
        m = QLabel(html.escape(meta))
        m.setWordWrap(True)
        m.setObjectName("Muted")
        lay.addWidget(m)
        badges = QHBoxLayout()
        badges.setSpacing(6)
        def badge(text, bg, fg):
            b = QLabel(text)
            b.setObjectName("Badge")
            b.setStyleSheet(f"background:{bg}; color:{fg};")
            badges.addWidget(b)
        if a.has_pdf:
            badge("PDF grátis", "#e7f6ee", "#1f7a5a")
        else:
            badge("sem PDF gratuito", "#fde8e9", "#b0262e")
        if a.language:
            badge(traducao.NAMES.get(a.language, a.language), "#eef3fc", "#1d5fbf")
        if a.kind == "review":
            badge("revisão", "#fff6dd", "#8a6100")
        elif a.kind == "preprint":
            badge("preprint (sem revisão por pares)", "#fff6dd", "#8a6100")
        if a.citations:
            badge(f"{a.citations} citações", "#f1ecfe", "#5b2bb5")
        badges.addStretch()
        lay.addLayout(badges)
        self.abs = QLabel()
        self.abs.setWordWrap(True)
        self.abs.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.abs.hide()
        lay.addWidget(self.abs)
        row = QHBoxLayout()
        row.setSpacing(6)
        def btn(text, fn, enabled=True, tip=""):
            b = QPushButton(text)
            b.setEnabled(enabled)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
            return b
        btn("Abrir PDF", lambda: dlg.open_article(a), a.has_pdf, "" if a.has_pdf else "A revista não oferece PDF gratuito")
        self.abs_btn = btn("Resumo", self.toggle_abstract, bool(a.abstract), "" if a.abstract else "Sem resumo na base")
        if a.id:
            btn("Parecidos", lambda: dlg.navigate("related", a), bool(a.related))
            btn(f"Citado por ({a.citations or 0})", lambda: dlg.navigate("citing", a), bool(a.citations))
            btn(f"Referências ({len(a.refs)})", lambda: dlg.navigate("refs", a), bool(a.refs))
        row.addStretch()
        btn("ABNT", lambda: dlg.copy_ref(a), tip="Copiar a referência no padrão ABNT")
        btn("Página", lambda: QDesktopServices.openUrl(QUrl(a.page_url or (a.pdf_urls[0] if a.pdf_urls else a.doi))),
            bool(a.page_url or a.pdf_urls or a.doi))
        lay.addLayout(row)
        self._translated = None

    def toggle_abstract(self):
        if self.abs.isVisible():
            self.abs.hide()
            self.abs_btn.setText("Resumo")
            return
        self.abs_btn.setText("Fechar resumo")
        self.abs.show()
        dst = cfg.get("translate_to") or traducao.system_language()
        src = self.a.language or traducao.detect(self.a.abstract) or "en"
        if self._translated:
            self._show(self._translated, True)
            return
        self._show(self.a.abstract, False)
        if src == dst:
            return
        try:
            path = traducao.route(src, dst)
        except Exception:
            path = None
        if not path or (traducao.missing(path) and not ensure_models(self.dlg, path)):
            return
        self.abs.setText(f"<i>Traduzindo o resumo…</i><br>{html.escape(self.a.abstract)}")
        job = _keep(self.dlg, _Job(lambda j: traducao.translate_paragraphs([self.a.abstract], path, dst)[0]))
        job.done.connect(lambda t: (setattr(self, "_translated", t), self._show(t, True)))
        job.failed.connect(lambda e: self._show(self.a.abstract, False))
        job.start()

    def _show(self, text, translated):
        head = "<b>Resumo (tradução automática)</b>" if translated else "<b>Resumo</b>"
        self.abs.setText(f"{head}<br>{html.escape(text)}")


class ArticlesDialog(QDialog):
    """Pesquisa de artigos: sugestões enquanto digita, filtros em botões, resumo traduzido, navegar entre artigos
    (parecidos, quem citou, referências), rolagem contínua e DOI/link colado."""

    def __init__(self, win, query=""):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Pesquisar artigos científicos")
        self.resize(980, 760)
        self.results, self.page, self.total, self.loading = [], 1, 0, False
        self.stack = []                 # navegação (parecidos / citado por / referências) para "Voltar"
        self.mode = ("search", None)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText("Pesquise um tema, cole um DOI ou link de artigo…  ex.: maus-tratos animais medicina veterinária")
        self.q.returnPressed.connect(self.search)
        go = QPushButton("Pesquisar")
        go.setDefault(True)
        go.clicked.connect(self.search)
        row.addWidget(self.q, 1)
        row.addWidget(go)
        self.from_doc = QPushButton("Sobre o documento aberto")
        self.from_doc.setToolTip("Usa o título e os termos principais do PDF aberto para achar artigos relacionados")
        self.from_doc.clicked.connect(self.search_open_document)
        row.addWidget(self.from_doc)
        root.addLayout(row)
        # sugestões
        from PySide6.QtWidgets import QCompleter
        from PySide6.QtCore import QStringListModel, QTimer
        self._sugg_model = QStringListModel()
        self._sugg_map = {}
        self.completer = QCompleter(self._sugg_model, self)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.activated.connect(self._suggestion_chosen)
        self.q.setCompleter(self.completer)
        self._sugg_timer = QTimer(self)
        self._sugg_timer.setSingleShot(True)
        self._sugg_timer.timeout.connect(self._suggest)
        self.q.textEdited.connect(lambda _: self._sugg_timer.start(450))
        # filtros em botões
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chips = {}
        on = set(cfg.get("articles_filters").split(",")) if cfg.get("articles_filters") else {"pdf"}
        for k, (label, *_r) in artigos.FILTERS.items():
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(k in on)
            b.setObjectName("Chip")
            b.toggled.connect(lambda _=False: self._refilter())
            chips.addWidget(b)
            self.chips[k] = b
        chips.addSpacing(10)
        self.sorts = QButtonGroup(self)
        for k, (label, key) in enumerate([("Relevância", "relevance"), ("Mais citados", "citations"), ("Recentes", "recent")]):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setObjectName("Chip")
            b.setProperty("key", key)
            b.setChecked(k == 0)
            self.sorts.addButton(b, k)
            chips.addWidget(b)
        self.sorts.idClicked.connect(lambda _: self._refilter())
        chips.addSpacing(10)
        self.en = QCheckBox("Também em inglês")
        self.en.setToolTip("Traduz a pesquisa para o inglês (sem internet) e junta os resultados.")
        self.en.setChecked(cfg.get("articles_english"))
        chips.addWidget(self.en)
        chips.addStretch()
        root.addLayout(chips)
        self.setStyleSheet("QPushButton#Chip{border:1px solid palette(mid); border-radius:13px; padding:3px 11px;}"
                           "QPushButton#Chip:checked{background:#7c3aed; color:white; border-color:#7c3aed;}")
        nav = QHBoxLayout()
        self.back = QPushButton("← Voltar")
        self.back.clicked.connect(self.go_back)
        self.back.hide()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        nav.addWidget(self.back)
        nav.addWidget(self.status, 1)
        root.addLayout(nav)
        from PySide6.QtWidgets import QScrollArea
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.inner = QWidget()
        self.col = QVBoxLayout(self.inner)
        self.col.setSpacing(10)
        self.col.addStretch()
        self.area.setWidget(self.inner)
        self.area.verticalScrollBar().valueChanged.connect(self._maybe_more)
        root.addWidget(self.area, 1)
        self._sync_from_doc()
        if query:
            self.q.setText(query)
            QTimer.singleShot(0, self.search)

    # ---------------------------------------------------------------- estado
    def filters(self):
        return tuple(k for k, b in self.chips.items() if b.isChecked())

    def sort(self):
        b = self.sorts.checkedButton()
        return b.property("key") if b else "relevance"

    def _sync_from_doc(self):
        t = self.win.cur() if hasattr(self.win, "cur") else None
        self.from_doc.setEnabled(t is not None)

    def _clear(self):
        while self.col.count() > 1:
            w = self.col.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.results = []

    def _add(self, arts):
        for a in arts:
            self.results.append(a)
            self.col.insertWidget(self.col.count() - 1, ArticleCard(self, a))

    # ---------------------------------------------------------------- sugestões
    def _suggest(self):
        text = self.q.text().strip()
        if len(text) < 3 or artigos.parse_link(text):
            return
        queries = [text]
        try:
            path = traducao.route("pt", "en") if not _looks_english(text) else None
            if path and not traducao.missing(path):
                en = traducao.translate_paragraphs([artigos.restore_accents(text)], path, "en")[0].strip().rstrip(".")
                if en.lower() != text.lower():
                    queries.append(en)
        except Exception:
            pass

        def work(j):
            out = []
            for qq in queries:
                out += artigos.autocomplete(qq)
            return out
        job = _keep(self, _Job(work))
        job.done.connect(lambda res, t=text: self._show_suggestions(res, t))
        job.start()

    def _show_suggestions(self, res, typed):
        if self.q.text().strip() != typed:
            return
        labels, self._sugg_map = [], {}
        for kind, label, hint, ident in res:
            show = f"🔎 {label}" if kind == "tema" else f"📄 {label}"
            if show not in self._sugg_map:
                self._sugg_map[show] = (kind, label, ident)
                labels.append(show)
        hist = [h for h in (cfg.qs.value("articles_history", []) or []) if typed.lower() in str(h).lower()][:3]
        for h in hist:
            show = f"🕘 {h}"
            if show not in self._sugg_map:
                self._sugg_map[show] = ("hist", h, None)
                labels.insert(0, show)
        self._sugg_model.setStringList(labels)
        if labels:
            self.completer.complete()

    def _suggestion_chosen(self, text):
        kind, label, ident = self._sugg_map.get(text, ("hist", text, None))
        from PySide6.QtCore import QTimer
        if kind == "artigo" and ident:
            QTimer.singleShot(0, lambda: (self.q.setText(label), self._open_key(ident)))
        else:
            QTimer.singleShot(0, lambda: (self.q.setText(label), self.search()))

    # ---------------------------------------------------------------- pesquisa
    def _remember(self, q):
        h = [x for x in (cfg.qs.value("articles_history", []) or []) if x != q]
        cfg.qs.setValue("articles_history", ([q] + h)[:30])

    def _refilter(self):
        cfg.set("articles_filters", ",".join(self.filters()))
        if self.mode[0] == "search" and self.q.text().strip():
            self.search()
        elif self.mode[0] == "citing":
            self.navigate("citing", self.mode[1], push=False)

    def search(self, more=False):
        q = self.q.text().strip()
        if not q:
            return
        key = artigos.parse_link(q)
        if key and not more:
            return self._open_key(key)
        cfg.set("articles_english", self.en.isChecked())
        if not more:
            self.stack.clear()
            self.back.hide()
            self.mode = ("search", q)
            self._remember(q)
            self.page, self.total = 1, 0
            self._clear()
        else:
            self.page += 1
        queries = artigos.variants(q)
        if self.en.isChecked() and not _looks_english(q):
            path = None
            try:
                path = traducao.route("pt", "en")
            except Exception:
                pass
            if path and (not traducao.missing(path) or ensure_models(self, path)):
                try:
                    en = traducao.translate_paragraphs([artigos.restore_accents(q)], path, "en")[0].strip().rstrip(".")
                    if en and en.lower() not in [x.lower() for x in queries]:
                        queries.append(en)
                except Exception:
                    pass
        yf, sort, key, page, flt = None, self.sort(), cfg.get("openalex_key"), self.page, self.filters()
        seen = {artigos.norm_key(a) for a in self.results}
        en = [x for x in queries if _looks_english(x) and x != q]
        self.status.setText("Pesquisando" + (f" também em inglês (“{en[-1]}”)" if en else "") + "…")
        self._run(lambda j: artigos.search_many(queries, yf, sort, page, key, seen, flt), more)

    def _run(self, fn, more):
        self.loading = True
        job = _keep(self, _Job(fn))
        job.done.connect(lambda res: self._shown(res, more))
        job.failed.connect(self._failed)
        job.start()

    def _failed(self, e):
        self.loading = False
        self.status.setText(f"<span style='color:#d7373f'>{html.escape(e)}</span>")

    def _shown(self, res, more=False):
        self.loading = False
        arts, total = res
        self.total = max(self.total, total) if more else total
        self._add(arts)
        what = {"search": "resultado(s)", "related": "artigo(s) parecido(s)", "citing": "artigo(s) que citam",
                "refs": "referência(s)", "one": "artigo"}[self.mode[0]]
        extra = ""
        if self.mode[0] in ("related", "citing", "refs"):
            extra = f" — “{html.escape(self.mode[1].title[:80])}”"
        src = {a.source for a in self.results}
        self.status.setText(f"{len(self.results)} {what}{extra}" + (f" de {self.total}" if self.total > len(self.results) else "")
                            + (" · fonte: " + ", ".join(sorted(src)) if src else "")
                            + (". Nada encontrado: tente outras palavras, desligue algum filtro ou marque “Também em inglês”."
                               if not self.results else ""))
        if not more:
            self.area.verticalScrollBar().setValue(0)

    def _maybe_more(self, v):
        sb = self.area.verticalScrollBar()
        if self.loading or v < sb.maximum() - 200 or len(self.results) >= self.total:
            return
        if self.mode[0] == "search":
            self.search(more=True)
        elif self.mode[0] == "citing":
            self.page += 1
            a, page, flt, key = self.mode[1], self.page, self.filters(), cfg.get("openalex_key")
            self._run(lambda j: artigos.citing(a.id, page, key, flt, self.sort()), True)

    def _open_key(self, key):
        self.mode = ("one", None)
        self.stack.clear()
        self.back.hide()
        self._clear()
        self.status.setText("Buscando o artigo…")
        self._run(lambda j: ([artigos.by_key(key, cfg.get("openalex_key"))], 1), False)

    # ---------------------------------------------------------------- navegar entre artigos
    def navigate(self, kind, a, push=True):
        if push:
            self.stack.append((self.mode, list(self.results), self.total, self.page, self.area.verticalScrollBar().value()))
        self.back.show()
        self.mode = (kind, a)
        self.page, self.total = 1, 0
        self._clear()
        key, flt = cfg.get("openalex_key"), tuple(k for k in self.filters() if k != "pdf")
        self.status.setText({"related": "Buscando artigos parecidos…", "citing": "Buscando quem citou…",
                             "refs": "Buscando as referências…"}[kind])
        if kind == "related":
            self._run(lambda j: (artigos.by_ids(a.related, key), len(a.related)), False)
        elif kind == "refs":
            self._run(lambda j: (artigos.by_ids(a.refs, key), len(a.refs)), False)
        else:
            self._run(lambda j: artigos.citing(a.id, 1, key, flt, self.sort()), False)

    def go_back(self):
        if not self.stack:
            return
        mode, results, total, page, pos = self.stack.pop()
        self.mode, self.total, self.page = mode, total, page
        self._clear()
        self._add(results)
        self.back.setVisible(bool(self.stack))
        self.status.setText(f"{len(results)} resultado(s)")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.area.verticalScrollBar().setValue(pos))

    def search_open_document(self):
        t = self.win.cur()
        if t is None:
            return
        q = artigos.query_from_document(t.doc)
        if not q:
            self.status.setText("Não consegui tirar um tema deste documento (é uma imagem? use o OCR antes).")
            return
        if traducao.detect(" ".join(t.doc[p].get_text() for p in range(min(2, t.doc.page_count)))) != "en":
            self.en.setChecked(True)
        self.q.setText(q)
        self.search()

    # ---------------------------------------------------------------- ações
    def copy_ref(self, a):
        QApplication.clipboard().setText(a.abnt())
        self.status.setText("Referência ABNT copiada.")

    def open_article(self, a):
        dlg = QProgressDialog("Baixando o artigo…", "Cancelar", 0, 0, self)
        dlg.setWindowTitle("Artigos")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        job = _keep(self, _Job(lambda j: artigos.download(a, None, lambda x, y: j.progress.emit(x, y), lambda: j.cancel)))
        job.progress.connect(lambda x, y: (dlg.setMaximum(y if y > 0 else 0), dlg.setValue(x if y > 0 else 0)))
        dlg.canceled.connect(lambda: setattr(job, "cancel", True))

        def done(fn):
            dlg.close()
            if fn:
                self.win.open_path(fn)
                self.win.statusBar().showMessage(f"Artigo salvo em {fn}", 8000)
                self.accept()
            elif not job.cancel:
                if QMessageBox.question(self, "Artigos", "A revista não liberou o PDF para download direto (às vezes ela "
                                        "pede uma confirmação no navegador).\n\nAbrir o artigo no navegador?") == QMessageBox.Yes:
                    QDesktopServices.openUrl(QUrl(a.pdf_urls[0]))
        job.done.connect(done)
        job.failed.connect(lambda e: (dlg.close(), QMessageBox.warning(self, "Artigos", e)))
        job.start()

    # compatibilidade (testes e atalhos antigos)
    def current(self):
        return self.results[0] if self.results else None

    def open_selected(self):
        if self.results:
            self.open_article(self.results[0])


# ------------------------------------------------------------------ leitura traduzida
class TranslateWindow(QDialog):
    """Tela de leitura da tradução do documento: só a tradução, o original, lado a lado ou intercalado (bilíngue).
    Mostra as páginas conforme ficam prontas. Referências, cabeçalhos e números de página ficam no original."""

    MODES = ("Tradução", "Original", "Lado a lado", "Intercalado")

    def __init__(self, win, tab):
        super().__init__(win)
        self.tab = tab
        self.setWindowTitle(f"Leitura traduzida — {tab.title().lstrip('● ')}")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1000, 760)
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.info = QLabel()
        top.addWidget(self.info, 1)
        self.mode = QButtonGroup(self)
        for k, label in enumerate(self.MODES):
            r = QRadioButton(label)
            r.setChecked(k == cfg.get("reading_mode"))
            self.mode.addButton(r, k)
            top.addWidget(r)
        self.mode.idToggled.connect(lambda i, on: on and (cfg.set("reading_mode", i), self.render()))
        root.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        root.addWidget(self.view, 1)
        note = QLabel("Tradução automática gratuita e sem internet: boa para entender; confira trechos importantes no original. "
                      "Citações, referências e números ficam como no original.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)
        tab.trUpdated.connect(self.render)
        self.render()

    def render(self):
        from . import traducao
        tr = self.tab.tr or {}
        pages = tr.get("pages", {})
        name = traducao.NAMES.get(tr.get("dst"), tr.get("dst"))
        self.info.setText((f"Traduzindo para o {name}… {len(pages)} de {tr.get('total')} página(s)" if tr.get("running")
                           else f"Traduzido para o {name} — {len(pages)} página(s)."))
        mode = self.mode.checkedId()
        sb = self.view.verticalScrollBar()
        pos = sb.value()
        esc = html.escape
        out = ["<style>p{margin:0 0 10px 0; line-height:135%} h3{color:#7c3aed; margin-top:18px}"
               " td{vertical-align:top; padding:0 12px 8px 0} .o{color:#777} .k{color:#888; font-size:small}"
               " .t{font-weight:600}</style>"]
        for p in sorted(pages):
            out.append(f"<h3>Página {p + 1}</h3>")
            items = [(b, t) for b, t in pages[p] if not (b.keep and b.why in ("cabeçalho/rodapé", "número da página"))]
            if mode == 2:
                out.append("<table width='100%'>")
            for b, t in items:
                o = b.shown
                t = o if t is None else t
                cls = " class='t'" if (b.bold or b.size >= 13) else ""
                if b.keep:
                    if mode == 2:
                        out.append(f"<tr><td colspan='2' class='k'>{esc(o)}</td></tr>")
                    else:
                        out.append(f"<p class='k'>{esc(o)}</p>")
                elif mode == 0:
                    out.append(f"<p{cls}>{esc(t)}</p>")
                elif mode == 1:
                    out.append(f"<p{cls}>{esc(o)}</p>")
                elif mode == 2:
                    out.append(f"<tr><td width='50%' class='o'>{esc(o)}</td><td width='50%'>{esc(t)}</td></tr>")
                else:
                    out.append(f"<p{cls}>{esc(t)}</p><p class='o' style='margin-top:-6px'>{esc(o)}</p>")
            if mode == 2:
                out.append("</table>")
        self.view.setHtml("".join(out))
        sb.setValue(pos)


class SelectionTranslation(QDialog):
    """Balão com a tradução do trecho selecionado."""

    def __init__(self, win, text, src, dst):
        super().__init__(win, Qt.Tool)
        self.setWindowTitle(f"Tradução ({traducao.NAMES.get(src, src)} → {traducao.NAMES.get(dst, dst)})")
        self.resize(460, 260)
        from PySide6.QtGui import QCursor
        self.move(QCursor.pos() + __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(12, 12))
        lay = QVBoxLayout(self)
        self.out = QTextBrowser()
        self.out.setPlainText("Traduzindo…")
        lay.addWidget(self.out, 1)
        row = QHBoxLayout()
        orig = QLabel(html.escape(text[:160]) + ("…" if len(text) > 160 else ""))
        orig.setObjectName("Muted")
        orig.setWordWrap(True)
        row.addWidget(orig, 1)
        cp = QPushButton("Copiar")
        cp.clicked.connect(lambda: QApplication.clipboard().setText(self.out.toPlainText()))
        row.addWidget(cp)
        lay.addLayout(row)
        try:
            path = traducao.route(src, dst)
        except Exception:
            path = None
        if path is None:
            self.out.setPlainText(f"Sem tradução gratuita de {traducao.NAMES.get(src, src)} para {traducao.NAMES.get(dst, dst)}.")
            return
        if traducao.missing(path) and not ensure_models(win, path):
            self.out.setPlainText("É preciso baixar o pacote de idioma para traduzir.")
            return
        flat = " ".join(text.split())
        job = _keep(self, _Job(lambda j: traducao.translate_paragraphs([flat], path, dst)[0]))
        job.done.connect(self.out.setPlainText)
        job.failed.connect(lambda e: self.out.setPlainText(f"Não foi possível traduzir: {e}"))
        job.start()
