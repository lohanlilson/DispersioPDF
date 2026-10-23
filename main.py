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


def send_to_running(paths):
    """Se o programa já está aberto, entrega os arquivos para ele e retorna True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps(paths).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


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

    paths = [os.path.abspath(a) for a in sys.argv[1:] if os.path.exists(a)]
    if send_to_running(paths):
        return 0

    from lumenpdf.mainwindow import MainWindow
    win = MainWindow()
    from lumenpdf import errors
    errors.install(win)

    server = QLocalServer()
    QLocalServer.removeServer(SERVER)
    server.listen(SERVER)

    def incoming():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            try:
                files = json.loads(bytes(conn.readAll()).decode("utf-8") or "[]")
            except ValueError:
                files = []
            for f in files:
                win.open_path(f)
            win.bring_to_front()
        conn.readyRead.connect(read)
    server.newConnection.connect(incoming)

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
    if not paths and cfg.get("startup") == "last_session":
        session = cfg.qs.value("session", []) or []
        for p in ([session] if isinstance(session, str) else session):
            if os.path.exists(p):
                win.open_path(p)
    import threading
    from lumenpdf import ops
    threading.Thread(target=ops.system_fonts, daemon=True).start()  # prepara a edição de texto com fontes originais
    for p in paths:
        win.open_path(p)
    QTimer.singleShot(1200, win.check_default_app)
    QTimer.singleShot(4000, win.updater.auto_check)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
