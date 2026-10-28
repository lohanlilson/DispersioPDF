"""Janela da fila da impressora Dispersio PDF: o que foi impresso de outros programas fica aqui para juntar,
salvar, abrir, imprimir numa impressora de verdade ou enviar por e-mail."""
import os
import sys
import tempfile
from datetime import datetime

import pymupdf
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QIcon, QImage, QPixmap, QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel,
                               QFileDialog, QMessageBox, QAbstractItemView, QWidget)

from . import icons, impressora, resource
from .config import cfg

APP = "Dispersio PDF"


def _thumb(path, h=64):
    try:
        with pymupdf.open(path) as d:
            p = d[0]
            pix = p.get_pixmap(matrix=pymupdf.Matrix(h / p.rect.height, h / p.rect.height), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            return QIcon(QPixmap.fromImage(img)), d.page_count
    except Exception:
        return icons.icon("createpdf"), 0


def merge(paths, out):
    doc = pymupdf.open()
    for p in paths:
        with pymupdf.open(p) as d:
            doc.insert_pdf(d)
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    return out


def send_mail(path, subject):
    """Abre uma mensagem nova no programa de e-mail do Windows (Outlook, Thunderbird…) com o PDF anexado (MAPI).
    Retorna False se não houver programa de e-mail configurado."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class FileDesc(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("flFlags", wintypes.ULONG), ("nPosition", wintypes.ULONG),
                    ("lpszPathName", wintypes.LPWSTR), ("lpszFileName", wintypes.LPWSTR), ("lpFileType", ctypes.c_void_p)]

    class Message(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("lpszSubject", wintypes.LPWSTR), ("lpszNoteText", wintypes.LPWSTR),
                    ("lpszMessageType", wintypes.LPWSTR), ("lpszDateReceived", wintypes.LPWSTR),
                    ("lpszConversationID", wintypes.LPWSTR), ("flFlags", wintypes.ULONG), ("lpOriginator", ctypes.c_void_p),
                    ("nRecipCount", wintypes.ULONG), ("lpRecips", ctypes.c_void_p), ("nFileCount", wintypes.ULONG),
                    ("lpFiles", ctypes.POINTER(FileDesc))]
    try:
        fn = ctypes.windll.mapi32.MAPISendMailW  # Windows 8 ou mais novo
    except (OSError, AttributeError):
        return False
    f = FileDesc(0, 0, 0xFFFFFFFF, path, os.path.basename(path), None)
    m = Message(0, subject, "", None, None, None, 0, None, 0, None, 1, ctypes.pointer(f))
    rc = fn(0, 0, ctypes.byref(m), 0x1 | 0x8, 0)  # MAPI_LOGON_UI | MAPI_DIALOG
    return rc in (0, 1)  # 0 = ok, 1 = a pessoa cancelou


class PrinterQueueDialog(QDialog):
    """Janela própria (independente do leitor) com a fila da impressora Dispersio PDF."""

    ACTIONS = [("merge", "Juntar num PDF e abrir", "merge"), ("open", "Abrir cada um no leitor", "open"),
               ("save", "Salvar num PDF só…", "save"), ("print", "Imprimir…", "print"),
               ("mail", "Enviar por e-mail…", "attach"), ("remove", "Tirar da fila", "trash")]

    def __init__(self, win):
        super().__init__(None)  # sem janela-mãe: aparece sozinha, com ícone próprio na barra de tarefas
        self.win = win
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Impressora Dispersio PDF")
        self.setWindowIcon(QIcon(resource("assets", "logo.png")))
        self.resize(820, 540)
        root = QVBoxLayout(self)
        head = QLabel("<b>Documentos impressos na impressora “Dispersio PDF”</b><br>"
                      "<span style='color:gray'>Arraste para mudar a ordem. Clique com Ctrl ou Shift para "
                      "selecionar vários.</span>")
        head.setWordWrap(True)
        root.addWidget(head)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.list = QListWidget()
        self.list.setIconSize(QSize(48, 64))
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSpacing(2)
        self.list.itemDoubleClicked.connect(lambda it: self._open([it.data(Qt.UserRole)]))
        self.list.itemSelectionChanged.connect(self._update)
        body.addWidget(self.list, 1)
        side = QVBoxLayout()
        body.addLayout(side)
        from PySide6.QtWidgets import QGroupBox, QGridLayout
        self.groups, self.buttons = {}, {}
        for scope in ("all", "sel"):
            g = QGroupBox()
            gl = QGridLayout(g)
            gl.setSpacing(6)
            for k, (key, text, icon) in enumerate(self.ACTIONS):
                bt = QPushButton(icons.icon(icon), text)
                bt.setMinimumWidth(180)
                bt.clicked.connect(lambda _=False, a=key, sc=scope: self.run(a, sc))
                gl.addWidget(bt, k // 2, k % 2)
                self.buttons[(scope, key)] = bt
            self.groups[scope] = g
            side.addWidget(g)
        side.addStretch(1)
        folder = QPushButton(icons.icon("open"), "Abrir a pasta da fila")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(impressora.queue_dir())))
        side.addWidget(folder)
        self.empty = QLabel("A fila está vazia. Em qualquer programa, escolha <b>Imprimir</b> e a impressora "
                            "<b>Dispersio PDF</b>.")
        self.empty.setWordWrap(True)
        self.empty.setObjectName("Muted")
        root.addWidget(self.empty)
        self.refresh()

    # ------------------------------------------------------------------ fila
    def refresh(self, select=None):
        known = {self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())}
        files = impressora.queue_files()
        for i in reversed(range(self.list.count())):  # some quem foi apagado por fora
            if self.list.item(i).data(Qt.UserRole) not in files:
                self.list.takeItem(i)
        for f in files:
            if f in known:
                continue
            icon, n = _thumb(f)
            when = datetime.fromtimestamp(os.path.getmtime(f))
            it = QListWidgetItem(icon, f"{impressora.title_of(f)}\n{n} página(s) · {when:%d/%m %H:%M}")
            it.setData(Qt.UserRole, f)
            self.list.addItem(it)
        if select:
            self.list.clearSelection()
            for i in range(self.list.count()):
                if os.path.normcase(self.list.item(i).data(Qt.UserRole)) in {os.path.normcase(x) for x in select}:
                    self.list.item(i).setSelected(True)
                    self.list.scrollToItem(self.list.item(i))
        self._update()

    def _update(self):
        n = self.list.count()
        k = len(self.list.selectedItems())
        self.empty.setVisible(n == 0)
        self.groups["all"].setTitle(f"Com todos os documentos ({n})")
        self.groups["sel"].setTitle(f"Só com os selecionados ({k})" if k else "Só com os selecionados (selecione na lista)")
        for (scope, key), bt in self.buttons.items():
            bt.setEnabled(bool(n if scope == "all" else k))
        single = {"merge": "Abrir no leitor", "save": "Salvar como…"}
        for scope, count in (("all", n), ("sel", k)):
            for key, text, _ in self.ACTIONS:
                self.buttons[(scope, key)].setText(single.get(key, text) if count == 1 else text)
            self.buttons[(scope, "open")].setVisible(count != 1)  # com um só, "Abrir no leitor" já basta

    def paths(self, scope):
        """Na ordem da lista: todos, ou só os selecionados."""
        items = [self.list.item(i) for i in range(self.list.count())]
        if scope == "sel":
            items = [it for it in items if it.isSelected()]
        return [it.data(Qt.UserRole) for it in items]

    def chosen(self):  # compatibilidade: selecionados, ou todos se nenhum
        return self.paths("sel") or self.paths("all")

    def run(self, action, scope):
        paths = self.paths(scope)
        if paths:
            getattr(self, "do_" + action)(paths)

    def _name(self, paths):
        return impressora.title_of(paths[0]) if len(paths) == 1 else f"Documentos impressos {datetime.now():%d-%m-%Y %H%M}"

    def _merged_temp(self, paths):
        out = os.path.join(tempfile.mkdtemp(prefix="dispersio-fila-"), self._name(paths) + ".pdf")
        return merge(paths, out)

    def _open(self, paths):
        show = getattr(self.win, "show_main", None)
        if show:
            show()
        for p in paths:
            self.win.open_path(p)
        self.win.bring_to_front()

    # ------------------------------------------------------------------ ações
    def do_merge(self, paths):
        self._open([self._merged_temp(paths) if len(paths) > 1 else paths[0]])

    def do_open(self, paths):
        self._open(paths)

    def do_save(self, paths):
        start = os.path.join(self.win.settings.value("last_dir", "") or os.path.expanduser("~"), self._name(paths) + ".pdf")
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar como PDF", start, "PDF (*.pdf)")
        if not fn:
            return
        try:
            merge(paths, fn)
        except Exception as e:
            QMessageBox.warning(self, APP, f"Não foi possível salvar: {e}")
            return
        self.win.settings.setValue("last_dir", os.path.dirname(fn))
        if QMessageBox.question(self, APP, f"Salvo em:\n{fn}\n\nTirar da fila o que foi salvo?") == QMessageBox.Yes:
            self._delete(paths)

    def do_print(self, paths):
        from .print_manager import PrintManager, Source
        sources = [Source(impressora.title_of(p) + ".pdf", pymupdf.open(p)) for p in paths]
        PrintManager(self, sources, "Imprimir" if len(sources) == 1 else f"Imprimir {len(sources)} documentos").exec()

    def do_mail(self, paths):
        f = self._merged_temp(paths) if len(paths) > 1 else paths[0]
        if not send_mail(f, self._name(paths)):
            QMessageBox.information(self, APP, "Não encontrei um programa de e-mail configurado no Windows.\n"
                                               "Vou abrir a pasta com o arquivo para você anexar no e-mail.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(f)))

    def do_remove(self, paths):
        what = "todos os documentos" if len(paths) == self.list.count() and len(paths) > 1 else f"{len(paths)} documento(s)"
        if QMessageBox.question(self, APP, f"Tirar {what} da fila? Os arquivos serão apagados.") == QMessageBox.Yes:
            self._delete(paths)

    # nomes antigos (testes e atalhos)
    def save(self):
        self.do_save(self.chosen())

    def merge_open(self):
        self.do_merge(self.chosen())

    def open_each(self):
        self.do_open(self.chosen())

    def remove(self):
        self.do_remove(self.chosen())

    def _delete(self, paths):
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass
        self.refresh()


def offer_install(win):
    """Pergunta, uma vez, se a pessoa quer adicionar a impressora (quem atualizou de uma versão anterior)."""
    box = QMessageBox(win)
    box.setWindowTitle(APP)
    box.setIconPixmap(QIcon(resource("assets", "logo.png")).pixmap(64, 64))
    box.setText("<b>Novidade: impressora Dispersio PDF</b>")
    box.setInformativeText("Com ela, qualquer programa (Word, Excel, navegador…) imprime direto em PDF. Os documentos "
                           "vão para uma fila onde você pode <b>juntar tudo num PDF só</b>, salvar, editar, imprimir "
                           "numa impressora de verdade ou enviar por e-mail.<br><br>"
                           "Quer adicionar a impressora neste computador? O Windows vai pedir permissão de administrador.")
    yes = box.addButton("Adicionar impressora", QMessageBox.AcceptRole)
    box.addButton("Agora não", QMessageBox.RejectRole)
    box.exec()
    cfg.set("printer_offered", True)
    if box.clickedButton() is yes:
        return install(win)
    QMessageBox.information(win, APP, "Tudo bem. Se mudar de ideia, é só ir em Preferências › Impressora.")
    return False


def install(win):
    from PySide6.QtWidgets import QApplication
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        code = impressora.run_elevated("--install-printer")
    finally:
        QApplication.restoreOverrideCursor()
    if code is None:
        QMessageBox.information(win, APP, "A impressora não foi adicionada (a permissão de administrador foi recusada).")
        return False
    if code == 0 and impressora.is_installed():
        impressora.start_agent()
        QMessageBox.information(win, APP, "Pronto! A impressora <b>Dispersio PDF</b> já aparece na lista de impressoras "
                                          "de todos os programas.")
        return True
    QMessageBox.warning(win, APP, "Não foi possível adicionar a impressora. Veja o registro em:\n"
                        + os.path.join(impressora.queue_dir(), "impressora.log"))
    return False


def uninstall(win):
    if QMessageBox.question(win, APP, "Remover a impressora Dispersio PDF deste computador?") != QMessageBox.Yes:
        return False
    code = impressora.run_elevated("--uninstall-printer")
    if code is None:
        return False
    ok = not impressora.is_installed()
    QMessageBox.information(win, APP, "Impressora removida." if ok else "Não foi possível remover a impressora.")
    return ok
