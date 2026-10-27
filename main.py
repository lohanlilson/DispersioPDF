"""Lumen PDF — leitor e editor de PDF completo (PySide6 + PyMuPDF)."""
import json
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from lumenpdf import APP_NAME, APP_ID, __version__, resource

SERVER = f"{APP_ID}-{os.environ.get('USERNAME') or os.environ.get('USER') or 'user'}"


def parse_args(argv):
    """Interpreta a linha de comando.
    LumenPDF.exe arquivo.pdf …            abre
    LumenPDF.exe /p arquivo.pdf …         imprime na impressora padrão, sem janela (Outlook, botão direito)
    LumenPDF.exe /pt arquivo.pdf "Impressora" [driver] [porta]   imprime numa impressora específica
    """
    cmd, files, printer = "open", [], ""
    args = list(argv[1:])
    i = 0
    while i < len(args):
        a = args[i]
        low = a.lower()
        if low in ("/p", "-p", "--print", "/print"):
            cmd = "print"
        elif low in ("/pt", "-pt", "--printto", "/printto"):
            cmd = "print"
            rest = list(args[i + 1:])
            if rest:
                files.append(os.path.abspath(rest[0]))
                printer = rest[1] if len(rest) > 1 else ""
            break
        elif low.startswith(("--", "/")) and not os.path.exists(a):
            pass  # outras opções
        elif os.path.exists(a):
            files.append(os.path.abspath(a))
        i += 1
    return dict(cmd=cmd, files=files, printer=printer)


def send_to_running(msg, wait_ms=400):
    """Entrega o pedido à instância já aberta e espera a confirmação dela. Retorna True se foi recebido."""
    import time
    sock = QLocalSocket()
    sock.connectToServer(SERVER)
    if not sock.waitForConnected(wait_ms):
        sock.abort()
        return False
    sock.write(json.dumps(msg).encode("utf-8") + b"\n")
    sock.flush()
    ok = False
    if sock.bytesToWrite():
        sock.waitForBytesWritten(3000)
    reply = bytearray()
    t0 = time.time()
    while time.time() - t0 < 20:  # a instância principal pode estar ocupada imprimindo
        if sock.bytesAvailable() or sock.waitForReadyRead(300):
            reply.extend(bytes(sock.readAll()))
            if b"ok" in reply:
                ok = True
                break
        if sock.state() == QLocalSocket.UnconnectedState:
            break
    sock.abort()  # nunca fica preso esperando o outro lado
    return ok


def become_server_or_forward(msg):
    """Garante uma única instância, mesmo quando o Windows abre vários processos ao mesmo tempo
    (ex.: “Imprimir” com 30 PDFs selecionados). Retorna o trava (QLockFile) se esta instância for a principal."""
    import time
    from PySide6.QtCore import QLockFile, QDir
    lock = QLockFile(os.path.join(QDir.tempPath(), SERVER + ".lock"))
    lock.setStaleLockTime(0)
    deadline = time.time() + 15
    while True:
        if send_to_running(msg):
            return None
        if lock.tryLock(100):
            return lock
        if time.time() > deadline:
            lock.removeStaleLockFile()
            if lock.tryLock(100):
                return lock
            return None
        time.sleep(0.2)


