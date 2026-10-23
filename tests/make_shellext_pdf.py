"""PDF de teste para a extensão do Explorador: 3 páginas com título colorido, texto e uma página paisagem."""
import sys
import pymupdf

d = pymupdf.open()
for i in range(3):
    p = d.new_page(width=842, height=595) if i == 2 else d.new_page()
    p.draw_rect(pymupdf.Rect(40, 40, p.rect.width - 40, 120), color=(0.43, 0.24, 0.94), fill=(0.43, 0.24, 0.94))
    p.insert_text((60, 95), f"Lumen PDF - pagina {i + 1}", fontsize=28, color=(1, 1, 1))
    p.insert_textbox(pymupdf.Rect(60, 150, p.rect.width - 60, p.rect.height - 60),
                     "Contrato de cessao de creditos. " * 60, fontsize=11)
d.save(sys.argv[1])
