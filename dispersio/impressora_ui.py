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
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Impressora Dispersio PDF")
        self.setWindowIcon(QIcon(resource("assets", "logo.png")))
        self.resize(760, 520)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        root = QVBoxLayout(self)
        head = QLabel("<b>Documentos impressos na impressora “Dispersio PDF”</b><br>"
                      "<span style='color:gray'>Arraste para mudar a ordem. As ações usam os selecionados — "
                      "ou todos, se nenhum estiver selecionado.</span>")
        head.setWordWrap(True)
        root.addWidget(head)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.list = QListWidget()
        self.list.setIconSize(QSize(48, 64))
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSpacing(2)
        self.list.itemDoubleClicked.connect(lambda it: self.win.open_path(it.data(Qt.UserRole)))
        self.list.itemSelectionChanged.connect(self._update)
        body.addWidget(self.list, 1)
        side = QVBoxLayout()
        body.addLayout(side)

        def btn(text, icon, slot, tip=""):
            b = QPushButton(icons.icon(icon), text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            b.setMinimumWidth(220)
            side.addWidget(b)
            return b
        self.b_merge = btn("Juntar num PDF e abrir", "merge", self.merge_open,
                           "Junta os documentos na ordem da lista e abre no Dispersio para editar ou salvar")
        self.b_open = btn("Abrir no Dispersio", "open", self.open_each, "Abre cada documento numa aba")
        self.b_save = btn("Salvar como PDF…", "save", self.save, "Vários documentos são salvos juntos num PDF só")
        self.b_print = btn("Imprimir…", "print", self.print_, "Manda para uma impressora de verdade, tudo de uma vez")
        self.b_mail = btn("Enviar por e-mail…", "attach", self.mail,
                          "Abre uma mensagem no seu programa de e-mail com o PDF anexado")
        side.addSpacing(12)
        self.b_remove = btn("Tirar da fila", "trash", self.remove)
        side.addStretch(1)
        self.b_folder = btn("Abrir pasta da fila", "open", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(impressora.queue_dir())))
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
                if self.list.item(i).data(Qt.UserRole) in select:
                    self.list.item(i).setSelected(True)
                    self.list.scrollToItem(self.list.item(i))
        self._update()

    def _update(self):
        n = self.list.count()
        self.empty.setVisible(n == 0)
        for b in (self.b_merge, self.b_open, self.b_save, self.b_print, self.b_mail, self.b_remove):
            b.setEnabled(n > 0)
        sel = len(self.list.selectedItems())
        scope = f" ({sel})" if sel else (f" (todos: {n})" if n > 1 else "")
        self.b_merge.setText("Juntar num PDF e abrir" + scope)
        self.b_save.setText("Salvar como PDF…" + scope)
        self.b_print.setText("Imprimir…" + scope)

    def chosen(self):
        """Selecionados, na ordem da lista; se nenhum, todos."""
        items = [self.list.item(i) for i in range(self.list.count())]
        sel = [it for it in items if it.isSelected()]
        return [it.data(Qt.UserRole) for it in (sel or items)]

    def _name(self, paths):
        return impressora.title_of(paths[0]) if len(paths) == 1 else f"Documentos impressos {datetime.now():%d-%m-%Y %H%M}"

    def _merged_temp(self, paths):
        out = os.path.join(tempfile.mkdtemp(prefix="dispersio-fila-"), self._name(paths) + ".pdf")
        return merge(paths, out)

    # ------------------------------------------------------------------ ações
    def merge_open(self):
        paths = self.chosen()
        if paths:
            self.win.open_path(self._merged_temp(paths) if len(paths) > 1 else paths[0])

    def open_each(self):
        for p in self.chosen():
            self.win.open_path(p)

    def save(self):
        paths = self.chosen()
        if not paths:
            return
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

    def print_(self):
        from .print_manager import PrintManager, Source
        paths = self.chosen()
        sources = [Source(impressora.title_of(p) + ".pdf", pymupdf.open(p)) for p in paths]
        if sources:
            PrintManager(self, sources, "Imprimir" if len(sources) == 1 else f"Imprimir {len(sources)} documentos").exec()

    def mail(self):
        paths = self.chosen()
        if not paths:
            return
        f = self._merged_temp(paths) if len(paths) > 1 else paths[0]
        if not send_mail(f, self._name(paths)):
            QMessageBox.information(self, APP, "Não encontrei um programa de e-mail configurado no Windows.\n"
                                               "Vou abrir a pasta com o arquivo para você anexar no e-mail.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(f)))

    def remove(self):
        paths = self.chosen()
        if not paths:
            return
        what = "todos os documentos" if not self.list.selectedItems() and len(paths) > 1 else f"{len(paths)} documento(s)"
        if QMessageBox.question(self, APP, f"Tirar {what} da fila? Os arquivos serão apagados.") == QMessageBox.Yes:
            self._delete(paths)

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
