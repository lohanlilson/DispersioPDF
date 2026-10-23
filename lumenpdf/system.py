"""Integração com o Windows: leitor padrão de PDF."""
import subprocess
import sys

from . import APP_NAME, PROG_ID

IS_WINDOWS = sys.platform == "win32"


def is_frozen():
    return getattr(sys, "frozen", False)


def is_default_pdf():
    """True se o Windows abre .pdf com o Lumen PDF (escolha do usuário)."""
    if not IS_WINDOWS:
        return True
    try:
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            prog, _ = winreg.QueryValueEx(k, "ProgId")
        return prog == PROG_ID
    except OSError:
        return False


def is_registered():
    """True se o instalador registrou o programa (Capabilities/RegisteredApplications)."""
    if not IS_WINDOWS:
        return False
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\RegisteredApplications") as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            pass
    return False


def open_default_apps_settings():
    """Abre a tela do Windows onde o usuário confirma o Lumen PDF como padrão.
    O Windows 10/11 não permite que um programa se defina como padrão sozinho."""
    if not IS_WINDOWS:
        return
    import winreg
    target = "ms-settings:defaultapps"
    for hive, param in ((winreg.HKEY_LOCAL_MACHINE, "registeredAppMachine"), (winreg.HKEY_CURRENT_USER, "registeredAppUser")):
        try:
            with winreg.OpenKey(hive, r"Software\RegisteredApplications") as k:
                winreg.QueryValueEx(k, APP_NAME)
            target = f"ms-settings:defaultapps?{param}={APP_NAME.replace(' ', '%20')}"
            break
        except OSError:
            pass
    subprocess.Popen(["cmd", "/c", "start", "", target], shell=False, creationflags=0x08000000)
