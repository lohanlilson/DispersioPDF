"""Identidade visual do Lumen PDF (lumen = luz).

Marca: o Prisma — a luz branca atravessa um prisma e se abre em violeta e dourado.
Gera: logo.png (1024), lumenpdf.png (256), lumenpdf.ico (programa) e pdfdoc.ico (arquivos .pdf).
"""
import math

from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 2048
INDIGO_1, INDIGO_2, VIOLET = (28, 20, 78), (66, 36, 168), (124, 58, 237)
GOLD_1, GOLD_2 = (255, 214, 102), (255, 140, 66)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def linear(size, stops, angle=45):
    w, h = size
    g = Image.new("RGB", (64, 64))
    px = g.load()
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    for y in range(64):
        for x in range(64):
            t = ((x / 63) * ca + (y / 63) * sa) / (ca + sa)
            t = max(0.0, min(1.0, t))
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= t <= p1:
                    px[x, y] = lerp(c0, c1, (t - p0) / max(p1 - p0, 1e-6))
                    break
    return g.resize((w, h), Image.BICUBIC)


def radial(size, center, radius, color, strength=1.0):
    w, h = size
    small = Image.new("L", (128, 128), 0)
    px = small.load()
    cx, cy = center[0] / w * 127, center[1] / h * 127
    r = radius / w * 127
    for y in range(128):
        for x in range(128):
            d = math.hypot(x - cx, y - cy) / r
            px[x, y] = int(255 * strength * max(0.0, 1 - d) ** 2)
    mask = small.resize((w, h), Image.BICUBIC)
    layer = Image.new("RGBA", (w, h), color + (0,))
    layer.putalpha(mask)
    return layer


def squircle_mask(size, box, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=r, fill=255)
    return m


def sparkle(draw, cx, cy, r, fill, k=0.16):
    pts = []
    for i in range(16):
        ang = math.pi / 2 * (i / 4)
        rad = r if i % 4 == 0 else r * (k if i % 2 == 0 else k * 1.15)
        if i % 4 == 0:
            rad = r
        elif i % 2 == 0:
            rad = r * k * 1.4
        else:
            rad = r * k
        pts.append((cx + rad * math.cos(ang - math.pi / 2), cy + rad * math.sin(ang - math.pi / 2)))
    draw.polygon(pts, fill=fill)


def star4(draw, cx, cy, r, fill, waist=0.2):
    """Brilho de 4 pontas com lados côncavos (curvas)."""
    pts = []
    n = 64
    for i in range(n):
        a = 2 * math.pi * i / n
        # superelipse côncava: |x|^p + |y|^p = r^p com p<1
        p = 0.55
        c, s = math.cos(a), math.sin(a)
        rr = r / ((abs(c) ** p + abs(s) ** p) ** (1 / p))
        pts.append((cx + rr * c, cy + rr * s))
    draw.polygon(pts, fill=fill)


def page_mask(size, x0, y0, x1, y1, fold, r):
    """Folha com cantos arredondados e o canto superior direito dobrado."""
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=255)
    d.polygon([(x1 - fold, y0 - 2), (x1 + 2, y0 - 2), (x1 + 2, y0 + fold)], fill=0)
    return m


