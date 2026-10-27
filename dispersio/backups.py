"""Cópia de segurança ao salvar por cima: a versão anterior do arquivo fica guardada (últimas 10, até 30 dias)."""
import hashlib
import json
import os
import shutil
import time
from datetime import datetime

KEEP = 10
DAYS = 30


def base_dir():
    try:
        from PySide6.QtCore import QStandardPaths
        d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    except Exception:
        d = ""
    return os.path.join(d or os.path.expanduser("~"), "versoes")


def _key(path):
    return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:16]


def _dir(path):
    return os.path.join(base_dir(), _key(path))


def backup(path):
    """Guarda o arquivo atual antes de ser substituído. Devolve o caminho da cópia (ou None)."""
    if not path or not os.path.isfile(path):
        return None
    d = _dir(path)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "arquivo.json"), "w", encoding="utf-8") as f:
        json.dump({"path": os.path.abspath(path)}, f, ensure_ascii=False)
    dst = os.path.join(d, datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".pdf")
    shutil.copy2(path, dst)
    prune(d)
    return dst


def prune(d):
    files = sorted((f for f in os.listdir(d) if f.endswith(".pdf")), reverse=True)
    limit = time.time() - DAYS * 86400
    for i, f in enumerate(files):
        fp = os.path.join(d, f)
        if i >= KEEP or os.path.getmtime(fp) < limit and i > 0:
            try:
                os.remove(fp)
            except OSError:
                pass


def versions(path):
    """[(arquivo, data em que foi substituído, tamanho)] — mais recente primeiro."""
    d = _dir(path)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted((f for f in os.listdir(d) if f.endswith(".pdf")), reverse=True):
        fp = os.path.join(d, f)
        try:
            when = datetime.strptime(f[:15], "%Y%m%d-%H%M%S")
        except ValueError:
            when = datetime.fromtimestamp(os.path.getmtime(fp))
        out.append((fp, when, os.path.getsize(fp)))
    return out