def app_icon():
    """Ícone em vários tamanhos a partir do PNG (não depende do plugin de .ico do Qt)."""
    from PySide6.QtGui import QPixmap
    icon = QIcon()
    big = QPixmap(resource("assets", "logo.png"))  # nova marca
    if not big.isNull():
        for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
            icon.addPixmap(big.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    if icon.isNull():
        icon = QIcon(resource("assets", "lumenpdf.ico"))
    return icon


def main():
    if "--orient-scan" in sys.argv:  # processo auxiliar: posição das páginas por OCR (sem janela)
        import json
        from lumenpdf import ops
        i = sys.argv.index("--orient-scan")
        src, out = sys.argv[i + 1], sys.argv[i + 2]
        pwd = sys.stdin.readline().rstrip("\n") or None
        with open(src, "rb") as f:
            fixes = ops.orientation_fixes_bytes(f.read(), pwd, int(sys.argv[i + 3]), sys.argv[i + 4])
        with open(out, "w") as f:
            json.dump({str(k): v for k, v in fixes.items()}, f)
        return 0
    if "--run-update" in sys.argv:  # auxiliar da atualização automática (sem janela, sem trava de instância)
        from lumenpdf.updater import run_update_helper
        return run_update_helper(sys.argv)
    if "--selftest" in sys.argv:  # usado pelo build para conferir o executável gerado
        from lumenpdf import selftest
        i = sys.argv.index("--selftest")
        return selftest.run(sys.argv[i + 1] if len(sys.argv) > i + 1 else None)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform == "win32":
        import ctypes
        # ícone próprio na barra de tarefas e mutex usado pelo instalador para detectar o programa aberto
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.App")
        main._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "LumenPDF_Running")
        if "--set-default" in sys.argv:  # chamado pelo instalador
            from PySide6.QtCore import QSettings
            from lumenpdf import system
            QSettings(APP_ID, APP_ID).setValue("default_asked", "true")  # o programa não pergunta de novo
            system.open_default_apps_settings()
            return 0
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ID)
    app.setWindowIcon(app_icon())

    req = parse_args(sys.argv)
    paths = req["files"]
    headless = req["cmd"] == "print"
    main._lock = become_server_or_forward(req)
    if main._lock is None:
        return 0

    from lumenpdf.mainwindow import MainWindow
    win = MainWindow()
    from lumenpdf import errors
    errors.install(win)

    server = QLocalServer()
    QLocalServer.removeServer(SERVER)
    server.listen(SERVER)
    state = {"shown": False}

    def show_window():
        if state["shown"]:
            win.bring_to_front()
            return
        state["shown"] = True
        _show(win, app)

    def handle(msg):
        if isinstance(msg, list):  # formato antigo
            msg = dict(cmd="open", files=msg, printer="")
        if msg.get("cmd") == "print":
            win.enqueue_print(msg.get("files", []), msg.get("printer", ""))
            return
        show_window()
        for f in msg.get("files", []):
            win.open_path(f)

    def incoming():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            buf = bytearray()

            def read(conn=conn, buf=buf):
                buf.extend(bytes(conn.readAll()))
                if b"\n" not in buf or getattr(conn, "_handled", False):
                    return
                conn._handled = True
                line = bytes(buf).split(b"\n", 1)[0]
                conn.write(b"ok\n")  # confirma o recebimento antes de processar
                conn.flush()
                try:
                    msg = json.loads(line.decode("utf-8") or "{}")
                except ValueError:
                    return
                QTimer.singleShot(0, lambda m=msg: handle(m))
            conn.readyRead.connect(read)
            conn.disconnected.connect(conn.deleteLater)
            if conn.bytesAvailable():
                read()
    server.newConnection.connect(incoming)

    if headless:
        # só imprime: sem janela; encerra sozinho quando a fila acabar (a menos que o usuário abra um PDF)
        def idle():
            if not state["shown"]:
                QTimer.singleShot(5000, lambda: (not state["shown"] and not getattr(win, "_printing", False)
                                                 and not getattr(win, "_print_queue", None) and app.quit()))
        win.on_print_idle = idle
        win.enqueue_print(paths, req["printer"])
        return app.exec()

    state["shown"] = True
    _show(win, app)
    from lumenpdf.config import cfg
    if not paths and cfg.get("startup") == "last_session":
        session = cfg.qs.value("session", []) or []
        for p in ([session] if isinstance(session, str) else session):
            if os.path.exists(p):
                win.open_path(p)
    for p in paths:
        win.open_path(p)
    QTimer.singleShot(1200, win.check_default_app)
    QTimer.singleShot(4000, win.updater.auto_check)
    return app.exec()


def _show(win, app):
    from lumenpdf.config import cfg
    win.setWindowIcon(app.windowIcon())
    mode = cfg.get("window_mode")
    if mode == "last" and cfg.qs.value("geometry") is not None:
        win.restoreGeometry(cfg.qs.value("geometry"))
        win.showMaximized() if cfg.qs.value("was_maximized", "true") == "true" else win.show()
    elif mode == "normal":
        win.resize(1280, 820)
        win.show()
    else:
        win.showMaximized()
    from lumenpdf import theme as _theme
    _theme.style_titlebar(win)
    try:  # tema "Seguir o Windows"
        app.styleHints().colorSchemeChanged.connect(win._on_system_theme)
    except Exception:
        pass
    import threading
    from lumenpdf import ops
    threading.Thread(target=ops.system_fonts, daemon=True).start()  # prepara a edição de texto com fontes originais


if __name__ == "__main__":
    sys.exit(main())
