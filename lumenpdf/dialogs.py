"""Diálogos das ferramentas."""
import io
import os

import pymupdf
from PySide6.QtCore import Qt, QPointF, QRectF, QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QFontDatabase, QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QSpinBox,
                               QDoubleSpinBox, QComboBox, QCheckBox, QDialogButtonBox, QPlainTextEdit,
                               QPushButton, QColorDialog, QTabWidget, QWidget, QFileDialog, QListWidget,
                               QListWidgetItem, QRadioButton, QButtonGroup, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QSlider, QGroupBox, QHeaderView, QAbstractItemView, QMessageBox)

from . import ops, icons


class ColorButton(QPushButton):
    def __init__(self, color="#000000"):
        super().__init__()
        self.setFixedSize(46, 28)
        self.set_color(color)
        self.clicked.connect(self.pick)

    def set_color(self, c):
        self.color = c
        self.setStyleSheet(f"background:{c}; border:1px solid #888; border-radius:6px;")

    def pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Cor")
        if c.isValid():
            self.set_color(c.name())


class FormDialog(QDialog):
    """Diálogo de formulário simples: título, linhas (rótulo, widget) e OK/Cancelar."""

    def __init__(self, parent, title, rows, ok_text="OK", intro=None, width=420):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        lay = QVBoxLayout(self)
        if intro:
            lb = QLabel(intro)
            lb.setWordWrap(True)
            lb.setObjectName("Muted")
            lay.addWidget(lb)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for label, w in rows:
            if label is None:
                form.addRow(w)
            else:
                form.addRow(label, w)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(ok_text)
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


def spin(v, lo, hi, dec=False, suffix=""):
    w = QDoubleSpinBox() if dec else QSpinBox()
    w.setRange(lo, hi)
    w.setValue(v)
    if suffix:
        w.setSuffix(suffix)
    return w


def combo(items, current=None):
    w = QComboBox()
    w.addItems(items)
    if current:
        w.setCurrentText(current)
    return w


def line(text="", placeholder="", password=False):
    w = QLineEdit(text)
    w.setPlaceholderText(placeholder)
    if password:
        w.setEchoMode(QLineEdit.Password)
    return w


# ---------------------------------------------------------------- edição de texto
class EditTextDialog(FormDialog):
    def __init__(self, parent, span):
        self.text = QPlainTextEdit(span["text"])
        self.text.setFixedHeight(80)
        self.size = spin(round(span["size"], 1), 4, 200, dec=True, suffix=" pt")
        orig = span.get("font", "").split("+")[-1] or "original"
        self.font = combo([f"Original ({orig})"] + list(ops.BASE_FONTS))
        c = span.get("color", 0)
        self.colorb = ColorButton("#%06x" % c)
        super().__init__(parent, "Editar texto", [("Texto:", self.text), ("Fonte:", self.font),
                                                   ("Tamanho:", self.size), ("Cor:", self.colorb)],
                         intro="O trecho será substituído mantendo a fonte original sempre que possível "
                               "(fonte do PDF ou a mesma fonte instalada no Windows).")

    def values(self):
        f = self.font.currentText()
        return (self.text.toPlainText(), self.size.value(), ops.hex_to_rgb(self.colorb.color),
                ops.BASE_FONTS.get(f, ops.ORIGINAL_FONT))


class AddTextDialog(FormDialog):
    def __init__(self, parent):
        self.text = QPlainTextEdit()
        self.text.setFixedHeight(90)
        self.size = spin(12, 4, 200, dec=True, suffix=" pt")
        self.font = combo(list(ops.BASE_FONTS))
        self.colorb = ColorButton("#000000")
        super().__init__(parent, "Adicionar texto", [("Texto:", self.text), ("Fonte:", self.font),
                                                       ("Tamanho:", self.size), ("Cor:", self.colorb)])

    def values(self):
        return (self.text.toPlainText(), self.size.value(), ops.BASE_FONTS[self.font.currentText()],
                ops.hex_to_rgb(self.colorb.color))


