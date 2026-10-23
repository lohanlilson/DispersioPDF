"""Gera a identidade visual do Lumen PDF: lumenpdf.ico/png (programa), pdfdoc.ico (arquivos .pdf) e logo.png."""
from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 2048  # desenha grande e reduz (antisserrilhado)
C1, C2, C3 = (255, 88, 76), (232, 38, 108), (110, 44, 220)  # coral -> magenta -> violeta


def gradient(size, stops):
    w, h = size
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(w):
            t = (x * 0.45 + y * 0.55) / (w * 0.45 + h * 0.55)
            if t < 0.5:
                a, b, k = stops[0], stops[1], t / 0.5
            else:
                a, b, k = stops[1], stops[2], (t - 0.5) / 0.5
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
    return g


def rounded_mask(size, box, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=r, fill=255)
    return m


def sparkle(draw, cx, cy, r, fill):
    k = 0.2
    pts = [(cx, cy - r), (cx + r * k, cy - r * k), (cx + r, cy), (cx + r * k, cy + r * k),
           (cx, cy + r), (cx - r * k, cy + r * k), (cx - r, cy), (cx - r * k, cy - r * k)]
    draw.polygon(pts, fill=fill)


def mark(s=S):
    """Monograma: um 'L' que também é uma folha com o canto dobrado, e um brilho (lumen)."""
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    u = s / 1024
    # base com degradê e cantos arredondados
    small = gradient((256, 256), [C1, C2, C3]).resize((s, s), Image.BICUBIC)
    base = Image.new("RGBA", (s, s))
    base.paste(small, (0, 0))
    m = rounded_mask((s, s), [int(40 * u), int(40 * u), int(s - 40 * u), int(s - 40 * u)], int(230 * u))
    img.paste(base, (0, 0), m)
    # brilho superior suave
    shine = Image.new("L", (s, s), 0)
    ImageDraw.Draw(shine).ellipse([int(-200 * u), int(-620 * u), int(1220 * u), int(420 * u)], fill=60)
    shine = ImageChops.multiply(shine.filter(ImageFilter.GaussianBlur(60 * u)), m)
    img.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), shine)
    # sombra do monograma
    L = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(L)
    x0, y0, x1, y1 = 300 * u, 230 * u, 470 * u, 800 * u      # haste
    d.rounded_rectangle([x0, y0 + 60 * u, x1, y1], radius=40 * u, fill=255)
    d.polygon([(x0, y0 + 100 * u), (x0, y0 + 40 * u), (x0 + 40 * u, y0), (x1 - 70 * u, y0), (x1, y0 + 70 * u),
               (x1, y0 + 160 * u), (x0, y0 + 160 * u)], fill=255)
    d.rounded_rectangle([x0, y1 - 170 * u, 740 * u, y1], radius=40 * u, fill=255)  # base do L
    sh = L.filter(ImageFilter.GaussianBlur(28 * u))
    shadow = Image.new("RGBA", (s, s), (60, 0, 60, 0))
    shadow.putalpha(sh.point(lambda a: int(a * 0.35)))
    img.alpha_composite(shadow, (int(10 * u), int(22 * u)))
    img.paste(Image.new("RGBA", (s, s), (255, 255, 255, 255)), (0, 0), L)
    d2 = ImageDraw.Draw(img)
    # canto dobrado (tom do degradê)
    d2.polygon([(x1 - 70 * u, y0), (x1, y0 + 70 * u), (x1 - 70 * u, y0 + 70 * u)], fill=(255, 205, 214, 255))
    # brilhos
    sparkle(d2, 690 * u, 420 * u, 150 * u, (255, 255, 255, 255))
    sparkle(d2, 820 * u, 260 * u, 62 * u, (255, 255, 255, 230))
    return img


def doc_icon(s=S):
    u = s / 1024
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1, f = 170 * u, 50 * u, 830 * u, 974 * u, 210 * u
    page = [(x0 + 40 * u, y0), (x1 - f, y0), (x1, y0 + f), (x1, y1 - 40 * u), (x1 - 40 * u, y1), (x0 + 40 * u, y1),
            (x0, y1 - 40 * u), (x0, y0 + 40 * u)]
    sh = Image.new("L", (s, s), 0)
    ImageDraw.Draw(sh).polygon([(x + 12 * u, y + 20 * u) for x, y in page], fill=90)
    img.putalpha(sh.filter(ImageFilter.GaussianBlur(20 * u)))
    d = ImageDraw.Draw(img)
    d.polygon(page, fill=(255, 255, 255, 255))
    d.line(page + [page[0]], fill=(205, 205, 215, 255), width=int(10 * u))
    d.polygon([(x1 - f, y0), (x1 - f, y0 + f), (x1, y0 + f)], fill=(236, 226, 246, 255))
    for k in range(3):
        yy = 300 * u + k * 80 * u
        d.rounded_rectangle([x0 + 90 * u, yy, x1 - (90 + 120 * (k == 2)) * u, yy + 34 * u], radius=17 * u,
                            fill=(214, 214, 226, 255))
    badge = mark(s).resize((int(560 * u), int(560 * u)), Image.LANCZOS)
    img.alpha_composite(badge, (int(220 * u), int(470 * u)))
    return img


SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
if __name__ == "__main__":
    a = mark().resize((1024, 1024), Image.LANCZOS)
    a.save("logo.png")
    a.resize((256, 256), Image.LANCZOS).save("lumenpdf.png")
    a.save("lumenpdf.ico", sizes=SIZES)
    doc_icon().resize((1024, 1024), Image.LANCZOS).save("pdfdoc.ico", sizes=SIZES)
    print("ok")
