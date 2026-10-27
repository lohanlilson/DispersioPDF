"""Gera os ícones do app Android a partir da arte do Prisma (assets/make_icon.py).
Adaptativo: fundo índigo escuro (camada de trás) + feixe/leque/prisma (frente, dentro da zona segura)."""
import math, os, sys
from PIL import Image, ImageDraw, ImageFilter
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "assets"))
import make_icon as mi  # noqa: E402

RES = os.path.join(ROOT, "android", "app", "src", "main", "res")
S = 1024


def background(s=S):
    return mi.night_bg(s, glow_at=(540, 500), glow_r=420)


def foreground(s=S, mono=False):
    if not mono:   # mesma arte do logo ("Noite"): feixe com brilho e leque até a borda
        full = Image.new("L", (s, s), 255)
        return mi.light_symbol(s, s * 0.49, s * 0.49, 0.56, full)
    return _mono(s)


def _mono(s=S, mono=True):
    """Arte desenhada em 1024 e reduzida para caber nos 66% centrais (zona segura do ícone adaptativo)."""
    big = 1024
    u = 1
    P = lambda *pts: [(x * u, y * u) for x, y in pts]  # noqa: E731
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    full = Image.new("L", (big, big), 255)
    beam = Image.new("L", (big, big), 0)
    ImageDraw.Draw(beam).line(P((60, 660), (430, 560)), fill=255, width=26)
    if not mono:
        mi._put(img, beam.filter(ImageFilter.GaussianBlur(18)), (255, 255, 255, 170), full)
    mi._put(img, beam, (255, 255, 255, 255), full)
    apex = (600, 520)
    for (ex, ey), c in zip([(1000, 380), (1000, 520), (1000, 660)],
                           [(214, 196, 255, 220), (170, 125, 255, 230), (255, 200, 110, 220)]):
        ang = math.atan2(ey - apex[1], ex - apex[0]) + math.pi / 2
        dx, dy = math.cos(ang) * 40, math.sin(ang) * 40
        m = Image.new("L", (big, big), 0)
        ImageDraw.Draw(m).polygon([apex, (ex - dx, ey - dy), (ex + dx, ey + dy)], fill=255)
        mi._put(img, m, (255, 255, 255, 255) if mono else c, full)
    tri = Image.new("L", (big, big), 0)
    ImageDraw.Draw(tri).polygon(P((500, 250), (730, 690), (270, 690)), fill=255)
    tri = tri.filter(ImageFilter.GaussianBlur(26)).point(lambda v: 255 if v > 150 else 0).filter(ImageFilter.GaussianBlur(2))
    if not mono:
        sh = Image.new("L", (big, big), 0)
        sh.paste(tri, (0, 20))
        mi._put(img, sh.filter(ImageFilter.GaussianBlur(24)).point(lambda v: int(v * 0.45)), (16, 0, 50), full)
        mi._put(img, tri, mi.linear((big, big), [(0, (255, 255, 255)), (1, (226, 212, 255))], 100).convert("RGBA"))
    else:
        mi._put(img, tri, (255, 255, 255, 255), full)
    # cabe na zona segura: 66/108 do lado, centralizado
    inner = int(s * 0.66)
    art = img.resize((inner, inner), Image.LANCZOS)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.alpha_composite(art, ((s - inner) // 2, (s - inner) // 2))
    return out


def main():
    os.makedirs(os.path.join(RES, "drawable-nodpi"), exist_ok=True)
    background(432).save(os.path.join(RES, "drawable-nodpi", "ic_launcher_background.png"))
    foreground(432).save(os.path.join(RES, "drawable-nodpi", "ic_launcher_foreground.png"))
    foreground(432, mono=True).save(os.path.join(RES, "drawable-nodpi", "ic_launcher_monochrome.png"))
    legacy = mi.app_icon(1024)
    for d, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        os.makedirs(os.path.join(RES, f"mipmap-{d}"), exist_ok=True)
        legacy.resize((px, px), Image.LANCZOS).save(os.path.join(RES, f"mipmap-{d}", "ic_launcher.png"))
    # logo para a tela inicial do app
    legacy.resize((256, 256), Image.LANCZOS).save(os.path.join(RES, "drawable-nodpi", "dispersio_logo.png"))
    # ícone de arquivo PDF (lista de recentes)
    mi.doc_icon(1024).resize((192, 192), Image.LANCZOS).save(os.path.join(RES, "drawable-nodpi", "pdf_doc.png"))
    os.makedirs(os.path.join(RES, "mipmap-anydpi-v26"), exist_ok=True)
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
           '    <background android:drawable="@drawable/ic_launcher_background" />\n'
           '    <foreground android:drawable="@drawable/ic_launcher_foreground" />\n'
           '    <monochrome android:drawable="@drawable/ic_launcher_monochrome" />\n</adaptive-icon>\n')
    open(os.path.join(RES, "mipmap-anydpi-v26", "ic_launcher.xml"), "w").write(xml)
    print("ícones gerados")


if __name__ == "__main__":
    main()
