"""Quadrinhos, mangás e livros: CBZ/CBR/CB7 (e .zip de imagens) e EPUB/MOBI/FB2.

Quadrinhos viram um PDF só na memória, uma página por imagem, sem recomprimir (JPEG entra como está — rápido e do
mesmo tamanho). CBR (RAR) e CB7 são abertos pelo tar.exe do Windows (libarchive), que lê RAR4, RAR5 e 7z.
O arquivo original nunca é alterado.
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import pymupdf

COMIC_EXT = {".cbz", ".cbr", ".cb7", ".cbt"}
BOOK_EXT = {".epub", ".mobi", ".fb2"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".jxl", ".tif", ".tiff"}


def is_comic(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in COMIC_EXT:
        return True
    if ext == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
                imgs = [n for n in names if os.path.splitext(n)[1].lower() in IMG_EXT]
                return bool(imgs) and len(imgs) >= 0.8 * len([n for n in names if not _junk(n)])
        except Exception:
            return False
    return False


def is_book(path):
    return os.path.splitext(path)[1].lower() in BOOK_EXT


def natural_key(s):
    """Ordem natural: 2.jpg antes de 10.jpg; “Cap 9” antes de “Cap 10”."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _junk(n):
    b = os.path.basename(n)
    return n.startswith("__MACOSX/") or b.startswith(".") or b.lower() in ("thumbs.db", "desktop.ini")


def _images_from_zip(path):
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if not n.endswith("/") and not _junk(n)
                        and os.path.splitext(n)[1].lower() in IMG_EXT), key=natural_key)
        info = None
        if "ComicInfo.xml" in z.namelist():
            info = z.read("ComicInfo.xml").decode("utf-8", "replace")
        return [(n, z.read(n)) for n in names], info


def _images_from_archive(path):
    """RAR/7z/tar: extrai com o tar do sistema (no Windows 10/11 é o libarchive, que lê RAR4/RAR5/7z)."""
    tar = shutil.which("bsdtar") or shutil.which("tar")
    if not tar:
        raise RuntimeError("Não há como abrir este formato neste computador.")
    tmp = tempfile.mkdtemp(prefix="dispersio_hq_")
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0      # sem janela de console
        r = subprocess.run([tar, "-xf", path, "-C", tmp], capture_output=True, creationflags=flags, timeout=300)
        if r.returncode != 0:
            msg = r.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError("Não foi possível abrir o arquivo compactado." + (f"\n{msg[:300]}" if msg else ""))
        files, info = [], None
        for root, _dirs, fs in os.walk(tmp):
            for f in fs:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, tmp).replace("\\", "/")
                if _junk(rel):
                    continue
                if f == "ComicInfo.xml":
                    info = open(full, encoding="utf-8", errors="replace").read()
                elif os.path.splitext(f)[1].lower() in IMG_EXT:
                    files.append(rel)
        files.sort(key=natural_key)
        return [(n, open(os.path.join(tmp, n), "rb").read()) for n in files], info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_comic(path):
    """[(nome, bytes da imagem)] em ordem de leitura, e o ComicInfo.xml (se houver)."""
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"PK":                      # muitos .cbr são na verdade ZIP
        return _images_from_zip(path)
    return _images_from_archive(path)


def manga_rtl(info):
    """O ComicInfo.xml diz que é mangá (leitura da direita para a esquerda)?"""
    return bool(info and re.search(r"<Manga>\s*YesAndRightToLeft\s*</Manga>", info, re.I))


def _page_from_image(doc, data):
    try:
        img = pymupdf.open(stream=data)          # descobre o tamanho sem decodificar tudo
        r = img[0].rect
        img.close()
        page = doc.new_page(width=r.width, height=r.height)
        page.insert_image(page.rect, stream=data)
        return True
    except Exception:
        pass
    try:                                         # WebP/AVIF etc. que o MuPDF não lê: converte com o Pillow
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        page = doc.new_page(width=im.width, height=im.height)
        page.insert_image(page.rect, stream=buf.getvalue())
        return True
    except Exception:
        return False


def comic_to_pdf(path):
    """(bytes do PDF, info) — info: {'pages', 'rtl', 'webtoon', 'skipped'}."""
    images, xml = read_comic(path)
    if not images:
        raise RuntimeError("Nenhuma imagem encontrada neste arquivo.")
    doc = pymupdf.open()
    skipped = 0
    tall = 0
    for _name, data in images:
        if _page_from_image(doc, data):
            r = doc[-1].rect
            if r.height > 2.2 * r.width:
                tall += 1
        else:
            skipped += 1
    if doc.page_count == 0:
        raise RuntimeError("Não foi possível ler as imagens deste arquivo.")
    title = os.path.splitext(os.path.basename(path))[0]
    doc.set_metadata({"title": title, "creator": "Dispersio PDF"})
    info = {"pages": doc.page_count, "rtl": manga_rtl(xml), "webtoon": tall >= max(1, doc.page_count // 3),
            "skipped": skipped}
    return doc.tobytes(garbage=0), info


def book_to_pdf(path, fontsize=11):
    """EPUB/MOBI/FB2 paginado em tamanho de livro (A5)."""
    src = pymupdf.open(path)
    if src.is_reflowable:
        src.layout(rect=pymupdf.paper_rect("a5"), fontsize=fontsize)
    data = src.convert_to_pdf()
    toc = src.get_toc()
    src.close()
    if toc:
        d = pymupdf.open("pdf", data)
        try:
            d.set_toc(toc)
            data = d.tobytes()
        except Exception:
            pass
    return data


def siblings(path):
    """Capítulos da mesma pasta, em ordem natural (para “próximo/anterior capítulo”)."""
    folder = os.path.dirname(os.path.abspath(path))
    try:
        fs = [os.path.join(folder, f) for f in os.listdir(folder)
              if os.path.splitext(f)[1].lower() in COMIC_EXT | BOOK_EXT | {".pdf", ".zip"}]
    except OSError:
        return []
    return sorted(fs, key=lambda p: natural_key(os.path.basename(p)))


def neighbor(path, step):
    sib = siblings(path)
    try:
        i = [os.path.normcase(p) for p in sib].index(os.path.normcase(os.path.abspath(path)))
    except ValueError:
        return None
    j = i + step
    return sib[j] if 0 <= j < len(sib) else None


def pos_key(path):
    return "posicao/" + hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:20]
