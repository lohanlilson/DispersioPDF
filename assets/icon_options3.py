"""Terceira rodada: variações do Prisma (luz branca entrando, saindo em tons de violeta)."""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont

from make_icon import linear, radial, squircle_mask

S = 2048
U = S / 1024


def base(stops, angle=70):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    box = [int(56 * U), int(56 * U), int(S - 56 * U), int(S - 56 * U)]
    mask = squircle_mask((S, S), box, int(236 * U))
    img.paste(linear((S, S), list(stops), angle=angle).convert("RGBA"), (0, 0), mask)
    return img, mask


def P(*pts):
    return [(x * U, y * U) for x, y in pts]


def poly(pts):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def put(img, m, color, clip=None):
    if clip is not None:
        m = ImageChops.multiply(m, clip)
    if isinstance(color, Image.Image):
        layer = color.copy()
        layer.putalpha(m)
        img.alpha_composite(layer)
    else:
        layer = Image.new("RGBA", (S, S), color[:3] + (255,))
        a = color[3] if len(color) > 3 else 255
        layer.putalpha(m.point(lambda v: v * a // 255))
        img.alpha_composite(layer)


def shadow(img, m, clip, alpha=0.45, dy=20, blur=24, color=(16, 0, 50)):
    sh = Image.new("L", (S, S), 0)
    sh.paste(m, (0, int(dy * U)))
    sh = ImageChops.multiply(sh.filter(ImageFilter.GaussianBlur(blur * U)).point(lambda v: int(v * alpha)), clip)
    put(img, sh, color)


def glow_line(img, pts, width, color, clip, blur=18):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).line(pts, fill=255, width=int(width * U), joint="curve")
    put(img, m.filter(ImageFilter.GaussianBlur(blur * U)), color + (170,), clip)
    put(img, m, (255, 255, 255, 255), clip)


def fan(img, apex, ends, colors, clip, spread=26):
    """Raios saindo de um ponto (lado do prisma) até a borda."""
    for (ex, ey), c in zip(ends, colors):
        ang = math.atan2(ey - apex[1], ex - apex[0]) + math.pi / 2
        dx, dy = math.cos(ang) * spread * U, math.sin(ang) * spread * U
        put(img, poly([(apex[0], apex[1]), (ex * U - dx, ey * U - dy), (ex * U + dx, ey * U + dy)]), c, clip)


# P1 — Prisma de vidro refinado
def p1():
    img, clip = base([(0, (36, 14, 96)), (0.6, (88, 44, 210)), (1, (140, 90, 255))], 75)
    img.alpha_composite(radial((S, S), (520 * U, 520 * U), 520 * U, (180, 140, 255), 0.35))
    glow_line(img, P((60, 700), (452, 540)), 22, (255, 255, 255), clip)
    fan(img, (560 * U, 520 * U), [(1000, 400), (1000, 500), (1000, 600), (1000, 700)],
        [(255, 255, 255, 230), (214, 192, 255, 240), (170, 120, 255, 240), (255, 190, 90, 235)], clip, spread=34)
    tri = poly(P((512, 230), (740, 700), (284, 700)))
    shadow(img, tri, clip)
    glass = linear((S, S), [(0, (255, 255, 255)), (1, (220, 204, 255))], 100).convert("RGBA")
    put(img, tri, glass)
    put(img, poly(P((512, 230), (740, 700), (560, 700))), (190, 168, 250, 140))
    edge = Image.new("L", (S, S), 0)
    ImageDraw.Draw(edge).line(P((512, 236), (290, 694)), fill=255, width=int(10 * U))
    put(img, edge, (255, 255, 255, 220))
    return img


# P2 — Plano e minimalista
def p2():
    img, clip = base([(0, (109, 60, 240)), (1, (124, 72, 250))], 90)
    d = ImageDraw.Draw(img)
    beam = Image.new("L", (S, S), 0)
    ImageDraw.Draw(beam).line(P((40, 690), (455, 560)), fill=255, width=int(34 * U))
    put(img, beam, (255, 255, 255, 255), clip)
    fan(img, (560 * U, 545 * U), [(1000, 440), (1000, 560), (1000, 680)],
        [(255, 255, 255, 255), (205, 184, 255, 255), (160, 120, 255, 255)], clip, spread=44)
    tri = poly(P((512, 250), (730, 690), (294, 690)))
    put(img, tri, (255, 255, 255, 255))
    put(img, poly(P((512, 250), (730, 690), (540, 690))), (232, 222, 255, 255))
    return img


# P3 — A luz vira texto: os raios saem do prisma e formam as linhas de uma página
def p3():
    img, clip = base([(0, (40, 16, 110)), (1, (110, 62, 240))], 70)
    glow_line(img, P((60, 470), (300, 430)), 20, (255, 255, 255), clip)
    tri = poly(P((350, 250), (520, 600), (180, 600)))
    shadow(img, tri, clip)
    put(img, tri, linear((S, S), [(0, (255, 255, 255)), (1, (222, 208, 255))], 100).convert("RGBA"))
    # página à direita recebendo a luz
    page = Image.new("L", (S, S), 0)
    ImageDraw.Draw(page).rounded_rectangle(P((560, 300), (860, 760)), radius=36 * U, fill=255)
    shadow(img, page, clip)
    put(img, page, (255, 255, 255, 255))
    cols = [(255, 190, 90), (190, 160, 255), (130, 90, 245)]
    for k, c in enumerate(cols):
        y = 400 + k * 90
        ray = poly(P((440, 420 + k * 26), (440, 440 + k * 26), (600, y + 18), (600, y - 2)))
        put(img, ray, c + (220,), clip)
        line = Image.new("L", (S, S), 0)
        ImageDraw.Draw(line).rounded_rectangle(P((600, y - 10), (800 - k * 40, y + 26)), radius=18 * U, fill=255)
        put(img, line, c + (255,))
    return img


# P4 — Composição vertical: luz sobe e abre em leque
def p4():
    img, clip = base([(0, (30, 10, 84)), (1, (104, 56, 236))], 90)
    glow_line(img, P((512, 980), (512, 650)), 24, (255, 255, 255), clip)
    apex = (512 * U, 430 * U)
    ends = [(150, 40), (330, 40), (512, 40), (694, 40), (874, 40)]
    cols = [(150, 100, 255, 230), (190, 150, 255, 235), (255, 255, 255, 235), (190, 150, 255, 235), (255, 190, 90, 230)]
    fan(img, apex, ends, cols, clip, spread=40)
    tri = poly(P((512, 380), (720, 760), (304, 760)))
    shadow(img, tri, clip)
    put(img, tri, linear((S, S), [(0, (255, 255, 255)), (1, (214, 196, 255))], 90).convert("RGBA"))
    put(img, poly(P((512, 380), (720, 760), (540, 760))), (190, 170, 250, 130))
    return img


# P5 — Prisma 3D (faces sombreadas) com feixe dourado
def p5():
    img, clip = base([(0, (24, 10, 70)), (1, (80, 36, 190))], 70)
    glow_line(img, P((40, 640), (380, 560)), 22, (255, 255, 255), clip)
    fan(img, (650 * U, 540 * U), [(1000, 430), (1000, 540), (1000, 650)],
        [(255, 200, 100, 235), (210, 180, 255, 235), (150, 105, 255, 235)], clip, spread=40)
    front = P((420, 260), (600, 640), (240, 640))
    side = P((420, 260), (640, 300), (800, 660), (600, 640))
    bottom = P((240, 640), (600, 640), (800, 660), (460, 690))
    whole = poly(P((420, 260), (640, 300), (800, 660), (460, 690), (240, 640)))
    shadow(img, whole, clip)
    put(img, poly(side), (176, 150, 250, 255))
    put(img, poly(bottom), (130, 98, 230, 255))
    put(img, poly(front), linear((S, S), [(0, (255, 255, 255)), (1, (226, 214, 255))], 100).convert("RGBA"))
    return img


# P6 — Prisma suave (cantos arredondados) com brilho dourado na saída da luz
def p6():
    from make_icon import star4
    img, clip = base([(0, (60, 24, 150)), (1, (130, 80, 255))], 60)
    img.alpha_composite(radial((S, S), (640 * U, 520 * U), 420 * U, (200, 160, 255), 0.4))
    glow_line(img, P((60, 660), (430, 560)), 26, (255, 255, 255), clip)
    fan(img, (600 * U, 520 * U), [(1000, 380), (1000, 520), (1000, 660)],
        [(214, 196, 255, 220), (170, 125, 255, 230), (255, 200, 110, 220)], clip, spread=40)
    tri = Image.new("L", (S, S), 0)
    td = ImageDraw.Draw(tri)
    pts = P((500, 250), (730, 690), (270, 690))
    td.polygon(pts, fill=255)
    tri = tri.filter(ImageFilter.GaussianBlur(26 * U)).point(lambda v: 255 if v > 150 else 0)
    tri = tri.filter(ImageFilter.GaussianBlur(2 * U))
    shadow(img, tri, clip)
    put(img, tri, linear((S, S), [(0, (255, 255, 255)), (1, (226, 212, 255))], 100).convert("RGBA"))
    cx, cy = 610 * U, 520 * U
    img.alpha_composite(radial((S, S), (cx, cy), 170 * U, (255, 200, 90), 0.95))
    d = ImageDraw.Draw(img)
    star4(d, cx, cy, 110 * U, (255, 205, 100, 255))
    star4(d, cx, cy, 60 * U, (255, 245, 210, 255))
    return img


OPTIONS = [p1, p2, p3, p4, p5, p6]
NAMES = ["B1 · Vidro refinado", "B2 · Plano minimalista", "B3 · A luz vira texto", "B4 · Leque vertical",
         "B5 · Prisma 3D", "B6 · Prisma suave com brilho"]

if __name__ == "__main__":
    out = sys.argv[1]
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        f = ImageFont.load_default()
    icons = [fn().resize((512, 512), Image.LANCZOS) for fn in OPTIONS]
    sheet = Image.new("RGBA", (1200, 660), (244, 243, 249, 255))
    d = ImageDraw.Draw(sheet)
    for i, ic in enumerate(icons):
        ic.save(f"{out}/opcao_B{i + 1}.png")
        x, y = (i % 3) * 400, (i // 3) * 330
        sheet.alpha_composite(ic.resize((220, 220), Image.LANCZOS), (x + 20, y + 24))
        dark = Image.new("RGBA", (60, 200), (32, 32, 36, 255))
        yy = 12
        for sz in (48, 32, 24, 16):
            sheet.alpha_composite(ic.resize((sz, sz), Image.LANCZOS), (x + 260 + (48 - sz) // 2, y + 24 + yy))
            dark.alpha_composite(ic.resize((sz, sz), Image.LANCZOS), (6 + (48 - sz) // 2, yy))
            yy += sz + 14
        sheet.alpha_composite(dark, (x + 320, y + 24))
        d.text((x + 20, y + 262), NAMES[i], font=f, fill=(30, 28, 40, 255))
    sheet.save(f"{out}/opcoes_prisma.png")
    print("ok")
