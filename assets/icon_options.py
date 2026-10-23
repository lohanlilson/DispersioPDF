"""Seis propostas de ícone para o Lumen PDF (escolha uma; a escolhida vira o app_icon do make_icon.py)."""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont

from make_icon import linear, radial, squircle_mask, star4, page_mask

S = 2048
U = S / 1024


def base(stops, angle=60, glow=None):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    box = [int(56 * U), int(56 * U), int(S - 56 * U), int(S - 56 * U)]
    mask = squircle_mask((S, S), box, int(236 * U))
    bg = linear((S, S), stops, angle=angle).convert("RGBA")
    for g in glow or []:
        bg.alpha_composite(radial((S, S), *g))
    img.paste(bg, (0, 0), mask)
    return img, mask


def paste_color(img, mask, color):
    img.paste(Image.new("RGBA", (S, S), color), (0, 0), mask)


def shadow(img, mask_shape, dx=10, dy=24, blur=24, alpha=0.45, color=(10, 0, 40), clip=None):
    sh = Image.new("L", (S, S), 0)
    sh.paste(mask_shape, (int(dx * U), int(dy * U)))
    sh = sh.filter(ImageFilter.GaussianBlur(blur * U)).point(lambda v: int(v * alpha))
    if clip is not None:
        sh = ImageChops.multiply(sh, clip)
    layer = Image.new("RGBA", (S, S), color + (255,))
    layer.putalpha(sh)
    img.alpha_composite(layer)


def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf"):
        try:
            return ImageFont.truetype(f, int(size))
        except OSError:
            pass
    return ImageFont.load_default()


# 1 — Monograma "L" luminoso (minimalista, premium)
def opt1():
    img, clip = base([(0, (18, 16, 32)), (1, (40, 32, 70))], 70,
                     [((760 * U, 300 * U), 520 * U, (255, 170, 60), 0.45)])
    L = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(L)
    d.rounded_rectangle([330 * U, 250 * U, 470 * U, 780 * U], radius=70 * U, fill=255)
    d.rounded_rectangle([330 * U, 640 * U, 700 * U, 780 * U], radius=70 * U, fill=255)
    shadow(img, L, clip=clip, alpha=0.6, color=(0, 0, 0))
    grad = linear((S, S), [(0, (255, 255, 255)), (1, (255, 226, 170))], 90).convert("RGBA")
    img.paste(grad, (0, 0), L)
    img.alpha_composite(radial((S, S), (700 * U, 330 * U), 300 * U, (255, 196, 70), 0.9))
    d = ImageDraw.Draw(img)
    star4(d, 700 * U, 330 * U, 170 * U, (255, 200, 80, 255))
    star4(d, 700 * U, 330 * U, 100 * U, (255, 240, 190, 255))
    star4(d, 700 * U, 330 * U, 45 * U, (255, 255, 255, 255))
    return img


