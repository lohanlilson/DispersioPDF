"""Impressora virtual "Dispersio PDF" (como a do PDF24): qualquer programa imprime nela e o documento vira PDF
na fila do Dispersio, onde dá para juntar, salvar, abrir, imprimir de verdade ou enviar por e-mail.

Como funciona (sem driver próprio): usa o driver "Microsoft Print To PDF" do Windows com uma porta local que é
um named pipe. Um agente leve (DispersioPDF.exe --printer-agent), iniciado com o Windows, escuta o pipe:
cada trabalho de impressão chega como um PDF completo, é guardado na pasta da fila e entregue ao programa.
"""
import os
import re
import subprocess
import sys
import time
from datetime import datetime

PRINTER = "Dispersio PDF"
PIPE = r"\\.\pipe\DispersioPDF"
DRIVER = "Microsoft Print To PDF"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "DispersioPDF-Impressora"
AGENT_MUTEX = "DispersioPDF_Impressora"
STOP_EVENT = "DispersioPDF_Impressora_Parar"
IS_WINDOWS = sys.platform == "win32"


def exe_path():
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])


def queue_dir():
    """Pasta da fila (por usuário). Os PDFs ficam aqui até a pessoa tirar da fila."""
    base = os.environ.get("DISPERSIO_PRINTER_TEST_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Dispersio PDF", "Impressora")
    os.makedirs(base, exist_ok=True)
    return base


def queue_files():
    d = queue_dir()
    fs = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".pdf")]
    return sorted(fs, key=os.path.getmtime)


def title_of(path):
    """Nome mostrado na fila: o nome do documento impresso (sem a data do arquivo)."""
    base = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"^\d{8}-\d{6}-\d+\s+", "", base)


