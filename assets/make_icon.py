"""Identidade visual do Lumen PDF (lumen = luz).

Marca: uma página branca iluminada por um brilho dourado, sobre um fundo índigo-violeta.
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


def app_icon(s=S):
    u = s / 1024
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    box = [int(56 * u), int(56 * u), int(s - 56 * u), int(s - 56 * u)]
    mask = squircle_mask((s, s), box, int(236 * u))
    base = linear((s, s), [(0, INDIGO_1), (0.55, INDIGO_2), (1, VIOLET)], angle=60).convert("RGBA")
    # luz quente vindo do canto superior direito
    base.alpha_composite(radial((s, s), (800 * u, 230 * u), 700 * u, (255, 120, 170), 0.35))
    base.alpha_composite(radial((s, s), (780 * u, 260 * u), 430 * u, (255, 200, 120), 0.55))
    img.paste(base, (0, 0), mask)
    # brilho de borda superior (vidro)
    gloss = Image.new("L", (s, s), 0)
    ImageDraw.Draw(gloss).rounded_rectangle([box[0], box[1], box[2], int(430 * u)], radius=int(236 * u), fill=38)
    gloss = ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(40 * u)), mask)
    img.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), gloss)

    # página
    x0, y0, x1, y1, f = 300 * u, 250 * u, 690 * u, 790 * u, 130 * u
    pm = page_mask((s, s), x0, y0, x1, y1, f, 34 * u)
    sh = Image.new("L", (s, s), 0)
    sh.paste(pm, (int(14 * u), int(30 * u)))
    sh = ImageChops.multiply(sh.filter(ImageFilter.GaussianBlur(26 * u)).point(lambda v: int(v * 0.6)), mask)
    shadow = Image.new("RGBA", (s, s), (10, 0, 40, 255))
    shadow.putalpha(sh)
    img.alpha_composite(shadow)
    img.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), pm)
    d = ImageDraw.Draw(img)
    fold = Image.new("L", (s, s), 0)
    ImageDraw.Draw(fold).rounded_rectangle([x1 - f, y0 - 40 * u, x1 + 40 * u, y0 + f], radius=26 * u, fill=255)
    tri = Image.new("L", (s, s), 0)
    ImageDraw.Draw(tri).polygon([(x1 - f, y0), (x1 - f, y0 + f), (x1, y0 + f)], fill=255)
    fold = ImageChops.multiply(fold, tri)
    fsh = Image.new("RGBA", (s, s), (120, 60, 0, 255))
    fsh.putalpha(fold.filter(ImageFilter.GaussianBlur(10 * u)).point(lambda v: int(v * 0.35)))
    img.alpha_composite(fsh, (int(-6 * u), int(8 * u)))
    img.paste(Image.new("RGBA", (s, s), (255, 220, 160, 255)), (0, 0), fold)
    # linhas de texto
    for k, w in enumerate((260, 300, 220)):
        yy = y0 + 210 * u + k * 70 * u
        d.rounded_rectangle([x0 + 62 * u, yy, x0 + (62 + w) * u, yy + 30 * u], radius=15 * u, fill=(212, 206, 236, 255))
    # o lúmen: brilho dourado com halo, atravessando a borda da página
    cx, cy = 690 * u, 660 * u
    halo = radial((s, s), (cx, cy), 260 * u, (255, 200, 80), 0.9)
    img.alpha_composite(halo)
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    star4(ImageDraw.Draw(glow), cx, cy, 200 * u, (255, 190, 70, 255))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(22 * u)))
    d = ImageDraw.Draw(img)
    star4(d, cx, cy, 175 * u, (255, 205, 92, 255))
    star4(d, cx, cy, 120 * u, (255, 236, 170, 255))
    star4(d, cx, cy, 58 * u, (255, 255, 255, 255))
    return img


def doc_icon(s=S):
    """Ícone dos arquivos .pdf: folha branca moderna com o selo da marca (estilo dos leitores profissionais)."""
    u = s / 1024
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    x0, y0, x1, y1, f, r = 196 * u, 64 * u, 828 * u, 960 * u, 220 * u, 46 * u
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
    d.rounded_rectangle([x1 - f, y0, x1, y0 + f], radius=34 * u, fill=(234, 229, 248, 255),
                        outline=(206, 202, 222, 255), width=int(8 * u))
    corner = Image.new("L", (s, s), 0)
    ImageDraw.Draw(corner).polygon([(x1 - f + 6 * u, y0 - 6 * u), (x1 + 6 * u, y0 + f - 6 * u), (x1 + 6 * u, y0 - 6 * u)],
                                   fill=255)
    img.paste(Image.new("RGBA", (s, s), (0, 0, 0, 0)), (0, 0), corner)
    d = ImageDraw.Draw(img)
    d.line([(x1 - f, y0 + 3 * u), (x1 - 3 * u, y0 + f)], fill=(206, 202, 222, 255), width=int(8 * u))
    # linhas de texto
    for k, w in enumerate((420, 470, 470, 330)):
        yy = 300 * u + k * 72 * u
        d.rounded_rectangle([x0 + 84 * u, yy, x0 + (84 + w) * u, yy + 30 * u], radius=15 * u,
                            fill=(224, 221, 236, 255))
    # selo da marca, sobressaindo da borda esquerda
    badge = app_icon(s).resize((int(560 * u), int(560 * u)), Image.LANCZOS)
    img.alpha_composite(badge, (int(70 * u), int(420 * u)))
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