# 2 — Sol nascente sobre a página (lúmen = luz que nasce do documento)
def opt2():
    img, clip = base([(0, (255, 120, 60)), (0.55, (240, 60, 90)), (1, (140, 40, 160))], 120)
    pm = page_mask((S, S), 290 * U, 210 * U, 734 * U, 814 * U, 140 * U, 40 * U)
    shadow(img, pm, clip=clip, alpha=0.5, color=(80, 0, 40))
    paste_color(img, pm, (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    d.polygon([(734 * U - 140 * U, 210 * U), (734 * U - 140 * U, 350 * U), (734 * U, 350 * U)], fill=(255, 214, 196, 255))
    cx, cy, r = 512 * U, 640 * U, 150 * U
    sun = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sun).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    ImageDraw.Draw(sun).rectangle([0, cy, S, S], fill=0)
    img.paste(linear((S, S), [(0, (255, 200, 70)), (1, (255, 110, 60))], 90).convert("RGBA"), (0, 0), sun)
    for k in range(7):
        a = math.pi + math.pi * (k + 0.5) / 7
        x0, y0 = cx + math.cos(a) * (r + 30 * U), cy + math.sin(a) * (r + 30 * U)
        x1, y1 = cx + math.cos(a) * (r + 95 * U), cy + math.sin(a) * (r + 95 * U)
        d.line([(x0, y0), (x1, y1)], fill=(255, 150, 60, 255), width=int(28 * U))
        d.ellipse([x0 - 14 * U, y0 - 14 * U, x0 + 14 * U, y0 + 14 * U], fill=(255, 150, 60, 255))
        d.ellipse([x1 - 14 * U, y1 - 14 * U, x1 + 14 * U, y1 + 14 * U], fill=(255, 150, 60, 255))
    d.rounded_rectangle([370 * U, 668 * U, 654 * U, 696 * U], radius=14 * U, fill=(255, 140, 70, 255))
    d.rounded_rectangle([410 * U, 724 * U, 614 * U, 750 * U], radius=13 * U, fill=(255, 190, 160, 255))
    return img


# 3 — Feixe de luz atravessando a página (estilo janela iluminada)
def opt3():
    img, clip = base([(0, (12, 24, 64)), (1, (24, 58, 140))], 60)
    pm = page_mask((S, S), 290 * U, 200 * U, 734 * U, 824 * U, 150 * U, 40 * U)
    shadow(img, pm, clip=clip, alpha=0.6, color=(0, 0, 20))
    paste_color(img, pm, (246, 248, 255, 255))
    beam = Image.new("L", (S, S), 0)
    ImageDraw.Draw(beam).polygon([(120 * U, 120 * U), (420 * U, 120 * U), (920 * U, 920 * U), (520 * U, 920 * U)], fill=210)
    beam = ImageChops.multiply(beam.filter(ImageFilter.GaussianBlur(30 * U)), clip)
    glow = linear((S, S), [(0, (255, 240, 180)), (1, (255, 170, 60))], 45).convert("RGBA")
    glow.putalpha(beam)
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    for k, w in enumerate((300, 340, 260, 320)):
        yy = (420 + k * 80) * U
        d.rounded_rectangle([350 * U, yy, (350 + w) * U, yy + 30 * U], radius=15 * U, fill=(70, 90, 150, 200))
    d.polygon([(734 * U - 150 * U, 200 * U), (734 * U - 150 * U, 350 * U), (734 * U, 350 * U)], fill=(200, 210, 240, 255))
    return img


# 4 — Lente / abertura (anéis de luz com a página no centro)
def opt4():
    img, clip = base([(0, (0, 150, 160)), (0.5, (20, 110, 200)), (1, (90, 60, 220))], 45)
    d = ImageDraw.Draw(img)
    cx, cy = 512 * U, 512 * U
    for r, a in ((380, 40), (310, 70), (240, 110)):
        d.ellipse([cx - r * U, cy - r * U, cx + r * U, cy + r * U], outline=(255, 255, 255, a), width=int(26 * U))
    img.alpha_composite(radial((S, S), (cx, cy), 330 * U, (255, 255, 255), 0.45))
    pm = page_mask((S, S), 400 * U, 330 * U, 624 * U, 694 * U, 80 * U, 26 * U)
    shadow(img, pm, clip=clip, alpha=0.5, color=(0, 20, 60), dy=16, blur=16)
    paste_color(img, pm, (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    d.polygon([(544 * U, 330 * U), (544 * U, 410 * U), (624 * U, 410 * U)], fill=(190, 225, 245, 255))
    d.text((cx, 560 * U), "PDF", font=font(78 * U), fill=(20, 110, 200, 255), anchor="mm")
    return img


# 5 — Lâmpada formada pela página dobrada (ideia + luz + documento)
def opt5():
    img, clip = base([(0, (255, 190, 40)), (1, (255, 120, 30))], 120,
                     [((512 * U, 380 * U), 520 * U, (255, 255, 230), 0.55)])
    d = ImageDraw.Draw(img)
    cx, cy, r = 512 * U, 430 * U, 230 * U
    bulb = Image.new("L", (S, S), 0)
    bd = ImageDraw.Draw(bulb)
    bd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    bd.polygon([(cx - 150 * U, cy + 170 * U), (cx + 150 * U, cy + 170 * U), (cx + 110 * U, cy + 320 * U),
                (cx - 110 * U, cy + 320 * U)], fill=255)
    shadow(img, bulb, clip=clip, alpha=0.35, color=(120, 50, 0))
    paste_color(img, bulb, (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    # página dentro da lâmpada
    d.rounded_rectangle([cx - 95 * U, cy - 130 * U, cx + 95 * U, cy + 120 * U], radius=16 * U, outline=(255, 140, 30, 255),
                        width=int(18 * U))
    for k in range(3):
        yy = cy - 60 * U + k * 50 * U
        d.rounded_rectangle([cx - 55 * U, yy, cx + 55 * U, yy + 18 * U], radius=9 * U, fill=(255, 170, 70, 255))
    for k in range(3):
        yy = cy + 345 * U + k * 52 * U
        d.rounded_rectangle([cx - 100 * U + k * 18 * U, yy, cx + 100 * U - k * 18 * U, yy + 34 * U], radius=17 * U,
                            fill=(120, 60, 10, 255))
    for a in (-60, -30, 0, 30, 60):
        rad = math.radians(a - 90)
        x0, y0 = cx + math.cos(rad) * (r + 40 * U), cy + math.sin(rad) * (r + 40 * U)
        x1, y1 = cx + math.cos(rad) * (r + 100 * U), cy + math.sin(rad) * (r + 100 * U)
        d.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 255), width=int(26 * U))
    return img


# 6 — Selo "PDF" moderno com brilho (estilo dos leitores profissionais, cor própria)
def opt6():
    img, clip = base([(0, (230, 40, 90)), (1, (130, 30, 200))], 60,
                     [((780 * U, 260 * U), 420 * U, (255, 210, 120), 0.6)])
    pm = page_mask((S, S), 250 * U, 170 * U, 774 * U, 854 * U, 170 * U, 46 * U)
    shadow(img, pm, clip=clip, alpha=0.55, color=(60, 0, 40))
    paste_color(img, pm, (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    d.polygon([(604 * U, 170 * U), (604 * U, 340 * U), (774 * U, 340 * U)], fill=(255, 220, 230, 255))
    d.text((512 * U, 610 * U), "PDF", font=font(210 * U), fill=(200, 35, 110, 255), anchor="mm")
    for k, w in enumerate((330, 260)):
        yy = (330 + k * 70) * U
        d.rounded_rectangle([330 * U, yy, (330 + w) * U, yy + 34 * U], radius=17 * U, fill=(240, 220, 236, 255))
    cx, cy = 700 * U, 760 * U
    img.alpha_composite(radial((S, S), (cx, cy), 220 * U, (255, 200, 80), 0.9))
    d = ImageDraw.Draw(img)
    star4(d, cx, cy, 150 * U, (255, 200, 80, 255))
    star4(d, cx, cy, 90 * U, (255, 240, 190, 255))
    star4(d, cx, cy, 40 * U, (255, 255, 255, 255))
    return img


OPTIONS = [opt1, opt2, opt3, opt4, opt5, opt6]
NAMES = ["1 · Monograma L luminoso", "2 · Sol nascendo da página", "3 · Feixe de luz na página",
         "4 · Lente de luz", "5 · Lâmpada-documento", "6 · Selo PDF com brilho"]

if __name__ == "__main__":
    out = sys.argv[1]
    icons = [f().resize((512, 512), Image.LANCZOS) for f in OPTIONS]
    for i, ic in enumerate(icons, 1):
        ic.save(f"{out}/opcao{i}.png")
    W, H = 3 * 400, 2 * 440
    sheet = Image.new("RGBA", (W, H), (244, 243, 249, 255))
    d = ImageDraw.Draw(sheet)
    f = font(22)
    for i, ic in enumerate(icons):
        x, y = (i % 3) * 400, (i // 3) * 440
        sheet.alpha_composite(ic.resize((220, 220), Image.LANCZOS), (x + 20, y + 30))
        # tamanhos pequenos: claro e escuro
        dark = Image.new("RGBA", (130, 220), (32, 32, 36, 255))
        yy = 12
        for sz in (48, 32, 24, 16):
            sheet.alpha_composite(ic.resize((sz, sz), Image.LANCZOS), (x + 260 + (48 - sz) // 2, y + 30 + yy))
            dark.alpha_composite(ic.resize((sz, sz), Image.LANCZOS), (70 + (48 - sz) // 2 - 60, yy))
            yy += sz + 14
        sheet.alpha_composite(dark.crop((0, 0, 60, 200)), (x + 320, y + 30))
        d.text((x + 20, y + 268), NAMES[i], font=f, fill=(30, 28, 40, 255))
    sheet.save(f"{out}/opcoes_icone.png")
    print("ok")
