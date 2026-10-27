"""Telas: pesquisar artigos científicos e ler/salvar a tradução de um documento."""
from __future__ import annotations

import html
import os

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QComboBox, QSpinBox,
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
    if QMessageBox.question(parent, "Tradução", f"Para traduzir sem internet, o Lumen PDF precisa baixar uma vez o pacote "
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
class ArticlesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Pesquisar artigos científicos")
        self.resize(900, 680)
        self.results, self.page, self.total, self.last = [], 1, 0, None
        root = QVBoxLayout(self)
        intro = QLabel("Artigos de acesso aberto (PDF gratuito e legal) de revistas e repositórios do mundo todo, "
                       "pela base OpenAlex. Os em outro idioma podem ser traduzidos ao abrir.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)
        row = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText("Ex.: maus-tratos animais medicina veterinária legal")
        self.q.returnPressed.connect(self.search)
        go = QPushButton("Pesquisar")
        go.setDefault(True)
        go.clicked.connect(self.search)
        row.addWidget(self.q, 1)
        row.addWidget(go)
        root.addLayout(row)
        opts = QHBoxLayout()
        self.en = QCheckBox("Procurar também em inglês")
        self.en.setToolTip("Traduz a pesquisa para o inglês (sem internet) e junta os resultados: a maior parte dos artigos está em inglês.")
        self.en.setChecked(cfg.get("articles_english"))
        opts.addWidget(self.en)
        opts.addSpacing(16)
        opts.addWidget(QLabel("A partir de:"))
        self.year = QSpinBox()
        self.year.setRange(0, 2100)
        self.year.setSpecialValueText("qualquer ano")
        self.year.setValue(0)
        opts.addWidget(self.year)
        opts.addSpacing(16)
        opts.addWidget(QLabel("Ordenar:"))
        self.sort = QComboBox()
        for label, k in [("Mais relevantes", "relevance"), ("Mais citados", "citations"), ("Mais recentes", "recent")]:
            self.sort.addItem(label, k)
        opts.addWidget(self.sort)
        opts.addStretch()
        root.addLayout(opts)
        self.status = QLabel("")
        root.addWidget(self.status)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(True)
        self.list.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.list.currentRowChanged.connect(lambda _: self._sync())
        root.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.more = QPushButton("Carregar mais")
        self.more.clicked.connect(lambda: self.search(more=True))
        self.b_open = QPushButton("Baixar e abrir")
        self.b_open.clicked.connect(self.open_selected)
        self.b_web = QPushButton("Abrir página do artigo")
        self.b_web.clicked.connect(self.open_web)
        self.b_ref = QPushButton("Copiar referência (ABNT)")
        self.b_ref.clicked.connect(self.copy_ref)
        for b in (self.more, self.b_ref, self.b_web, self.b_open):
            btns.addWidget(b)
        btns.insertStretch(1)
        root.addLayout(btns)
        self._sync()

    def _sync(self):
        has = self.current() is not None
        for b in (self.b_open, self.b_web, self.b_ref):
            b.setEnabled(has)
        self.more.setVisible(bool(self.results) and len(self.results) < self.total)

    def current(self):
        i = self.list.currentRow()
        return self.results[i] if 0 <= i < len(self.results) else None

    def search(self, more=False):
        q = self.q.text().strip()
        if not q:
            return
        cfg.set("articles_english", self.en.isChecked())
        if not more:
            self.page, self.results, self.total = 1, [], 0
            self.list.clear()
        else:
            self.page += 1
        queries = [q]
        if self.en.isChecked() and not _looks_english(q):
            path = None
            try:
                path = traducao.route("pt", "en")
            except Exception:
                pass
            if path and (not traducao.missing(path) or ensure_models(self, path)):
                try:
                    en = traducao.translate_paragraphs([q], path, "en")[0]
                    if en.lower() != q.lower():
                        queries.append(en)
                except Exception:
                    pass
        yf = self.year.value() or None
        sort = self.sort.currentData()
        key = cfg.get("openalex_key")
        page = self.page
        self.status.setText("Pesquisando" + (f" (“{queries[-1]}”)" if len(queries) > 1 else "") + "…")

        def work(j):
            seen, out, total = {a.doi or a.title for a in self.results}, [], 0
            for qq in queries:
                arts, n = artigos.search(qq, yf, sort, page, key)
                total += n
                for a in arts:
                    k = a.doi or a.title
                    if k not in seen:
                        seen.add(k)
                        out.append(a)
            return out, total
        job = _keep(self, _Job(work))
        job.done.connect(self._shown)
        job.failed.connect(lambda e: self.status.setText(f"<span style='color:#d7373f'>{html.escape(e)}</span>"))
        job.start()

    def _shown(self, res):
        arts, total = res
        self.total = max(self.total, total)
        for a in arts:
            self.results.append(a)
            lang = traducao.NAMES.get(a.language, a.language or "?")
            meta = " · ".join(x for x in [a.authors_short, a.venue, str(a.year or ""),
                                          f"{a.citations} citações" if a.citations is not None else "",
                                          f"idioma: {lang}"] if x)
            it = QListWidgetItem(f"{a.title}\n{meta}")
            it.setToolTip(a.abnt())
            self.list.addItem(it)
        src = {a.source for a in self.results}
        self.status.setText(f"{len(self.results)} de {self.total} resultado(s) com PDF gratuito"
                            + (" — fonte: " + ", ".join(sorted(src)) if src else "")
                            + (". Nada encontrado; tente outras palavras ou marque “Procurar também em inglês”." if not self.results else ""))
        if self.list.currentRow() < 0 and self.results:
            self.list.setCurrentRow(0)
        self._sync()

    def open_web(self):
        a = self.current()
        if a:
            QDesktopServices.openUrl(QUrl(a.page_url or a.pdf_urls[0]))

    def copy_ref(self):
        a = self.current()
        if a:
            QApplication.clipboard().setText(a.abnt())
            self.status.setText("Referência ABNT copiada.")

    def open_selected(self):
        a = self.current()
        if not a:
            return
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
                self.win._article_lang = a.language
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


# ------------------------------------------------------------------ leitura traduzida
class TranslateWindow(QDialog):
    """Lê o documento traduzido (offline), página por página, com o original ao lado se quiser."""

    def __init__(self, win, tab, src, dst, path):
        super().__init__(win)
        self.win, self.tab, self.src, self.dst, self.path = win, tab, src, dst, path
        self.setWindowTitle(f"Tradução — {tab.title().lstrip('● ')}")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1000, 760)
        self.pages = {}       # página -> [(rect, original, tradução, tamanho)]
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.info = QLabel()
        top.addWidget(self.info, 1)
        self.mode = QButtonGroup(self)
        for k, label in enumerate(("Tradução", "Original", "Lado a lado")):
            r = QRadioButton(label)
            r.setChecked(k == 0)
            self.mode.addButton(r, k)
            top.addWidget(r)
        self.mode.idToggled.connect(lambda *_: self.render())
        root.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        root.addWidget(self.view, 1)
        bot = QHBoxLayout()
        note = QLabel("Tradução automática gratuita e sem internet: boa para entender; confira trechos importantes no original.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        bot.addWidget(note, 1)
        self.save_btn = QPushButton("Salvar PDF traduzido…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_pdf)
        bot.addWidget(self.save_btn)
        root.addLayout(bot)
        self.n = tab.doc.page_count
        self._start()

    def _start(self):
        data, pwd = self.tab.doc.tobytes(), self.tab.password

        def work(j):
            import pymupdf
            d = pymupdf.open("pdf", data)
            if d.needs_pass and pwd:
                d.authenticate(pwd)
            for p in range(d.page_count):
                if j.cancel:
                    break
                blocks = traducao.page_paragraphs(d[p])
                tr = traducao.translate_paragraphs([b[1] for b in blocks], self.path, self.dst)
                j.item.emit((p, d.page_count, [(r, o, t, s, b) for (r, o, s, b), t in zip(blocks, tr)]))
            return True
        self.job = _keep(self, _Job(work))
        self.job.item.connect(self._page)
        self.job.done.connect(lambda _: self._finished())
        self.job.failed.connect(lambda e: self.info.setText(f"<span style='color:#d7373f'>Erro na tradução: {html.escape(e)}</span>"))
        self.info.setText(f"Traduzindo do {traducao.NAMES.get(self.src)} para o {traducao.NAMES.get(self.dst)}… página 1 de {self.n}")
        self.job.start()

    def _page(self, res):
        pg, n, blocks = res
        self.pages[pg] = blocks
        self.info.setText(f"Traduzindo do {traducao.NAMES.get(self.src)} para o {traducao.NAMES.get(self.dst)}… "
                          f"página {min(pg + 2, n)} de {n}")
        self.render()

    def _finished(self):
        self.info.setText(f"Traduzido do {traducao.NAMES.get(self.src)} para o {traducao.NAMES.get(self.dst)} — {len(self.pages)} página(s).")
        self.save_btn.setEnabled(bool(self.pages))

    def render(self):
        mode = self.mode.checkedId()
        sb = self.view.verticalScrollBar()
        pos = sb.value()
        out = ["<style>p{margin:0 0 10px 0; line-height:135%} h3{color:#7c3aed; margin-top:18px}"
               " td{vertical-align:top; padding:0 10px 8px 0}</style>"]
        for p in sorted(self.pages):
            out.append(f"<h3>Página {p + 1}</h3>")
            if mode == 2:
                out.append("<table width='100%'>")
                for _r, o, t, s, _b in self.pages[p]:
                    out.append(f"<tr><td width='50%' style='color:#666'>{html.escape(o)}</td><td width='50%'>{html.escape(t)}</td></tr>")
                out.append("</table>")
            else:
                for _r, o, t, s, b in self.pages[p]:
                    txt = o if mode == 1 else t
                    style = " style='font-weight:600; font-size:large'" if s >= 13 else (" style='font-weight:600'" if b else "")
                    out.append(f"<p{style}>{html.escape(txt)}</p>")
        self.view.setHtml("".join(out))
        sb.setValue(pos)

    def save_pdf(self):
        base = os.path.splitext(self.tab.path or os.path.join(os.path.expanduser("~"), "Documento.pdf"))[0]
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar PDF traduzido", f"{base} ({traducao.NAMES.get(self.dst)}).pdf",
                                            "PDF (*.pdf)")
        if not fn:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            data = {p: [(r, t, s, bold) for r, _o, t, s, bold in b] for p, b in self.pages.items()}
            out = traducao.translated_pdf(self.tab.doc, data)
            out.save(fn, garbage=3, deflate=True)
        finally:
            QApplication.restoreOverrideCursor()
        self.win.open_path(fn)

    def closeEvent(self, e):
        if getattr(self, "job", None) and self.job.isRunning():
            self.job.cancel = True
            self.job.wait(5000)
        super().closeEvent(e)

    def reject(self):
        if getattr(self, "job", None) and self.job.isRunning():
            self.job.cancel = True
            self.job.wait(5000)
        super().reject()
