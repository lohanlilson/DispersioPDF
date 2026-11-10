"""Proteção contra golpes: links enganosos, JavaScript/ações automáticas/anexos executáveis, botão falso,
Pix para quem não aparece no documento e boleto com banco trocado."""
import os, sys, tempfile
from datetime import date
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
app = QApplication.instance() or QApplication([])
from dispersio import seguranca as seg, seguranca_ui, pagamentos as P, ops
from dispersio.config import cfg

# --- links
L = seg.link_risk
assert L("https://www.bradesco.com.br/x").level < seg.WARN
assert L("https://bradesco-seguro.top/login").level == seg.DANGER
assert L("https://evil.com/x", "Acesse www.itau.com.br").level == seg.DANGER, "texto mostra um site, link vai para outro"
assert L("https://www.itau.com.br", "www.itau.com.br").level < seg.WARN
assert L("http://192.168.0.10/boleto").level == seg.DANGER
assert L("https://bit.ly/x").level == seg.WARN
assert L("https://xn--bradsco-6ya.com").level == seg.DANGER
assert L("https://arquivos.com/nota-fiscal.exe").level == seg.DANGER
assert L("https://gov-br.online/cpf").level == seg.DANGER and L("https://www.gov.br/receita").level < seg.WARN
assert L("https://receitasdebolo.com").level < seg.WARN and L("https://capitaurbana.com").level < seg.WARN
assert L("javascript:alert(1)").level == seg.DANGER and L("file:///C:/x.exe").level == seg.DANGER
assert L("https://www.google.com@phish.ru/x").level == seg.DANGER
assert L("https://doi.org/10.1/x", "https://doi.org/10.1/x").level < seg.WARN
assert L("mailto:a@b.com").level == seg.INFO

# --- documento de golpe
d = pymupdf.open()
p = d.new_page()
p.insert_text((72, 60), "Documento protegido - clique para visualizar", fontsize=12)
p.draw_rect(pymupdf.Rect(60, 100, 540, 700), color=(0.6, 0.6, 0.6), fill=(0.9, 0.9, 0.9))
p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(60, 100, 540, 700), "uri": "https://office365-login.xyz/a"})
p2 = d.new_page()
p2.insert_text((72, 72), "Pague em www.bradesco.com.br", fontsize=12)
p2.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(70, 60, 300, 76), "uri": "https://pagamento-seguro.top/b"})
d.embfile_add("nota_fiscal.exe", b"MZ fake", filename="nota_fiscal.exe")
js = d.get_new_xref()
d.update_object(js, "<</S/JavaScript/JS(app.alert\\('oi'\\))>>")
d.xref_set_key(d.pdf_catalog(), "OpenAction", f"{js} 0 R")
data = d.tobytes()
t = seg.scan(pymupdf.open(stream=data, filetype="pdf"))
titles = [x.title for x in t]
print(titles)
assert t[0].level == seg.DANGER
assert any("JavaScript" in x for x in titles), titles
assert any("programa anexado" in x for x in titles), titles
assert any("botão" in x for x in titles), titles
assert any("Link suspeito na página 2" in x for x in titles), titles
clean = pymupdf.open(stream=data, filetype="pdf")
ops.remove_active_content(clean)
rest = [x.title for x in seg.scan(pymupdf.open(stream=clean.tobytes(), filetype="pdf"))]
assert not any("JavaScript" in x or "anexado" in x for x in rest), rest
assert clean[1].get_text().strip().startswith("Pague"), "o conteúdo fica"

# documento comum não acusa nada
ok = pymupdf.open(); pg = ok.new_page(); pg.insert_text((72, 72), "Contrato. Veja https://www.gov.br")
pg.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(70, 60, 300, 76), "uri": "https://www.gov.br"})
assert seg.scan(ok) == [], seg.scan(ok)

# --- Pix para quem não aparece no documento / banco trocado no boleto
PIX = ("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR"
       "5913Fulano de Tal6008BRASILIA62070503***63041D3D")