def _put(img, m, color, clip=None):
    if clip is not None:
        m = ImageChops.multiply(m, clip)
    if isinstance(color, Image.Image):
        layer = color.copy()
        layer.putalpha(m)
    else:
        layer = Image.new("RGBA", m.size, color[:3] + (255,))
        a = color[3] if len(color) > 3 else 255
        layer.putalpha(m.point(lambda v: v * a // 255))
    img.alpha_composite(layer)


def app_icon(s=S):
    """Prisma suave: a luz branca entra, atravessa o prisma e se abre em violeta e dourado."""
    u = s / 1024
    P = lambda *pts: [(x * u, y * u) for x, y in pts]  # noqa: E731
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    box = [int(56 * u), int(56 * u), int(s - 56 * u), int(s - 56 * u)]
    clip = squircle_mask((s, s), box, int(236 * u))
    img.paste(linear((s, s), [(0, (60, 24, 150)), (1, (130, 80, 255))], angle=60).convert("RGBA"), (0, 0), clip)
    img.alpha_composite(radial((s, s), (640 * u, 520 * u), 420 * u, (200, 160, 255), 0.4))
    # feixe de luz branca entrando
    beam = Image.new("L", (s, s), 0)
    ImageDraw.Draw(beam).line(P((60, 660), (430, 560)), fill=255, width=int(26 * u))
    _put(img, beam.filter(ImageFilter.GaussianBlur(18 * u)), (255, 255, 255, 170), clip)
    _put(img, beam, (255, 255, 255, 255), clip)
    # leque de luz saindo
    apex = (600 * u, 520 * u)
    for (ex, ey), c in zip([(1000, 380), (1000, 520), (1000, 660)],
                           [(214, 196, 255, 220), (170, 125, 255, 230), (255, 200, 110, 220)]):
        ang = math.atan2(ey * u - apex[1], ex * u - apex[0]) + math.pi / 2
        dx, dy = math.cos(ang) * 40 * u, math.sin(ang) * 40 * u
        m = Image.new("L", (s, s), 0)
        ImageDraw.Draw(m).polygon([apex, (ex * u - dx, ey * u - dy), (ex * u + dx, ey * u + dy)], fill=255)
        _put(img, m, c, clip)
    # prisma de cantos arredondados
    tri = Image.new("L", (s, s), 0)
    ImageDraw.Draw(tri).polygon(P((500, 250), (730, 690), (270, 690)), fill=255)
    tri = tri.filter(ImageFilter.GaussianBlur(26 * u)).point(lambda v: 255 if v > 150 else 0)
    tri = tri.filter(ImageFilter.GaussianBlur(2 * u))
    sh = Image.new("L", (s, s), 0)
    sh.paste(tri, (0, int(20 * u)))
    _put(img, sh.filter(ImageFilter.GaussianBlur(24 * u)).point(lambda v: int(v * 0.45)), (16, 0, 50), clip)
    _put(img, tri, linear((s, s), [(0, (255, 255, 255)), (1, (226, 212, 255))], 100).convert("RGBA"))
    return img


def prism_symbol(s, cx, cy, scale, page_bg=(255, 255, 255)):
    """O símbolo completo (feixe + prisma + leque de luz) desenhado direto sobre a folha, sem o quadrado de fundo."""
    u = s / 1024 * scale
    ox, oy = cx - 512 * u, cy - 512 * u
    P = lambda *pts: [(ox + x * u, oy + y * u) for x, y in pts]  # noqa: E731
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    beam = Image.new("L", (s, s), 0)
    ImageDraw.Draw(beam).line(P((60, 660), (430, 560)), fill=255, width=max(2, int(30 * u)))
    _put(layer, beam, (109, 60, 240, 255))
    apex = (ox + 600 * u, oy + 520 * u)
    for (ex, ey), c in zip([(980, 380), (980, 520), (980, 660)],
                           [(170, 140, 255, 255), (109, 60, 240, 255), (255, 176, 70, 255)]):
        ex, ey = ox + ex * u, oy + ey * u
        ang = math.atan2(ey - apex[1], ex - apex[0]) + math.pi / 2
        dx, dy = math.cos(ang) * 40 * u, math.sin(ang) * 40 * u
        m = Image.new("L", (s, s), 0)
        ImageDraw.Draw(m).polygon([apex, (ex - dx, ey - dy), (ex + dx, ey + dy)], fill=255)
        _put(layer, m, c)
    tri = Image.new("L", (s, s), 0)
    ImageDraw.Draw(tri).polygon(P((500, 250), (730, 690), (270, 690)), fill=255)
    tri = tri.filter(ImageFilter.GaussianBlur(26 * u)).point(lambda v: 255 if v > 150 else 0)
    tri = tri.filter(ImageFilter.GaussianBlur(max(1, 2 * u)))
    _put(layer, tri, linear((s, s), [(0, (124, 72, 250)), (1, (66, 28, 168))], 100).convert("RGBA"))
    return layer


def doc_icon(s=S):
    """Ícone dos arquivos .pdf (como o do Adobe): folha branca com o símbolo completo da marca e a etiqueta PDF."""
    u = s / 1024
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    x0, y0, x1, y1, f, r = 176 * u, 48 * u, 848 * u, 976 * u, 230 * u, 50 * u
    pm = page_mask((s, s), x0, y0, x1, y1, f, r)
    sh = Image.new("L", (s, s), 0)
    sh.paste(pm, (int(6 * u), int(18 * u)))
    shadow = Image.new("RGBA", (s, s), (20, 10, 50, 255))
    shadow.putalpha(sh.filter(ImageFilter.GaussianBlur(22 * u)).point(lambda v: int(v * 0.45)))
    img.alpha_composite(shadow)
    edge = pm.filter(ImageFilter.MaxFilter(9))
    img.paste(Image.new("RGBA", (s, s), (206, 202, 222, 255)), (0, 0), edge)
    img.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), pm)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x1 - f, y0, x1, y0 + f], radius=36 * u, fill=(236, 230, 252, 255),
                        outline=(206, 202, 222, 255), width=int(8 * u))
    corner = Image.new("L", (s, s), 0)
    ImageDraw.Draw(corner).polygon([(x1 - f + 6 * u, y0 - 6 * u), (x1 + 6 * u, y0 + f - 6 * u), (x1 + 6 * u, y0 - 6 * u)],
                                   fill=255)
    img.paste(Image.new("RGBA", (s, s), (0, 0, 0, 0)), (0, 0), corner)
    d = ImageDraw.Draw(img)
    d.line([(x1 - f, y0 + 3 * u), (x1 - 3 * u, y0 + f)], fill=(206, 202, 222, 255), width=int(8 * u))
    # símbolo completo no centro da folha
    sym = prism_symbol(s, 512 * u, 500 * u, 0.62)
    m = ImageChops.multiply(sym.getchannel("A"), pm)
    sym.putalpha(m)
    img.alpha_composite(sym)
    # etiqueta PDF
    try:
        from PIL import ImageFont
        fnt = None
        for fp in ("C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            try:
                fnt = ImageFont.truetype(fp, int(118 * u))
                break
            except OSError:
                pass
        if fnt:
            d = ImageDraw.Draw(img)
            d.text((512 * u, 820 * u), "PDF", font=fnt, fill=(80, 40, 190, 255), anchor="mm")
    except Exception:
        pass
    return img


SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def save_ico(img, path):
    """ICO com cada tamanho reduzido a partir da arte grande (nitidez nos tamanhos pequenos)."""
    frames = [img.resize(sz, Image.LANCZOS) for sz in SIZES]
    frames[-1].save(path, sizes=SIZES, append_images=frames[:-1])


if __name__ == "__main__":
    a = app_icon().resize((1024, 1024), Image.LANCZOS)
    a.save("logo.png")
    a.resize((256, 256), Image.LANCZOS).save("lumenpdf.png")
    save_ico(a, "lumenpdf.ico")
    doc = doc_icon().resize((1024, 1024), Image.LANCZOS)
    save_ico(doc, "pdfdoc.ico")
    doc.resize((256, 256), Image.LANCZOS).save("pdfdoc.png")
    print("ok")
