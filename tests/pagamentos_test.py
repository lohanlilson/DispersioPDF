"""Boletos, Pix e chaves de NF-e: leitura no texto e nos códigos desenhados, conferência dos dígitos e adulteração."""
import io, os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
import zxingcpp
from PIL import Image
from dispersio import pagamentos as P

HOJE = date(2026, 10, 27)

# --- dígitos (exemplos públicos: Banco do Brasil e manual do Pix do Banco Central)
LD_BB = "00190500954014481606906809350314337370000000100"
BC_BB = "00193373700000001000500940144816060680935031"
assert not P.check_boleto_line(LD_BB) and P.boleto_line_to_barcode(LD_BB) == BC_BB
assert P.boleto_barcode_to_line(BC_BB) == LD_BB
PIX = ("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR"
       "5913Fulano de Tal6008BRASILIA62070503***63041D3D")
assert P.pix_item(0, PIX).ok
assert not P.pix_item(0, PIX.replace("Fulano", "Fulana")).ok, "Pix alterado"
assert "2º campo" in P.check_boleto_line(LD_BB[:12] + "9" + LD_BB[13:])

# boleto Bradesco com valor e vencimento (montado pelas regras da FEBRABAN)
def boleto(banco, fator, cents, livre):
    sem_dv = banco + "9" + f"{fator:04d}" + f"{cents:010d}" + livre
    bc = sem_dv[:4] + str(P.mod11_boleto(sem_dv)) + sem_dv[4:]
    return bc
BC_BRAD = boleto("237", 1000 + (date(2026, 11, 10) - date(2025, 2, 22)).days, 123456, "0123456789012345678901234")
LD_BRAD = P.boleto_barcode_to_line(BC_BRAD)
it = P.boleto_item(0, LD_BRAD, HOJE)
d = dict(it.details)
assert it.ok and it.title == "Boleto Bradesco", it
assert d["Valor"] == "R$ 1.234,56", d
assert d["Vencimento"] == "10/11/2026", d
BC_OUTRO = boleto("237", 1000 + (date(2026, 11, 10) - date(2025, 2, 22)).days, 923456, "9993456789012345678901234")

# arrecadação (conta de energia), valor efetivo módulo 10
sem = ("836" + "00000012345" + "0055" + "1234567890123456789012345")[:43]
bc = sem[:3] + str(P.mod10(sem)) + sem[3:]
assert P.arrec_barcode_ok(bc), bc
LD_ARR = P.arrec_barcode_to_line(bc)
ia = P.arrec_item(0, LD_ARR)
assert ia.ok and dict(ia.details)["Valor"] == "R$ 123,45" and "Energia" in ia.title

# chave de NF-e de Goiás
base = "52" + "2610" + "53176704000186" + "55" + "001" + "000012345" + "1" + "12345678"
CH = base + str(P.mod11_zero(base))
ic = P.chave_item(0, CH)
assert ic.ok and ic.title == "NF-e nº 12345" and "53.176.704/0001-86" in dict(ic.details)["Emitente"], ic.details
assert not P.chave_ok(CH[:-1] + str((int(CH[-1]) + 1) % 10))
# CNPJ alfanumérico (a partir de 2026)
base2 = "35" + "2609" + "12ABC34501DE35" + "55" + "001" + "000000777" + "1" + "87654321"
assert P.chave_ok(base2 + str(P.mod11_zero(base2)))

# --- PDF de teste: texto + códigos desenhados
def png(fmt, txt, scale):
    img = zxingcpp.create_barcode(txt, fmt).to_image(scale=scale)
    im = Image.fromarray(img) if not isinstance(img, Image.Image) else img
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