def safe_name(title):
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or "").strip(" .")
    t = re.sub(r"\s+", " ", t)
    for suffix in (" - Microsoft Word", " - Word", " - Excel", " - Bloco de Notas", " - Notepad"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    t = os.path.splitext(t)[0] if t.lower().endswith((".docx", ".doc", ".xlsx", ".xls", ".txt", ".pdf", ".pptx")) else t
    return (t or "Documento")[:80]


# ---------------------------------------------------------------- instalação (requer administrador)
def is_installed():
    if not IS_WINDOWS:
        return False
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL
        return any(p[2] == PRINTER for p in win32print.EnumPrinters(flags, None, 1))
    except Exception:
        return False


def _ps(script, timeout=300):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def install():
    """Cria a porta, a impressora e o início automático do agente. Retorna (ok, mensagem)."""
    if not IS_WINDOWS:
        return False, "A impressora virtual existe só no Windows."
    exe = exe_path()
    script = f"""
$ErrorActionPreference = 'Stop'
if (-not (Get-PrinterDriver -Name '{DRIVER}' -ErrorAction SilentlyContinue)) {{
  Enable-WindowsOptionalFeature -Online -FeatureName 'Printing-PrintToPDFServices-Features' -All -NoRestart | Out-Null
  Start-Sleep 3
}}
if (-not (Get-PrinterDriver -Name '{DRIVER}' -ErrorAction SilentlyContinue)) {{ throw 'O driver Microsoft Print To PDF não está disponível neste Windows.' }}
if (-not (Get-PrinterPort -Name '{PIPE}' -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name '{PIPE}' }}
if (-not (Get-Printer -Name '{PRINTER}' -ErrorAction SilentlyContinue)) {{
  Add-Printer -Name '{PRINTER}' -DriverName '{DRIVER}' -PortName '{PIPE}'
}}
Set-Printer -Name '{PRINTER}' -Comment 'Imprime qualquer documento em PDF e manda para a fila do Dispersio PDF'
New-ItemProperty -Path 'HKLM:\\{RUN_KEY}' -Name '{RUN_VALUE}' -Value '"{exe}" --printer-agent' -PropertyType String -Force | Out-Null
'ok'
"""
    try:
        rc, out = _ps(script)
    except Exception as e:
        return False, str(e)
    return (rc == 0 and is_installed()), out.strip()


def uninstall():
    if not IS_WINDOWS:
        return True, ""
    stop_agent()
    script = f"""
Remove-Printer -Name '{PRINTER}' -ErrorAction SilentlyContinue
for ($i = 0; $i -lt 10; $i++) {{
  if (-not (Get-PrinterPort -Name '{PIPE}' -ErrorAction SilentlyContinue)) {{ break }}
  try {{ Remove-PrinterPort -Name '{PIPE}' -ErrorAction Stop; break }} catch {{ Start-Sleep 2 }}
}}
Remove-ItemProperty -Path 'HKLM:\\{RUN_KEY}' -Name '{RUN_VALUE}' -ErrorAction SilentlyContinue
'ok'
"""
    try:
        rc, out = _ps(script)
    except Exception as e:
        return False, str(e)
    return not is_installed(), out.strip()


def run_elevated(arg):
    """Roda DispersioPDF.exe <arg> como administrador (o Windows pede a permissão) e espera terminar.
    Retorna o código de saída, ou None se a pessoa recusou a permissão."""
    import ctypes
    from ctypes import wintypes

    class SEI(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
    exe = exe_path()
    params = arg if getattr(sys, "frozen", False) else f'"{os.path.abspath(sys.argv[0])}" {arg}'
    sei = SEI(cbSize=ctypes.sizeof(SEI), fMask=0x40, lpVerb="runas", lpFile=exe, lpParameters=params, nShow=0)
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return None
    ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(sei.hProcess)
    return code.value


def cli(argv):
    """--install-printer / --uninstall-printer (chamados pelo instalador ou com permissão de administrador)."""
    if "--install-printer" in argv:
        ok, msg = install()
        _log(f"instalar: {ok} {msg}")
        if ok and "--no-agent" not in argv:
            start_agent()
        return 0 if ok else 1
    ok, msg = uninstall()
    _log(f"remover: {ok} {msg}")
    return 0 if ok else 1


def _log(msg):
    try:
        with open(os.path.join(queue_dir(), "impressora.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ---------------------------------------------------------------- agente
def agent_running():
    if not IS_WINDOWS:
        return False
    import ctypes
    h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, AGENT_MUTEX)  # SYNCHRONIZE
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def start_agent():
    """Inicia o agente (sem janela) se a impressora estiver instalada e ele ainda não estiver rodando."""
    if not IS_WINDOWS or agent_running() or not is_installed():
        return
    args = [exe_path(), "--printer-agent"] if getattr(sys, "frozen", False) else \
        [sys.executable, os.path.abspath(sys.argv[0]), "--printer-agent"]
    subprocess.Popen(args, close_fds=True, creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_PROCESS_GROUP


def stop_agent():
    """Pede ao agente para encerrar (ex.: antes de remover a impressora)."""
    if not IS_WINDOWS:
        return
    import ctypes
    h = ctypes.windll.kernel32.OpenEventW(0x0002, False, STOP_EVENT)  # EVENT_MODIFY_STATE
    if h:
        ctypes.windll.kernel32.SetEvent(h)
        ctypes.windll.kernel32.CloseHandle(h)
        try:  # desbloqueia a espera por uma conexão
            import win32file
            win32file.CloseHandle(win32file.CreateFile(PIPE, win32file.GENERIC_WRITE, 0, None,
                                                       win32file.OPEN_EXISTING, 0, None))
        except Exception:
            pass


def _job_info(started):
    """Nome do documento e usuário do trabalho que está sendo impresso agora."""
    try:
        import win32print
        h = win32print.OpenPrinter(PRINTER)
        try:
            jobs = win32print.EnumJobs(h, 0, 50, 1)
        finally:
            win32print.ClosePrinter(h)
        printing = [j for j in jobs if j.get("Status", 0) & 0x10] or jobs  # JOB_STATUS_PRINTING
        if printing:
            j = printing[0]
            return j.get("pDocument") or "", j.get("pUserName") or ""
    except Exception:
        pass
    return "", ""


def _deliver(path, title):
    """Manda o PDF para o Dispersio aberto; se não estiver aberto, abre o programa já com a fila."""
    if os.environ.get("DISPERSIO_PRINTER_TEST_DIR"):
        return  # teste automatizado: só grava o arquivo
    msg = {"cmd": "printed", "files": [path], "title": title}
    send = _SEND
    if send is not None:
        try:
            if send(msg, wait_ms=800):
                return
        except Exception:
            pass
    args = [exe_path(), "--printed", path] if getattr(sys, "frozen", False) else \
        [sys.executable, os.path.abspath(sys.argv[0]), "--printed", path]
    subprocess.Popen(args, close_fds=True, creationflags=0x00000008 | 0x00000200)


_SEND = None


def agent_main(send=None):
    """Laço do agente: cada conexão no pipe é um trabalho de impressão (o PDF inteiro).
    send(msg, wait_ms) entrega o pedido ao Dispersio aberto (main.send_to_running)."""
    global _SEND
    _SEND = send
    if not IS_WINDOWS:
        return 1
    import ctypes
    import pywintypes
    import win32file
    import win32pipe
    import win32security
    k32 = ctypes.windll.kernel32
    mutex = k32.CreateMutexW(None, False, AGENT_MUTEX)
    if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS: já existe um agente
        return 0
    stop = k32.CreateEventW(None, True, False, STOP_EVENT)
    try:
        from PySide6.QtCore import QCoreApplication
        _app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # noqa: F841 (QLocalSocket)
    except Exception:
        pass
    me = (os.environ.get("USERNAME") or "").lower()
    # SYSTEM e administradores (spooler) e o próprio usuário podem escrever; os demais só leem
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;OW)(A;;GRGW;;;AU)", win32security.SDDL_REVISION_1)
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    _log("agente iniciado")
    seq = 0
    while True:
        try:
            h = win32pipe.CreateNamedPipe(PIPE, win32pipe.PIPE_ACCESS_INBOUND,
                                          win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT,
                                          win32pipe.PIPE_UNLIMITED_INSTANCES, 1 << 16, 1 << 16, 0, sa)
        except pywintypes.error as e:
            # ex.: outro usuário conectado ao mesmo tempo já atende a impressora
            if not getattr(agent_main, "_warned", False):
                _log(f"não foi possível criar o pipe: {e}")
                agent_main._warned = True
            if k32.WaitForSingleObject(stop, 30000) == 0:
                break
            continue
        try:
            win32pipe.ConnectNamedPipe(h, None)
        except pywintypes.error:
            pass
        if k32.WaitForSingleObject(stop, 0) == 0:
            win32file.CloseHandle(h)
            break
        doc, user = _job_info(time.time())
        data = bytearray()
        while True:
            try:
                _, chunk = win32file.ReadFile(h, 1 << 16)
            except pywintypes.error:
                break
            if not chunk:
                break
            data += chunk
        try:
            win32pipe.DisconnectNamedPipe(h)
        except pywintypes.error:
            pass
        win32file.CloseHandle(h)
        if not data.startswith(b"%PDF"):
            continue  # conexões vazias (o Windows testa a porta ao criá-la)
        if user and me and user.lower() != me:
            _log(f"trabalho de outro usuário ({user}) ignorado")
            continue
        seq += 1
        title = safe_name(doc)
        path = os.path.join(queue_dir(), f"{datetime.now():%Y%m%d-%H%M%S}-{seq} {title}.pdf")
        with open(path, "wb") as f:
            f.write(data)
        _log(f"recebido: {title} ({len(data)} bytes)")
        try:
            _deliver(path, title)
        except Exception as e:
            _log(f"falha ao entregar: {e}")
    k32.CloseHandle(stop)
    k32.CloseHandle(mutex)
    return 0