# ---------------------------------------------------------------- assinatura (preencher e assinar)
class SignaturePad(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(460, 170)
        self.paths = []
        self.setStyleSheet("background:white; border:1px solid #ccc; border-radius:8px;")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def mousePressEvent(self, e):
        self.paths.append([e.position()])

    def mouseMoveEvent(self, e):
        if self.paths:
            self.paths[-1].append(e.position())
            self.update()

    def clear(self):
        self.paths = []
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#cccccc"), 1, Qt.DashLine))
        p.drawLine(20, self.height() - 35, self.width() - 20, self.height() - 35)
        self._draw(p, QColor("#0b2a6f"))

    def _draw(self, p, col, offset=QPointF(0, 0)):
        p.setPen(QPen(col, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for pts in self.paths:
            if len(pts) < 2:
                continue
            path = QPainterPath(pts[0] - offset)
            for pt in pts[1:]:
                path.lineTo(pt - offset)
            p.drawPath(path)

    def image(self, color):
        if not self.paths:
            return None
        xs = [pt.x() for ps in self.paths for pt in ps]
        ys = [pt.y() for ps in self.paths for pt in ps]
        box = QRectF(min(xs) - 6, min(ys) - 6, max(xs) - min(xs) + 12, max(ys) - min(ys) + 12)
        img = QImage(int(box.width() * 3), int(box.height() * 3), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(3, 3)
        self._draw(p, QColor(color), box.topLeft())
        p.end()
        return img


def _png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


class SignatureDialog(QDialog):
    """Criar assinatura: desenhar, digitar ou importar imagem. Retorna PNG transparente."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Criar assinatura")
        self.png = None
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        # digitar
        tw = QWidget()
        tl = QVBoxLayout(tw)
        self.name = line(placeholder="Digite seu nome")
        self.font = QComboBox()
        fams = QFontDatabase.families()
        cursive = [f for f in fams if any(k in f.lower() for k in ("script", "hand", "brush", "segoe print",
                                                                     "mistral", "vivaldi", "lucida hand",
                                                                     "dancing", "pacifico", "great vibes",
                                                                     "kalam", "caveat", "z003", "chancery"))]
        self.font.addItems(cursive or ["Segoe Script", "Brush Script MT", "serif"])
        self.preview = QLabel()
        self.preview.setMinimumHeight(110)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:white; border:1px solid #ccc; border-radius:8px;")
        self.name.textChanged.connect(self._upd)
        self.font.currentTextChanged.connect(self._upd)
        tl.addWidget(self.name)
        tl.addWidget(self.font)
        tl.addWidget(self.preview)
        self.tabs.addTab(tw, "Digitar")
        # desenhar
        dw = QWidget()
        dl = QVBoxLayout(dw)
        self.pad = SignaturePad()
        dl.addWidget(self.pad)
        clr = QPushButton("Limpar")
        clr.clicked.connect(self.pad.clear)
        dl.addWidget(clr, alignment=Qt.AlignRight)
        self.tabs.addTab(dw, "Desenhar")
        # imagem
        iw = QWidget()
        il = QVBoxLayout(iw)
        self.img_label = QLabel("Nenhuma imagem selecionada")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumHeight(120)
        b = QPushButton("Selecionar imagem…")
        b.clicked.connect(self._pick)
        self.remove_white = QCheckBox("Remover fundo branco")
        self.remove_white.setChecked(True)
        il.addWidget(self.img_label)
        il.addWidget(self.remove_white)
        il.addWidget(b, alignment=Qt.AlignLeft)
        self.img_path = None
        self.tabs.addTab(iw, "Imagem")
        lay.addWidget(self.tabs)
        row = QHBoxLayout()
        row.addWidget(QLabel("Cor:"))
        self.colorb = ColorButton("#0b2a6f")
        row.addWidget(self.colorb)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Salvar assinatura")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _typed_image(self):
        txt = self.name.text().strip()
        if not txt:
            return None
        f = QFont(self.font.currentText(), 64)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(f)
        w, h = fm.horizontalAdvance(txt) + 40, fm.height() + 20
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(f)
        p.setPen(QColor(self.colorb.color))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, txt)
        p.end()
        return img

    def _upd(self):
        img = self._typed_image()
        self.preview.setPixmap(QPixmap.fromImage(img).scaledToHeight(90, Qt.SmoothTransformation) if img else QPixmap())

    def _pick(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Imagem da assinatura", "", "Imagens (*.png *.jpg *.jpeg *.bmp)")
        if fn:
            self.img_path = fn
            self.img_label.setPixmap(QPixmap(fn).scaledToHeight(110, Qt.SmoothTransformation))

    def _ok(self):
        t = self.tabs.currentIndex()
        img = None
        if t == 0:
            img = self._typed_image()
        elif t == 1:
            img = self.pad.image(self.colorb.color)
        elif self.img_path:
            img = QImage(self.img_path).convertToFormat(QImage.Format_ARGB32)
            if self.remove_white.isChecked():
                for y in range(img.height()):
                    for x in range(img.width()):
                        c = img.pixelColor(x, y)
                        if c.red() > 225 and c.green() > 225 and c.blue() > 225:
                            img.setPixelColor(x, y, QColor(0, 0, 0, 0))
        if img is None:
            QMessageBox.warning(self, "Assinatura", "Crie a assinatura antes de salvar.")
            return
        self.png = _png_bytes(img)
        self.accept()


# ---------------------------------------------------------------- assinatura digital
class CertSignDialog(FormDialog):
    KINDS = ["Certificado instalado no Windows (A1 ou A3/token)", "Certificado A1 em arquivo (.pfx/.p12)",
             "Token A3 via biblioteca PKCS#11 (avançado)"]

    def __init__(self, parent, last_pfx="", last_cert="", last_kind=0):
        from . import wincert
        self.wincert = wincert
        self.kind = combo(self.KINDS)
        # certificados do Windows
        self.certs = []
        self.cert_combo = QComboBox()
        self.cert_combo.setMinimumWidth(420)
        refresh = QPushButton("Atualizar")
        refresh.setToolTip("Recarregar (ex.: depois de conectar o token)")
        refresh.clicked.connect(self._load_certs)
        self.cert_row = QWidget()
        cl = QHBoxLayout(self.cert_row)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.cert_combo, 1)
        cl.addWidget(refresh)
        self.show_expired = QCheckBox("Mostrar vencidos")
        self.show_expired.toggled.connect(self._load_certs)
        # arquivo / biblioteca
        self.pfx = line(last_pfx, "Selecione o arquivo do certificado")
        bpick = QPushButton("…")
        bpick.setFixedWidth(36)
        bpick.clicked.connect(self._pick)
        self.file_row = QWidget()
        rl = QHBoxLayout(self.file_row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.pfx)
        rl.addWidget(bpick)
        self.pwd = line(password=True, placeholder="Senha do arquivo / PIN do token")
        from .config import cfg as _cfg
        self.reason = line(_cfg.get("sign_reason"))
        self.location = line(_cfg.get("sign_location"))
        from . import signing
        st = getattr(parent, "settings", None)
        self.use_tsa = QCheckBox("Carimbo de tempo (data e hora certificadas por um servidor confiável)")
        self.use_tsa.setChecked((st.value("sign_tsa", "true") if st else "true") == "true")
        self.tsa = QComboBox()
        self.tsa.setEditable(True)
        for label, url in signing.TSA_SERVERS.items():
            self.tsa.addItem(f"{label} — {url}", url)
        saved = st.value("sign_tsa_url", signing.DEFAULT_TSA) if st else signing.DEFAULT_TSA
        idx = self.tsa.findData(saved)
        if idx >= 0:
            self.tsa.setCurrentIndex(idx)
        else:
            self.tsa.setEditText(saved)
        self.use_ltv = QCheckBox("Validação de longo prazo — LTV (continua verificável após o certificado vencer)")
        self.use_ltv.setChecked((st.value("sign_ltv", "true") if st else "true") == "true")
        self.use_tsa.toggled.connect(self.tsa.setEnabled)
        self.tsa.setEnabled(self.use_tsa.isChecked())
        super().__init__(parent, "Assinar com certificado digital", [
            ("Tipo:", self.kind), ("Certificado:", self.cert_row), ("", self.show_expired),
            ("Arquivo / biblioteca:", self.file_row), ("Senha / PIN:", self.pwd),
            ("Motivo:", self.reason), ("Local:", self.location),
            (None, self.use_tsa), ("Servidor:", self.tsa), (None, self.use_ltv)],
            ok_text="Assinar", width=620,
            intro="Assinatura no padrão PAdES (compatível com ICP-Brasil), salva como um novo PDF. "
                  "Com certificado instalado, o Windows ou o driver do token pede o PIN quando necessário.")
        self.form = self.findChild(QFormLayout)
        self._last_cert = last_cert
        self._load_certs()
        if not wincert.IS_WINDOWS and last_kind == 0:
            last_kind = 1
        self.kind.setCurrentIndex(int(last_kind or 0))
        self.kind.currentIndexChanged.connect(self._kind)
        self._kind(self.kind.currentIndex())

    def _load_certs(self):
        self.cert_combo.clear()
        try:
            self.certs = self.wincert.list_certificates(include_expired=self.show_expired.isChecked())
        except Exception as e:
            self.certs = []
            self.cert_combo.addItem(f"Erro ao ler certificados: {e}")
            return
        if not self.certs:
            self.cert_combo.addItem("Nenhum certificado com chave privada encontrado" if self.wincert.IS_WINDOWS
                                    else "Disponível apenas no Windows")
            return
        for i, c in enumerate(self.certs):
            self.cert_combo.addItem(c.label())
            if c.der.hex()[-40:] == self._last_cert:
                self.cert_combo.setCurrentIndex(i)

    def _set_row(self, widget, visible):
        widget.setVisible(visible)
        lb = self.form.labelForField(widget)
        if lb:
            lb.setVisible(visible)

    def _kind(self, i):
        self._set_row(self.cert_row, i == 0)
        self._set_row(self.show_expired, i == 0)
        self._set_row(self.file_row, i != 0)
        self._set_row(self.pwd, i != 0)
        if i == 2 and not self.pfx.text().lower().endswith((".dll", ".so", ".dylib")):
            self.pfx.setText(r"C:\Windows\System32\eTPKCS11.dll" if os.name == "nt" else "/usr/lib/libeToken.so")
        if i == 1 and self.pfx.text().lower().endswith((".dll", ".so", ".dylib")):
            self.pfx.clear()
        self.adjustSize()

    def tsa_url(self):
        if not self.use_tsa.isChecked():
            return None
        data = self.tsa.currentData()
        text = self.tsa.currentText().strip()
        return data if data and text.endswith(data) else (text.split("—")[-1].strip() or None)

    def selected_cert(self):
        i = self.cert_combo.currentIndex()
        return self.certs[i] if 0 <= i < len(self.certs) else None

    def _pick(self):
        flt = "Certificado (*.pfx *.p12)" if self.kind.currentIndex() == 1 else "Biblioteca PKCS#11 (*.dll *.so *.dylib)"
        fn, _ = QFileDialog.getOpenFileName(self, "Certificado", "", flt)
        if fn:
            self.pfx.setText(fn)


def _fmt_dt(dt):
    if not dt:
        return "—"
    try:
        return dt.astimezone().strftime("%d/%m/%Y %H:%M:%S (UTC%z)")
    except Exception:
        return str(dt)


SIG_COLORS = {"ok": "#2d9d78", "warn": "#c58a00", "bad": "#d7373f"}
SIG_SYMBOL = {"ok": "✔", "warn": "⚠", "bad": "✖"}


class SignatureInfoDialog(QDialog):
    """Validação individual de uma assinatura (equivalente às 'Propriedades da assinatura' do Acrobat)."""

    def __init__(self, parent, info, on_view_signed=None, on_changes=None):
        from . import signing
        super().__init__(parent)
        self.setWindowTitle("Validação da assinatura")
        self.setMinimumWidth(620)
        lvl, title = signing.status_of(info)
        col = SIG_COLORS[lvl]
        lay = QVBoxLayout(self)
        head = QLabel(f"<table><tr><td style='font-size:30px; color:{col}; padding-right:10px'>{SIG_SYMBOL[lvl]}</td>"
                      f"<td><span style='font-size:15px; font-weight:600'>{html_escape(title)}</span><br>"
                      f"<span style='color:gray'>Assinatura {info.get('index', 1)} de {info.get('total', 1)} — "
                      f"campo “{html_escape(info.get('field') or '')}”</span></td></tr></table>")
        head.setWordWrap(True)
        lay.addWidget(head)
        c = info.get("cert") or {}

        def yesno(ok, yes, no):
            return f"<span style='color:{SIG_COLORS['ok'] if ok else SIG_COLORS['bad']}'>{'✔ ' + yes if ok else '✖ ' + no}</span>"
        mod = info.get("modification")
        mod_txt = {None: "—", "NONE": "Nenhuma alteração após a assinatura",
                   "LTA_UPDATES": "Apenas dados de validação de longo prazo (permitido)",
                   "FORM_FILLING": "Preenchimento de formulário/assinaturas posteriores (permitido)",
                   "ANNOTATIONS": "Comentários adicionados depois da assinatura",
                   "OTHER": "Conteúdo alterado depois da assinatura"}.get(mod, mod)
        rows = [
            ("<b>Signatário</b>", ""),
            ("Nome", c.get("nome") or info.get("signer")),
            ("CPF/CNPJ", c.get("documento") or "—"),
            ("Organização", c.get("organizacao") or "—"),
            ("E-mail", c.get("email") or "—"),
            ("<b>Assinatura</b>", ""),
            ("Data/hora informada", _fmt_dt(info.get("time")) + ("" if info.get("tsa_time") else " (relógio do computador do signatário)")),
            ("Carimbo de tempo", (f"{_fmt_dt(info.get('tsa_time'))} — " + ("certificado por servidor confiável" if info.get("tsa_trusted") and info.get("tsa_valid") else "servidor não verificado"))
             if info.get("tsa_time") else "Não possui"),
            ("Validação de longo prazo", "Sim (LTV — dados de validação embutidos)" if info.get("ltv") else "Não"),
            ("Motivo", info.get("reason") or "—"),
            ("Local", info.get("location") or "—"),
            ("Integridade", yesno(info.get("intact"), "O documento não foi alterado desde a assinatura",
                                  "O conteúdo assinado foi alterado")),
            ("Criptografia", yesno(info.get("valid"), "Assinatura matematicamente válida", "Assinatura inválida")),
            ("Alterações posteriores", html_escape(str(mod_txt))),
            ("Identidade", yesno(info.get("trusted"), "Certificado confiável (cadeia verificada)",
                                 "Cadeia de certificação não verificada neste computador")),
            ("<b>Certificado</b>", ""),
            ("Emitido por", f"{c.get('emissor', '—')}" + (f" ({c.get('emissor_org')})" if c.get('emissor_org') else "")),
            ("Validade", f"{_fmt_dt(c.get('valido_de'))[:10]} a {_fmt_dt(c.get('valido_ate'))[:10]}" if c else "—"),
            ("Número de série", c.get("serie") or "—"),
            ("Cadeia", " › ".join(info.get("chain") or []) or "—"),
        ]
        if info.get("error"):
            rows.append(("Detalhe técnico", html_escape(info["error"][:300])))
        table = "".join(
            f"<tr><td colspan=2 style='padding-top:10px'>{k}</td></tr>" if not v else
            f"<tr><td style='color:gray; padding-right:14px; white-space:nowrap'>{k}</td><td>{v if k in ('Integridade','Criptografia','Identidade') else html_escape(str(v))}</td></tr>"
            for k, v in rows)
        body = QLabel(f"<table cellspacing=2>{table}</table>")
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setWordWrap(True)
        from PySide6.QtWidgets import QScrollArea, QFrame as _QF
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_QF.NoFrame)
        scroll.setWidget(body)
        screen = self.screen().availableGeometry() if self.screen() else None
        max_h = int(screen.height() * 0.45) if screen else 420
        need = body.heightForWidth(580) if body.hasHeightForWidth() else body.sizeHint().height()
        scroll.setMinimumHeight(min(need + 12, max_h))
        lay.addWidget(scroll, 1)
        if not info.get("trusted") and info.get("intact"):
            note = QLabel("Para certificados ICP-Brasil, a identidade é confirmada quando as cadeias da ICP-Brasil "
                          "estão instaladas no Windows (disponíveis no site do ITI).")
            note.setWordWrap(True)
            note.setObjectName("Muted")
            lay.addWidget(note)
        row = QHBoxLayout()
        if on_view_signed and info.get("revision_end"):
            b = QPushButton("Ver versão assinada")
            b.setToolTip("Abre o documento exatamente como estava no momento desta assinatura")
            b.clicked.connect(lambda: (on_view_signed(info), self.accept()))
            row.addWidget(b)
        if on_changes and info.get("revision_end") and info.get("later_changes"):
            b = QPushButton("O que mudou depois desta assinatura")
            b.setToolTip("Compara a versão assinada com a versão atual e destaca cada alteração")
            b.clicked.connect(lambda: (self.accept(), on_changes(info)))
            row.addWidget(b)
        row.addStretch()
        close = QPushButton("Fechar")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)


def html_escape(t):
    import html
    return html.escape(t or "")


class SignaturesDialog(QDialog):
    def __init__(self, parent, results, on_view_signed=None, on_changes=None):
        from . import signing
        super().__init__(parent)
        self.setWindowTitle("Painel de assinaturas")
        self.resize(820, 320)
        self.results, self.on_view_signed, self.on_changes = results, on_view_signed, on_changes
        lay = QVBoxLayout(self)
        if not results:
            lay.addWidget(QLabel("Este documento não possui assinaturas digitais."))
        t = QTableWidget(len(results), 5)
        t.setHorizontalHeaderLabels(["", "Signatário", "Data", "Depois desta assinatura", "Situação"])
        for r, info in enumerate(results):
            lvl, title = signing.status_of(info)
            later = sum(1 for o in results if (o.get("revision_end") or 0) > (info.get("revision_end") or 0))
            after = ("Sem alterações" if not info.get("later_changes") else
                     (f"{later} assinatura(s) e alterações" if later else "Houve alterações"))
            vals = [SIG_SYMBOL[lvl], info["signer"], _fmt_dt(info["time"])[:16], after, title]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (0, 4):
                    it.setForeground(QColor(SIG_COLORS[lvl]))
                t.setItem(r, c, it)
        t.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.setColumnWidth(0, 30)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.cellDoubleClicked.connect(lambda r, c: self._details(r))
        self.table = t
        lay.addWidget(t)
        row = QHBoxLayout()
        note = QLabel("Clique duas vezes em uma assinatura para ver a validação completa.")
        note.setObjectName("Muted")
        row.addWidget(note, 1)
        if on_changes:
            chg = QPushButton("O que mudou depois…")
            chg.setToolTip("Compara a versão assinada selecionada com a versão atual")
            chg.clicked.connect(self._changes)
            row.addWidget(chg)
        det = QPushButton("Detalhes…")
        det.clicked.connect(lambda: self._details(t.currentRow()))
        row.addWidget(det)
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)

    def _details(self, r):
        if 0 <= r < len(self.results):
            SignatureInfoDialog(self, self.results[r], self.on_view_signed, self.on_changes).exec()

    def _changes(self):
        r = self.table.currentRow()
        if not (0 <= r < len(self.results)):
            r = 0 if len(self.results) == 1 else -1
        if r < 0:
            QMessageBox.information(self, "Painel de assinaturas", "Selecione uma assinatura na lista.")
            return
        info = self.results[r]
        if not info.get("later_changes"):
            QMessageBox.information(self, "Painel de assinaturas",
                                    "Nada foi alterado no documento depois desta assinatura.")
            return
        self.accept()
        self.on_changes(info)


# ---------------------------------------------------------------- páginas e documento
class SplitDialog(FormDialog):
    def __init__(self, parent):
        self.mode = combo(["A cada N páginas", "Por intervalos (ex.: 1-3;4-10)", "Por marcadores de nível 1",
                           "Por tamanho máximo (MB)"])
        self.value = line("1")
        super().__init__(parent, "Dividir documento", [("Dividir:", self.mode), ("Valor:", self.value)],
                         ok_text="Dividir")

    def values(self):
        return ["every", "ranges", "bookmarks", "size"][self.mode.currentIndex()], self.value.text()


class WatermarkDialog(FormDialog):
    def __init__(self, parent, page_count):
        self.text = line("CONFIDENCIAL")
        self.image = line(placeholder="(opcional) imagem no lugar do texto")
        b = QPushButton("…")
        b.setFixedWidth(36)
        b.clicked.connect(lambda: self.image.setText(QFileDialog.getOpenFileName(self, "Imagem", "", "Imagens (*.png *.jpg)")[0]))
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.image)
        rl.addWidget(b)
        self.size = spin(60, 8, 300)
        self.angle = spin(45, -90, 90, suffix="°")
        self.opacity = spin(20, 2, 100, suffix=" %")
        self.colorb = ColorButton("#d7373f")
        self.pages = line(placeholder=f"Todas (1-{page_count})")
        super().__init__(parent, "Adicionar marca d'água", [
            ("Texto:", self.text), ("Imagem:", row), ("Tamanho:", self.size), ("Rotação:", self.angle),
            ("Opacidade:", self.opacity), ("Cor:", self.colorb), ("Páginas:", self.pages)], ok_text="Aplicar")


class PageNumberDialog(FormDialog):
    def __init__(self, parent, page_count):
        self.fmt = combo(["Página {n} de {total}", "{n}", "{n}/{total}", "- {n} -", "Fls. {n}", "(sem número)"])
        self.fmt.setEditable(True)
        self.pos = combo(["inferior-centro", "inferior-direita", "inferior-esquerda", "superior-centro",
                          "superior-direita", "superior-esquerda"])
        self.start = spin(1, 1, 99999)
        self.size = spin(10, 5, 48)
        self.header = line(placeholder="Cabeçalho (opcional) – aceita {n} e {total}")
        self.footer = line(placeholder="Rodapé à esquerda (opcional)")
        self.pages = line(placeholder=f"Todas (1-{page_count})")
        super().__init__(parent, "Cabeçalho, rodapé e numeração", [
            ("Formato:", self.fmt), ("Posição:", self.pos), ("Começar em:", self.start), ("Tamanho:", self.size),
            ("Cabeçalho:", self.header), ("Rodapé:", self.footer), ("Páginas:", self.pages)], ok_text="Aplicar",
            intro="Use também para numeração Bates (ex.: formato \"NS-{n}\" e início 1001).")


class ProtectDialog(FormDialog):
    def __init__(self, parent):
        self.user = line(password=True, placeholder="Exigida para abrir (opcional)")
        self.owner = line(password=True, placeholder="Exigida para alterar permissões")
        self.checks = {}
        box = QGroupBox("Permitir")
        bl = QVBoxLayout(box)
        for k, (label, _) in ops.PERM_LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(k in ("print", "print_hq", "copy"))
            self.checks[k] = cb
            bl.addWidget(cb)
        super().__init__(parent, "Proteger com senha", [("Senha de abertura:", self.user),
                                                         ("Senha de permissões:", self.owner), (None, box)],
                         ok_text="Proteger", intro="Criptografia AES de 256 bits.")

    def values(self):
        return self.user.text(), self.owner.text(), [k for k, cb in self.checks.items() if cb.isChecked()]


class RedactSearchDialog(FormDialog):
    def __init__(self, parent):
        self.text = line(placeholder="Palavra ou frase")
        self.preset = combo(["(texto livre)"] + list(ops.PATTERNS))
        self.apply_now = QCheckBox("Aplicar a ocultação imediatamente (irreversível ao salvar)")
        super().__init__(parent, "Localizar e ocultar texto", [("Procurar:", self.text), ("Padrão:", self.preset),
                                                                (None, self.apply_now)], ok_text="Marcar")


class CompressDialog(FormDialog):
    def __init__(self, parent):
        self.level = combo(["Baixa compressão (alta qualidade)", "Média (recomendado)", "Alta compressão (menor arquivo)"])
        from .config import cfg as _cfg
        self.level.setCurrentIndex({"baixa": 0, "media": 1, "alta": 2}.get(_cfg.get("compress_level"), 1))
        super().__init__(parent, "Comprimir PDF", [("Nível:", self.level)], ok_text="Comprimir")

    def value(self):
        return ["baixa", "media", "alta"][self.level.currentIndex()]


class OcrDialog(FormDialog):
    def __init__(self, parent, langs, page_count, default="por"):
        from .config import cfg as _cfg
        langs = list(langs or ["por"])
        if "por" in langs and "eng" in langs:
            langs.append("por+eng")
        default = _cfg.get("ocr_lang") or default
        self.lang = combo(langs, default if default in langs else None)
        self.dpi = combo(["200", "300", "400"], str(_cfg.get("ocr_dpi")))
        self.pages = line(placeholder=f"Todas (1-{page_count})")
        self.force = QCheckBox("Reconhecer também páginas que já possuem texto")
        super().__init__(parent, "Reconhecer texto (OCR)", [("Idioma:", self.lang), ("Resolução (dpi):", self.dpi),
                                                            ("Páginas:", self.pages), (None, self.force)],
                         ok_text="Reconhecer texto",
                         intro=None if langs else "Tesseract OCR não encontrado. Instale-o (com o idioma Português) para usar o OCR.")


class ImageExportDialog(FormDialog):
    def __init__(self, parent, page_count):
        from .config import cfg as _cfg
        self.fmt = combo(["png", "jpg", "tiff"], _cfg.get("image_format"))
        self.dpi = combo(["72", "150", "200", "300", "600"], str(_cfg.get("image_dpi")))
        self.pages = line(placeholder=f"Todas (1-{page_count})")
        super().__init__(parent, "Exportar como imagem", [("Formato:", self.fmt), ("Resolução (dpi):", self.dpi),
                                                          ("Páginas:", self.pages)], ok_text="Exportar")


class PropertiesDialog(QDialog):
    FIELDS = [("title", "Título"), ("author", "Autor"), ("subject", "Assunto"), ("keywords", "Palavras-chave"),
              ("creator", "Aplicativo"), ("producer", "Produtor")]

    def __init__(self, parent, doc, path, size):
        super().__init__(parent)
        self.setWindowTitle("Propriedades do documento")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        md = doc.metadata or {}
        self.edits = {}
        for k, label in self.FIELDS:
            e = line(md.get(k) or "")
            self.edits[k] = e
            form.addRow(label + ":", e)
        info = [("Arquivo:", path or "(não salvo)"), ("Tamanho:", f"{size / 1024:.1f} KB"),
                ("Páginas:", str(doc.page_count)), ("Versão PDF:", md.get("format", "")),
                ("Criado em:", _pdfdate(md.get("creationDate"))), ("Modificado em:", _pdfdate(md.get("modDate"))),
                ("Tamanho da página:", f"{doc[0].rect.width / 72 * 25.4:.0f} × {doc[0].rect.height / 72 * 25.4:.0f} mm" if doc.page_count else ""),
                ("Criptografia:", md.get("encryption") or "Nenhuma"),
                ("Formulário:", "Sim" if doc.is_form_pdf else "Não"),
                ("Fontes:", ", ".join(sorted({f[3] for p in doc for f in p.get_fonts()}))[:300])]
        for a, b in info:
            lb = QLabel(b)
            lb.setWordWrap(True)
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(a, lb)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Salvar metadados")
        bb.button(QDialogButtonBox.Cancel).setText("Fechar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def metadata(self):
        return {k: e.text() for k, e in self.edits.items()}


def _pdfdate(s):
    if not s or len(s) < 10:
        return s or ""
    s = s.replace("D:", "")
    return f"{s[6:8]}/{s[4:6]}/{s[0:4]} {s[8:10]}:{s[10:12]}"


class FormFillDialog(QDialog):
    def __init__(self, parent, fields):
        super().__init__(parent)
        self.setWindowTitle("Preencher formulário")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.table = QTableWidget(len(fields), 3)
        self.table.setHorizontalHeaderLabels(["Campo", "Tipo", "Valor"])
        self.fields = fields
        self.editors = []
        for r, f in enumerate(fields):
            self.table.setItem(r, 0, QTableWidgetItem(f"{f['name']} (p.{f['page'] + 1})"))
            self.table.setItem(r, 1, QTableWidgetItem(f["type_name"]))
            if f["type"] in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                ed = QCheckBox()
                ed.setChecked(f["value"] not in (None, "", "Off", False))
            elif f["type"] in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
                ed = combo([str(c if not isinstance(c, (list, tuple)) else c[-1]) for c in (f["choices"] or [])], str(f["value"] or ""))
            elif f["type"] == pymupdf.PDF_WIDGET_TYPE_TEXT:
                ed = line(str(f["value"] or ""))
            else:
                ed = QLabel("—")
            self.editors.append(ed)
            self.table.setCellWidget(r, 2, ed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lay.addWidget(self.table)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aplicar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        out = []
        for f, ed in zip(self.fields, self.editors):
            if isinstance(ed, QCheckBox):
                out.append((f, ed.isChecked()))
            elif isinstance(ed, QComboBox):
                out.append((f, ed.currentText()))
            elif isinstance(ed, QLineEdit):
                out.append((f, ed.text()))
        return out


class HtmlDialog(QDialog):
    def __init__(self, parent, title, html, save_name=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        tb.setHtml(html)
        lay.addWidget(tb)
        row = QHBoxLayout()
        row.addStretch()
        if save_name:
            b = QPushButton("Salvar relatório…")
            b.clicked.connect(lambda: self._save(html, save_name))
            row.addWidget(b)
        c = QPushButton("Fechar")
        c.clicked.connect(self.accept)
        row.addWidget(c)
        lay.addLayout(row)

    def _save(self, html, name):
        fn, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", name, "HTML (*.html)")
        if fn:
            with open(fn, "w", encoding="utf-8") as f:
                f.write(f"<meta charset='utf-8'>{html}")


class PreferencesDialog(FormDialog):
    def __init__(self, parent, settings, langs):
        from .config import cfg as _cfg
        self.author = line(_cfg.get("author"))
        self.ocr = combo(langs or ["por"], settings.value("ocr_lang", "por"))
        self.zoom = combo(["Ajustar largura", "Ajustar página", "100%"], settings.value("default_zoom", "Ajustar largura"))
        self.tess = line(settings.value("tessdata", ""), "Pasta tessdata (opcional)")
        super().__init__(parent, "Preferências", [("Nome do autor (comentários):", self.author),
                                                   ("Idioma do OCR:", self.ocr), ("Zoom inicial:", self.zoom),
                                                   ("Tessdata:", self.tess)], ok_text="Salvar")


class VersionsDialog(QDialog):
    """Versões anteriores de um arquivo (cópias feitas ao salvar por cima)."""

    def __init__(self, parent, name, versions):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.setWindowTitle(f"Versões anteriores — {name}")
        self.resize(520, 380)
        self.chosen = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Cópias guardadas automaticamente cada vez que o arquivo foi salvo por cima (até 30 dias):"))
        self.list = QListWidget()
        for fp, when, size in versions:
            it = QListWidgetItem(f"{when:%d/%m/%Y %H:%M:%S}   ·   {size / 1048576:.2f} MB")
            it.setData(Qt.UserRole, fp)
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        b_open = QPushButton("Abrir em nova aba")
        b_rest = QPushButton("Restaurar esta versão")
        b_rest.setDefault(True)
        b_close = QPushButton("Fechar")
        row.addWidget(b_open); row.addStretch(); row.addWidget(b_rest); row.addWidget(b_close)
        lay.addLayout(row)
        b_open.clicked.connect(lambda: self._pick("abrir"))
        b_rest.clicked.connect(lambda: self._pick("restaurar"))
        self.list.itemDoubleClicked.connect(lambda *_: self._pick("restaurar"))
        b_close.clicked.connect(self.reject)

    def _pick(self, action):
        it = self.list.currentItem()
        if it:
            self.chosen = (it.data(Qt.UserRole), action)
            self.accept()


class ReplaceDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
        self.setWindowTitle("Localizar e substituir")
        lay = QFormLayout(self)
        self.find = QLineEdit(); self.repl = QLineEdit()
        self.case = QCheckBox("Diferenciar maiúsculas e minúsculas")
        self.word = QCheckBox("Somente palavra inteira")
        lay.addRow("Localizar:", self.find)
        lay.addRow("Substituir por:", self.repl)
        lay.addRow(self.case); lay.addRow(self.word)
        info = QLabel("Mantém a fonte, o tamanho e a cor de cada trecho; o resto da linha acompanha a nova largura.")
        info.setWordWrap(True)
        lay.addRow(info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Substituir tudo")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def values(self):
        return self.find.text(), self.repl.text(), self.case.isChecked(), self.word.isChecked()


class ScaleDialog(QDialog):
    """Escala das medidas: escala da planta (1:N) ou calibrar desenhando uma medida conhecida."""

    def __init__(self, parent, current):
        super().__init__(parent)
        from PySide6.QtWidgets import QRadioButton, QComboBox, QDialogButtonBox
        self.setWindowTitle("Escala das medidas")
        self.calibrate = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Escala atual: {current.get('label', '')}"))
        self.r_paper = QRadioButton("Tamanho real do papel"); lay.addWidget(self.r_paper)
        row = QHBoxLayout()
        self.r_plan = QRadioButton("Escala da planta   1 :"); row.addWidget(self.r_plan)
        self.n = QSpinBox(); self.n.setRange(1, 100000); self.n.setValue(100); row.addWidget(self.n)
        row.addStretch(); lay.addLayout(row)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Unidade:"))
        self.unit = QComboBox(); self.unit.addItems(["m", "cm", "mm", "km"]); row2.addWidget(self.unit); row2.addStretch()
        lay.addLayout(row2)
        self.r_cal = QRadioButton("Calibrar: desenhar sobre uma medida conhecida (ex.: uma parede com cota)")
        lay.addWidget(self.r_cal)
        self.r_plan.setChecked(True)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self):
        self.calibrate = self.r_cal.isChecked()
        self.accept()

    def result_scale(self):
        per_unit = {"m": 1.0, "cm": 100.0, "mm": 1000.0, "km": 0.001}[self.unit.currentText()]
        paper_m_per_pt = 0.0254 / 72
        if self.r_paper.isChecked():
            return {"factor": paper_m_per_pt * per_unit, "unit": self.unit.currentText(), "label": "tamanho real do papel"}
        n = self.n.value()
        return {"factor": paper_m_per_pt * n * per_unit, "unit": self.unit.currentText(), "label": f"1:{n}"}


class PaymentsDialog(QDialog):
    """Boletos, Pix e chaves de NF-e encontrados: conferência dos dígitos e botões de copiar."""

    def __init__(self, parent, items, on_goto):
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea, QFrame, QGridLayout, QApplication, QDialogButtonBox
        self.setWindowTitle("Boletos, Pix e notas fiscais")
        self.resize(640, 560)
        root = QVBoxLayout(self)
        ok = sum(1 for i in items if i.ok)
        head = QLabel(f"{len(items)} item(ns) encontrado(s)" + ("" if ok == len(items) else
                      f" — <b style='color:#d7373f'>{len(items) - ok} com problema</b>"))
        root.addWidget(head)
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        for it in items:
            card = QFrame()
            card.setObjectName("PayCard")
            fg = "#2d9d78" if it.ok else "#d7373f"
            card.setStyleSheet(f"QFrame#PayCard{{border:1px solid {fg}; border-radius:8px;}}")
            g = QGridLayout(card)
            t = QLabel(f"<span style='color:{fg}; font-size:15px'>{'✔' if it.ok else '⚠'}</span> "
                       f"<b>{it.title}</b> <span style='color:gray'>· página {it.page + 1}</span>")
            g.addWidget(t, 0, 0, 1, 2)
            r = 1
            if not it.ok:
                pr = QLabel(it.problem)
                pr.setWordWrap(True)
                pr.setStyleSheet("color:#d7373f")
                g.addWidget(pr, r, 0, 1, 2)
                r += 1
            elif it.source == "texto e código":
                g.addWidget(QLabel("<span style='color:#2d9d78'>Texto impresso confere com o "
                                   + ("QR Code" if it.kind == "pix" else "código de barras") + "</span>"), r, 0, 1, 2)
                r += 1
            for k, v in it.details:
                a = QLabel(k + ":")
                a.setStyleSheet("color:gray")
                b = QLabel(v)
                b.setWordWrap(True)
                b.setTextInteractionFlags(Qt.TextSelectableByMouse)
                g.addWidget(a, r, 0, Qt.AlignTop)
                g.addWidget(b, r, 1)
                r += 1
            row = QHBoxLayout()
            if it.ok:
                cp = QPushButton(it.copy_label)
                cp.clicked.connect(lambda _=False, it=it, cp=cp: (QApplication.clipboard().setText(it.copy),
                                                                  cp.setText("Copiado ✔")))
                row.addWidget(cp)
            go = QPushButton(f"Ir para a página {it.page + 1}")
            go.clicked.connect(lambda _=False, it=it: (on_goto(it.page, it.rect), self.accept()))
            row.addWidget(go)
            row.addStretch()
            g.addLayout(row, r, 0, 1, 2)
            g.setColumnStretch(1, 1)
            col.addWidget(card)
        col.addStretch()
        area.setWidget(inner)
        root.addWidget(area, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
