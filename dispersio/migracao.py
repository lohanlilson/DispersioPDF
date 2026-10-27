"""Migração do nome antigo (Lumen PDF) para Dispersio PDF: configurações e pasta de dados.
Roda uma vez, no início do programa, antes de qualquer leitura de configuração."""
import os
import shutil

from . import APP_ID, LEGACY_APP_ID, LEGACY_APP_NAMES


def _settings():
    from PySide6.QtCore import QSettings
    new = QSettings(APP_ID, APP_ID)
    if new.value("_migrado", None) is not None:
        return
    old = QSettings(LEGACY_APP_ID, LEGACY_APP_ID)
    for k in old.allKeys():
        if not new.contains(k):
            new.setValue(k, old.value(k))
    new.setValue("_migrado", LEGACY_APP_ID)
    new.sync()


def _merge(src, dst):
    """Move o conteúdo de src para dst sem sobrescrever o que já existe em dst."""
    for name in os.listdir(src):
        a, b = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(a) and os.path.isdir(b):
            _merge(a, b)
        elif not os.path.exists(b):
            try:
                shutil.move(a, b)
            except OSError:
                pass


def _data_dir():
    from PySide6.QtCore import QStandardPaths
    new = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not new:
        return
    parent = os.path.dirname(os.path.dirname(new))  # …/AppData/Roaming
    # versões até a 1.10: Roaming/LumenPDF/Lumen PDF; versão 1.11: Roaming/LumenPDF/Dispersio PDF
    for name in LEGACY_APP_NAMES:
        old = os.path.join(parent, LEGACY_APP_ID, name)
        if os.path.isdir(old) and os.path.normcase(old) != os.path.normcase(new):
            os.makedirs(new, exist_ok=True)
            _merge(old, new)
            shutil.rmtree(old, ignore_errors=True)
    try:
        os.rmdir(os.path.join(parent, LEGACY_APP_ID))  # só remove se ficou vazia
    except OSError:
        pass


def run():
    for step in (_settings, _data_dir):
        try:
            step()
        except Exception:  # migração nunca impede o programa de abrir
            pass
