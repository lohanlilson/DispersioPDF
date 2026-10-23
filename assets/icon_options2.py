"""Segunda rodada: símbolos abstratos de luz, em violeta (sem folha)."""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont

from make_icon import linear, radial, squircle_mask, star4

S = 2048
U = S / 1024
V1, V2, V3 = (46, 16, 120), (109, 60, 240), (160, 110, 255)


def base(stops=((0, V1), (1, V2)), angle=60):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    box = [int(56 * U), int(56 * U), int(S - 56 * U), int(S - 56 * U)]
    mask = squircle_mask((S, S), box, int(236 * U))
    img.paste(linear((S, S), list(stops), angle=angle).convert("RGBA"), (0, 0), mask)
    return img, mask


def fill(img, m, color, clip=None):
    if clip is not None:
        m = ImageChops.multiply(m, clip)
    img.paste(Image.new("RGBA", (S, S), color), (0, 0), m)


def soft_shadow(img, m, clip, alpha=0.35, dy=18, blur=22):
    sh = Image.new("L", (S, S), 0)
    sh.paste(m, (0, int(dy * U)))
    sh = ImageChops.multiply(sh.filter(ImageFilter.GaussianBlur(blur * U)).point(lambda v: int(v * alpha)), clip)
    layer = Image.new("RGBA", (S, S), (20, 0, 60, 255))
    layer.putalpha(sh)
    img.alpha_composite(layer)


def poly_mask(pts):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


# 1 — Brilho de 4 pontas (símbolo de luz puro)
def a1():
    img, clip = base(((0, (38, 12, 104)), (0.6, V2), (1, (150, 90, 255))), 70)
    img.alpha_composite(radial((S, S), (512 * U, 512 * U), 420 * U, (190, 150, 255), 0.55))
    m = Image.new("L", (S, S), 0)
    star4(ImageDraw.Draw(m), 500 * U, 530 * U, 330 * U, 255)
    soft_shadow(img, m, clip)
    fill(img, m, (255, 255, 255, 255))
    m2 = Image.new("L", (S, S), 0)
    star4(ImageDraw.Draw(m2), 760 * U, 270 * U, 105 * U, 255)
    fill(img, m2, (226, 210, 255, 255))
    return img


# 2 — Prisma: feixe branco entra e sai abrindo em tons de violeta
def a2():
    img, clip = base(((0, (24, 10, 60)), (1, (70, 30, 160))), 80)
    d = ImageDraw.Draw(img)
    beam_in = poly_mask([(70 * U, 600 * U), (70 * U, 640 * U), (455 * U, 545 * U), (455 * U, 520 * U)])
    fill(img, beam_in, (255, 255, 255, 235), clip)
    cols = [(200, 170, 255), (160, 110, 255), (120, 70, 245), (220, 140, 255)]
    for k, c in enumerate(cols):
        y0 = 460 + k * 70
        ray = poly_mask([(560 * U, (500 + k * 22) * U), (560 * U, (522 + k * 22) * U),
                         (980 * U, (y0 + 80) * U), (980 * U, y0 * U)])
        fill(img, ray, c + (235,), clip)
    tri = poly_mask([(512 * U, 250 * U), (720 * U, 700 * U), (304 * U, 700 * U)])
    soft_shadow(img, tri, clip, alpha=0.5)
    glass = linear((S, S), [(0, (255, 255, 255)), (1, (214, 196, 255))], 90).convert("RGBA")
    glass.putalpha(tri.point(lambda v: int(v * 0.96)))
    img.alpha_composite(glass)
    return img


# 3 — Íris / abertura de lente (6 lâminas)
def a3():
    img, clip = base(((0, V1), (1, (130, 80, 255))), 45)
    cx, cy, R, r = 512 * U, 512 * U, 330 * U, 120 * U
    shades = [(255, 255, 255), (232, 222, 255), (210, 192, 255), (255, 255, 255), (232, 222, 255), (210, 192, 255)]
    for k in range(6):
        a0 = math.radians(k * 60 - 90)
        a1_ = math.radians((k + 1) * 60 - 90)
        p1 = (cx + R * math.cos(a0), cy + R * math.sin(a0))
        p2 = (cx + R * math.cos(a1_), cy + R * math.sin(a1_))
        q1 = (cx + r * math.cos(a0 + math.radians(30)), cy + r * math.sin(a0 + math.radians(30)))
        q2 = (cx + r * math.cos(a1_ + math.radians(30)), cy + r * math.sin(a1_ + math.radians(30)))
        m = poly_mask([p1, p2, q2, q1])
        fill(img, m, shades[k] + (255,))
    hole = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hole).regular_polygon((cx, cy, r * 0.98), 6, rotation=0, fill=255)
    img.alpha_composite(radial((S, S), (cx, cy), r * 1.6, (255, 220, 140), 1.0))
    fill(img, hole, (255, 214, 120, 255))
    star4(ImageDraw.Draw(img), cx, cy, r * 0.7, (255, 255, 255, 255))
    return img


