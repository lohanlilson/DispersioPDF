"""Busca em vários PDFs de uma pasta (e subpastas).

Ignora acentos e maiúsculas ("credito" acha "CRÉDITO"); números como CPF, CNPJ e contrato são achados com ou sem
pontuação ("07202627000174" acha "07.202.627/0001-74"). Roda em segundo plano; clicar num resultado abre o arquivo
na página, com o trecho destacado.
"""
import os
import re
import unicodedata

import pymupdf
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QCheckBox, QLabel,
                               QTreeWidget, QTreeWidgetItem, QFileDialog, QHeaderView)

from .config import cfg

MAX_HITS_PER_FILE = 50


def _fold_char(c):
    d = unicodedata.normalize("NFKD", c)
    base = "".join(x for x in d if not unicodedata.combining(x))
    return (base[:1] or c).lower()


def fold(text):
    """Minúsculas e sem acento, com o MESMO tamanho do texto original (para recortar o trecho certo)."""
    return "".join(_fold_char(c) if ord(c) > 127 or c.isupper() else c for c in text)


def make_pattern(query, whole_word=False):
    """Regex sobre o texto “dobrado”. Números longos aceitam pontuação/espaço entre os dígitos."""
    q = fold(query.strip())
    if not q:
        return None
    digits = re.sub(r"\D", "", q)
    if len(digits) >= 6 and re.fullmatch(r"[\d.\-/\s]+", q):
        pat = r"[.\-/\s]?".join(re.escape(d) for d in digits)
        return re.compile(r"(?<!\d)" + pat + r"(?!\d)")
    pat = r"\s+".join(re.escape(p) for p in q.split())
    if whole_word:
        pat = r"(?<!\w)" + pat + r"(?!\w)"
    return re.compile(pat)


def search_file(path, pattern, cancel=lambda: False):
    """[(página, trecho, texto achado)] e um aviso (protegido, sem texto...) ou ""."""
    hits = []
    try:
        doc = pymupdf.open(path)
    except Exception:
        return hits, "não abriu (arquivo danificado?)"
    try:
        if doc.needs_pass:
            return hits, "protegido por senha"
        any_text = False
        for pno in range(doc.page_count):
            if cancel() or len(hits) >= MAX_HITS_PER_FILE:
                break
            try:
                text = doc[pno].get_text()
            except Exception:
                continue
            if text.strip():
                any_text = True
            folded = fold(text)
            for m in pattern.finditer(folded):
                a, b = m.span()
                s0 = max(0, a - 60)
                s1 = min(len(text), b + 60)
                snippet = ("…" if s0 else "") + re.sub(r"\s+", " ", text[s0:s1]).strip() + ("…" if s1 < len(text) else "")
                hits.append((pno, snippet, text[a:b]))
                if len(hits) >= MAX_HITS_PER_FILE:
                    break
        return hits, ("" if any_text else "sem texto (é imagem — use OCR)")
    finally:
        doc.close()


def list_pdfs(folder, recursive=True):
    out = []
    if recursive:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("$RECYCLE.BIN", "System Volume Information")]
            out += [os.path.join(root, f) for f in files if f.lower().endswith(".pdf")]
    else:
        out = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    return sorted(out, key=lambda p: p.lower())


class _Worker(QThread):
    found = Signal(str, list, str)      # arquivo, acertos, aviso
    progress = Signal(int, int, str)

    def __init__(self, folder, query, recursive, whole):
        super().__init__()
        self.folder, self.query, self.recursive, self.whole = folder, query, recursive, whole

    def run(self):
        pat = make_pattern(self.query, self.whole)
        if pat is None:
            return
        files = list_pdfs(self.folder, self.recursive)
        for n, f in enumerate(files, 1):
            if self.isInterruptionRequested():
                return
            self.progress.emit(n, len(files), os.path.basename(f))
            hits, note = search_file(f, pat, self.isInterruptionRequested)
            if hits or note:
                self.found.emit(f, hits, note)
        self.progress.emit(len(files), len(files), "")


class FolderSearchDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.worker = None
        self.setWindowTitle("Buscar em vários PDFs")
        self.resize(820, 560)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.folder = QLineEdit(cfg.qs.value("busca_pasta/pasta", "") or os.path.expanduser("~"))
        pick = QPushButton("Pasta…")
        pick.clicked.connect(self._pick)
        row.addWidget(QLabel("Pasta:"))
        row.addWidget(self.folder, 1)
        row.addWidget(pick)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Nome, CPF, CNPJ, número do contrato, palavra…")
        self.query.returnPressed.connect(self.start)
        self.go = QPushButton("Buscar")
        self.go.setDefault(True)
        self.go.clicked.connect(self.start)
        row.addWidget(self.query, 1)
        row.addWidget(self.go)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.sub = QCheckBox("Incluir subpastas")
        self.sub.setChecked(cfg.qs.value("busca_pasta/sub", "true") in ("true", True))
        self.whole = QCheckBox("Palavra inteira")
        row.addWidget(self.sub)
        row.addWidget(self.whole)
        row.addStretch()
        lay.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Arquivo / página", "Trecho"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.setColumnWidth(0, 260)
        self.tree.itemActivated.connect(self._open)
        lay.addWidget(self.tree, 1)
        self.status = QLabel("Digite o que procurar e clique em Buscar. Acentos e maiúsculas não importam.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.query.setFocus()

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta para buscar", self.folder.text())
        if d:
            self.folder.setText(d)

    def start(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
            self.go.setText("Buscar")
            self.status.setText(self.status.text() + " (parado)")
            return
        folder, q = self.folder.text().strip(), self.query.text().strip()
        if not q:
            return
        if not os.path.isdir(folder):
            self.status.setText("Escolha uma pasta que exista.")
            return
        cfg.qs.setValue("busca_pasta/pasta", folder)
        cfg.qs.setValue("busca_pasta/sub", "true" if self.sub.isChecked() else "false")
        self.tree.clear()
        self.n_files = self.n_hits = 0
        self.notes = []
        self.go.setText("Parar")
        self.worker = _Worker(folder, q, self.sub.isChecked(), self.whole.isChecked())
        self.worker.found.connect(self._found)
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._done)
        self.worker.start()

    def _found(self, path, hits, note):
        if not hits:
            self.notes.append(f"{os.path.basename(path)}: {note}")
            return
        self.n_files += 1
        self.n_hits += len(hits)
        top = QTreeWidgetItem([f"{os.path.basename(path)}  ({len(hits)}{'+' if len(hits) >= MAX_HITS_PER_FILE else ''})",
                               os.path.dirname(path)])
        top.setToolTip(0, path)
        top.setData(0, Qt.UserRole, (path, hits[0][0], hits[0][2]))
        for pno, snip, match in hits:
            it = QTreeWidgetItem([f"Página {pno + 1}", snip])
            it.setToolTip(1, snip)
            it.setData(0, Qt.UserRole, (path, pno, match))
            top.addChild(it)
        self.tree.addTopLevelItem(top)
        if self.tree.topLevelItemCount() <= 3:
            top.setExpanded(True)

    def _progress(self, n, total, name):
        self.status.setText(f"Procurando… {n} de {total} arquivo(s): {name}" if name else "")

    def _done(self):
        self.go.setText("Buscar")
        msg = (f"{self.n_hits} resultado(s) em {self.n_files} arquivo(s)." if self.n_hits
               else "Nada encontrado.")
        if self.notes:
            msg += f"  {len(self.notes)} arquivo(s) não puderam ser lidos: " + "; ".join(self.notes[:4]) + ("…" if len(self.notes) > 4 else "")
        self.status.setText(msg + "  Clique duas vezes num resultado para abrir.")

    def _open(self, item, _col=0):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        path, pno, match = data
        self.win.open_at(path, pno, match)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        super().closeEvent(e)
