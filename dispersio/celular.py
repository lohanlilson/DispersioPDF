"""Continuar no celular (e o contrário), pela rede Wi-Fi de casa/escritório — sem nuvem e sem cabo.

O computador mostra um QR. No app Dispersio PDF do celular, "Continuar do computador" lê o QR, baixa o documento
(com as alterações ainda não salvas) e abre na mesma página. "Enviar para o computador" faz o contrário: o celular
manda o documento aberto e o computador abre na página em que ele estava.

Só funciona enquanto a janela do QR estiver aberta, com um código aleatório no endereço; os dois aparelhos precisam
estar na mesma rede. Lendo o QR com a câmera comum, abre uma página simples para baixar o PDF.
"""
import html
import json
import os
import secrets
import socket
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout

MAX_UPLOAD = 400 * 1024 * 1024
TIMEOUT_S = 15 * 60


def lan_ip():
    """Endereço deste computador na rede local (o que o celular consegue alcançar)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))        # não envia nada: só escolhe a interface de saída
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


class Link(QObject):
    """Servidor temporário na rede local. received(caminho, página) quando o celular manda um documento."""
    received = Signal(str, int)
    downloaded = Signal()

    def __init__(self, data=None, name="Documento.pdf", page=0):
        super().__init__()
        self.data, self.name, self.page = data, name, page
        self.token = secrets.token_urlsafe(12)
        self.server = None
        self.started = time.time()

    @property
    def url(self):
        return f"http://{lan_ip()}:{self.server.server_address[1]}/{self.token}"

    def start(self, port=0):
        link = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok(self, path):
                parts = urllib.parse.urlsplit(path)
                segs = [p for p in parts.path.split("/") if p]
                if not segs or not secrets.compare_digest(segs[0], link.token):
                    self.send_error(404)
                    return None, None
                return (segs[1] if len(segs) > 1 else ""), urllib.parse.parse_qs(parts.query)

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                what, _q = self._ok(self.path)
                if what is None:
                    return
                if what == "info":
                    self._send(200, json.dumps({"name": link.name if link.data else "", "page": link.page,
                                                "has_doc": bool(link.data), "app": "Dispersio PDF"}).encode(),
                               "application/json; charset=utf-8")
                elif what == "doc.pdf" and link.data:
                    self._send(200, link.data, "application/pdf")
                    link.downloaded.emit()
                elif what == "":
                    nm = html.escape(link.name)
                    body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                            f"<title>Dispersio PDF</title><body style='font-family:sans-serif;padding:24px'>"
                            f"<h2>Dispersio PDF</h2>"
                            + (f"<p><a href='doc.pdf' download='{nm}' style='font-size:20px'>Baixar “{nm}”</a></p>"
                               if link.data else "<p>Nenhum documento oferecido.</p>")
                            + "<p style='color:#666'>Com o app Dispersio PDF no celular, use “Continuar do computador” para "
                              "abrir direto na mesma página.</p></body>").encode()
                    self._send(200, body, "text/html; charset=utf-8")
                else:
                    self.send_error(404)

            def do_POST(self):
                what, q = self._ok(self.path)
                if what is None:
                    return
                if what != "upload":
                    self.send_error(404)
                    return
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > MAX_UPLOAD:
                    self.send_error(413)
                    return
                data = self.rfile.read(n)
                if not data.startswith(b"%PDF"):
                    self.send_error(415)
                    return
                name = os.path.basename((q.get("name") or ["Do celular.pdf"])[0]) or "Do celular.pdf"
                if not name.lower().endswith(".pdf"):
                    name += ".pdf"
                name = "".join(c for c in name if c not in '<>:"/\\|?*')
                folder = os.path.join(tempfile.gettempdir(), "Dispersio PDF - do celular")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, name)
                base, ext = os.path.splitext(path)
                k = 2
                while os.path.exists(path):
                    path = f"{base} ({k}){ext}"
                    k += 1
                with open(path, "wb") as f:
                    f.write(data)
                try:
                    page = int((q.get("page") or ["0"])[0])
                except ValueError:
                    page = 0
                self._send(200, b'{"ok":true}', "application/json")
                link.received.emit(path, page)

        self.server = ThreadingHTTPServer(("0.0.0.0", port), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def qr_pixmap(text, size=260):
    import numpy as np
    import zxingcpp
    img = np.ascontiguousarray(np.array(zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode).to_image(scale=1)))
    h, w = img.shape
    q = QImage(img.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(q.scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation))


class PhoneDialog(QDialog):
    """Mostra o QR e espera o celular (baixar o documento atual ou mandar o dele)."""

    def __init__(self, win, data=None, name="", page=0):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Continuar no celular")
        self.link = Link(data, name or "Documento.pdf", page).start()
        self.link.received.connect(self._received)
        self.link.downloaded.connect(lambda: self.status.setText("✓ O celular baixou o documento."))
        lay = QVBoxLayout(self)
        head = QLabel("<b>No app Dispersio PDF do celular</b>, toque em <b>Continuar do computador</b> "
                      + ("e aponte para o código: o documento abre na mesma página." if data else "e aponte para o código.")
                      + "<br>Para mandar o documento do celular para cá, abra-o no celular e use "
                        "<b>⋮ › Enviar para o computador</b>.")
        head.setWordWrap(True)
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)
        qr = QLabel()
        qr.setAlignment(Qt.AlignCenter)
        qr.setPixmap(qr_pixmap(self.link.url))
        lay.addWidget(qr)
        addr = QLabel(f"<span style='color:#666'>{self.link.url}</span>")
        addr.setAlignment(Qt.AlignCenter)
        addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(addr)
        tip = QLabel("O celular e o computador precisam estar na mesma rede Wi-Fi. Se o Windows perguntar sobre o "
                     "firewall, permita em redes privadas. A ligação fica aberta só enquanto esta janela estiver aberta "
                     "(até 15 minutos).")
        tip.setWordWrap(True)
        tip.setObjectName("Muted")
        lay.addWidget(tip)
        self.status = QLabel("Esperando o celular…")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        QTimer.singleShot(TIMEOUT_S * 1000, self.reject)

    def _received(self, path, page):
        self.status.setText(f"✓ Recebido do celular: {os.path.basename(path)}")
        self.win.open_at(path, page)

    def done(self, r):
        self.link.stop()
        super().done(r)