doc = pymupdf.open()
p = doc.new_page()                                           # 1: boleto com linha e código conferindo
p.insert_text((40, 60), "Banco Bradesco   237-2", fontsize=12)
p.insert_text((40, 90), P.fmt_boleto(LD_BRAD), fontsize=11)
p.insert_image(pymupdf.Rect(40, 110, 440, 160), stream=png(zxingcpp.BarcodeFormat.ITF, BC_BRAD, 3))
p = doc.new_page()                                           # 2: Pix (QR + copia e cola quebrado em linhas)
p.insert_image(pymupdf.Rect(40, 40, 240, 240), stream=png(zxingcpp.BarcodeFormat.QRCode, PIX, 6))
p.insert_text((40, 270), "Pix copia e cola:", fontsize=10)
p.insert_text((40, 285), PIX[:70], fontsize=8)
p.insert_text((40, 297), PIX[70:], fontsize=8)
p = doc.new_page()                                           # 3: DANFE (chave em grupos + Code128)
p.insert_text((40, 60), "CHAVE DE ACESSO", fontsize=8)
p.insert_text((40, 75), P.fmt_chave(CH), fontsize=10)
p.insert_image(pymupdf.Rect(40, 90, 500, 130), stream=png(zxingcpp.BarcodeFormat.Code128, CH, 2))
p = doc.new_page()                                           # 4: boleto adulterado (linha de outro boleto)
p.insert_text((40, 90), P.fmt_boleto(P.boleto_barcode_to_line(BC_OUTRO)), fontsize=11)
p.insert_image(pymupdf.Rect(40, 110, 440, 160), stream=png(zxingcpp.BarcodeFormat.ITF, BC_BRAD, 3))
p = doc.new_page()                                           # 5: linha digitada errada + conta de energia
p.insert_text((40, 90), P.fmt_boleto(LD_BB[:12] + "9" + LD_BB[13:]), fontsize=11)
p.insert_text((40, 130), P.fmt_arrec(LD_ARR), fontsize=11)
p.insert_text((40, 170), "Pedido 0000000000000000000000000000000000000000000000 e telefone 62 99999-0000", fontsize=9)

items = P.scan(doc, HOJE)
by = {}
for i in items:
    by.setdefault(i.page, []).append(i)
    print(i.page + 1, i.kind, i.ok, i.source, i.title, i.summary, i.problem)
b1 = by[0]; assert len(b1) == 1 and b1[0].ok and b1[0].source == "texto e código" and b1[0].rect
assert [x.kind for x in by[1]] == ["pix"] and by[1][0].ok and by[1][0].source == "texto e código"
assert [x.kind for x in by[2]] == ["nfe"] and by[2][0].source == "texto e código"
bad = [x for x in by[3] if x.source == "texto"]
assert bad and not bad[0].ok and "NÃO confere" in bad[0].problem
assert any(x.source == "código" and x.ok for x in by[3])
k5 = sorted(x.kind for x in by[4])
assert k5 == ["arrecadacao", "boleto"], k5
assert not [x for x in by[4] if x.kind == "boleto"][0].ok
assert P.find_in_text("Telefone 62 3333-4444 CPF 123.456.789-09 valor 1.234,56 " + "1" * 60) == []
print("boletos, Pix e NF-e ok")

# --- interface: faixa ao abrir e lista
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile, time
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
app.setApplicationName("DispersioPDF-teste")
from dispersio.config import cfg
from dispersio import dialogs
from dispersio.mainwindow import MainWindow
cfg.set("detect_payments", True)
fn = os.path.join(tempfile.mkdtemp(), "boletos.pdf"); doc.save(fn)
w = MainWindow(); w.show(); w.open_path(fn)
t = w.cur(); end = time.time() + 30
while t.pay_items is None and time.time() < end:
    app.processEvents(); time.sleep(0.02)
assert t.pay_items and t.pay_bar.isVisible()
assert not t.pay_bar.main.ok, "a faixa mostra primeiro o que tem problema"
shown = []
dialogs.PaymentsDialog.exec = lambda self: shown.append(self) or 0
w.run_tool("payments")
assert shown
t.goto_rect(2, (40, 60, 300, 75))
# documento sem nada: sem faixa, e a ferramenta avisa
d2 = pymupdf.open(); d2.new_page().insert_text((72, 72), "Relatório sem boleto")
fn2 = fn.replace("boletos", "vazio"); d2.save(fn2)
w.open_path(fn2); t2 = w.cur(); end = time.time() + 30
while t2.pay_items is None and time.time() < end:
    app.processEvents(); time.sleep(0.02)
assert t2.pay_items == [] and not t2.pay_bar.isVisible()
msgs = []
QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2]))
w.run_tool("payments")
assert msgs and "Nenhum boleto" in msgs[0]
print("interface de boletos ok")