texto = ("NACIONAL SECURITIZADORA S.A. — Cobrança referente ao contrato 123. " * 5) + "\nPix copia e cola:\n" + PIX
dd = pymupdf.open(); dd.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=8)
items = P.scan(dd, images=False)
pix = [i for i in items if i.kind == "pix"]
assert pix and "não aparece" in pix[0].alert, [(i.kind, i.alert) for i in items]
texto2 = texto.replace("NACIONAL SECURITIZADORA S.A.", "FULANO DE TAL")
dd = pymupdf.open(); dd.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto2, fontsize=8)
assert not [i for i in P.scan(dd, images=False) if i.kind == "pix"][0].alert

def boleto(banco, fator, cents, livre):
    sem_dv = banco + "9" + f"{fator:04d}" + f"{cents:010d}" + livre
    return sem_dv[:4] + str(P.mod11_boleto(sem_dv)) + sem_dv[4:]
LD = P.boleto_barcode_to_line(boleto("341", 1000 + (date(2026, 11, 10) - date(2025, 2, 22)).days, 5000, "0123456789012345678901234"))
dd = pymupdf.open(); dd.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), f"Banco Bradesco 237-2\n{P.fmt_boleto(LD)}\nBeneficiário: Loja", fontsize=10)
b = [i for i in P.scan(dd, images=False) if i.kind == "boleto"][0]
assert "Itaú" in b.alert and "Bradesco" in b.alert, b.alert
dd = pymupdf.open(); dd.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), f"Itaú 341-7  CPF 123.456.789-01\n{P.fmt_boleto(LD)}", fontsize=10)
assert not [i for i in P.scan(dd, images=False) if i.kind == "boleto"][0].alert

# --- na janela: faixa de alerta, confirmação de link, remover perigo
from dispersio.mainwindow import MainWindow
import dispersio.viewer as V
opened = []
V.QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toString()))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
answer = [QDialog.Rejected]
seguranca_ui.LinkDialog.exec = lambda self: answer[0]
w = MainWindow(); w.show()
tmp = tempfile.mkdtemp(); fn = os.path.join(tmp, "golpe.pdf"); open(fn, "wb").write(data)
w.open_path(fn)
tab = w.tab_widgets[-1]
import time
for _ in range(100):
    app.processEvents(); time.sleep(0.05)
    if tab.threats is not None:
        break
assert tab.sec_bar.isVisible() and "golpe" in tab.sec_bar.text.text(), tab.sec_bar.text.text()
tab.view._follow_link({"kind": pymupdf.LINK_URI, "uri": "https://pagamento-seguro.top/b", "from": pymupdf.Rect(70, 60, 300, 76)}, 1)
assert not opened, "link perigoso recusado não abre"
answer[0] = QDialog.Accepted
tab.view._follow_link({"kind": pymupdf.LINK_URI, "uri": "https://pagamento-seguro.top/b", "from": pymupdf.Rect(70, 60, 300, 76)}, 1)
assert opened == ["https://pagamento-seguro.top/b"], opened
old = cfg.get("confirm_links")
cfg.set("confirm_links", False); answer[0] = QDialog.Rejected
tab.view._follow_link({"kind": pymupdf.LINK_URI, "uri": "https://www.gov.br/x", "from": pymupdf.Rect(0, 0, 1, 1)}, 1)
assert opened[-1] == "https://www.gov.br/x", "site comum abre direto quando o usuário desligou a pergunta"
tab.view._follow_link({"kind": pymupdf.LINK_URI, "uri": "http://10.0.0.1/x", "from": pymupdf.Rect(0, 0, 1, 1)}, 1)
assert opened[-1] != "http://10.0.0.1/x", "link perigoso sempre pergunta"
cfg.set("confirm_links", old)
tab.sec_bar._clean()
assert tab.doc.embfile_count() == 0 and tab.modified
tab.undo(); assert tab.doc.embfile_count() == 1, "remover perigo dá para desfazer"
while len(w.tab_widgets) > 1:
    w.close_tab(len(w.tab_widgets) - 1)
app.processEvents()
print("segurança ok")