# 4 — Sol geométrico (círculo + raios arredondados)
def a4():
    img, clip = base(((0, (60, 20, 150)), (1, (140, 80, 255))), 120)
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    cx, cy = 512 * U, 512 * U
    d.ellipse([cx - 150 * U, cy - 150 * U, cx + 150 * U, cy + 150 * U], fill=255)
    for k in range(8):
        a = math.radians(k * 45)
        long = 330 if k % 2 == 0 else 290
        x0, y0 = cx + math.cos(a) * 205 * U, cy + math.sin(a) * 205 * U
        x1, y1 = cx + math.cos(a) * long * U, cy + math.sin(a) * long * U
        d.line([(x0, y0), (x1, y1)], fill=255, width=int(56 * U))
        for x, y in ((x0, y0), (x1, y1)):
            d.ellipse([x - 28 * U, y - 28 * U, x + 28 * U, y + 28 * U], fill=255)
    soft_shadow(img, m, clip)
    fill(img, m, (255, 255, 255, 255))
    return img


# 5 — Feixes concêntricos saindo de um ponto (luz se espalhando)
def a5():
    img, clip = base(((0, (34, 12, 92)), (1, V2)), 45)
    d = ImageDraw.Draw(img)
    ox, oy = 270 * U, 760 * U
    for k, (r, a) in enumerate(((560, 255), (420, 255), (280, 255))):
        col = [(255, 255, 255), (220, 200, 255), (180, 150, 255)][k]
        d.arc([ox - r * U, oy - r * U, ox + r * U, oy + r * U], start=-90, end=0, fill=col + (255,), width=int(70 * U))
        for ang in (-90, 0):
            x, y = ox + math.cos(math.radians(ang)) * r * U, oy + math.sin(math.radians(ang)) * r * U
            d.ellipse([x - 35 * U, y - 35 * U, x + 35 * U, y + 35 * U], fill=col + (255,))
    img.alpha_composite(radial((S, S), (ox, oy), 200 * U, (255, 210, 120), 1.0))
    d = ImageDraw.Draw(img)
    d.ellipse([ox - 80 * U, oy - 80 * U, ox + 80 * U, oy + 80 * U], fill=(255, 205, 110, 255))
    return img


# 6 — Gema facetada (luz refletindo em facetas)
def a6():
    img, clip = base(((0, (30, 10, 80)), (1, (90, 40, 200))), 70)
    cx = 512 * U
    top, mid, bot = 250 * U, 430 * U, 820 * U
    L, R = 230 * U, 794 * U
    tl, tr = 360 * U, 664 * U
    facets = [
        ([(tl, top), (cx, top), (cx - 60 * U, mid)], (236, 226, 255)),
        ([(cx, top), (tr, top), (cx + 60 * U, mid)], (255, 255, 255)),
        ([(L, mid), (tl, top), (cx - 60 * U, mid)], (196, 170, 255)),
        ([(cx - 60 * U, mid), (cx, top), (cx + 60 * U, mid)], (214, 196, 255)),
        ([(cx + 60 * U, mid), (tr, top), (R, mid)], (226, 210, 255)),
        ([(L, mid), (cx - 60 * U, mid), (cx, bot)], (150, 110, 250)),
        ([(cx - 60 * U, mid), (cx + 60 * U, mid), (cx, bot)], (190, 160, 255)),
        ([(cx + 60 * U, mid), (R, mid), (cx, bot)], (230, 214, 255)),
    ]
    whole = poly_mask([(tl, top), (tr, top), (R, mid), (cx, bot), (L, mid)])
    soft_shadow(img, whole, clip, alpha=0.5)
    for pts, c in facets:
        fill(img, poly_mask(pts), c + (255,))
    star4(ImageDraw.Draw(img), 700 * U, 300 * U, 70 * U, (255, 255, 255, 255))
    return img


OPTIONS = [a1, a2, a3, a4, a5, a6]
NAMES = ["A · Brilho", "B · Prisma", "C · Íris de lente", "D · Sol geométrico", "E · Luz se espalhando",
         "F · Gema facetada"]

if __name__ == "__main__":
    out = sys.argv[1]
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        f = ImageFont.load_default()
    icons = [fn().resize((512, 512), Image.LANCZOS) for fn in OPTIONS]
    W, H = 3 * 400, 2 * 330
    sheet = Image.new("RGBA", (W, H), (244, 243, 249, 255))
    d = ImageDraw.Draw(sheet)
    for i, ic in enumerate(icons):
        ic.save(f"{out}/opcao_{'ABCDEF'[i]}.png")
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
    sheet.save(f"{out}/opcoes_icone2.png")
    print("ok")
