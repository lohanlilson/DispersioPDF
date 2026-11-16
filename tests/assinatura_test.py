"""Conferência de assinaturas: e-CNPJ mostra o responsável (nome e CPF) gravado no certificado ICP-Brasil."""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from asn1crypto import core
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
import pymupdf

from dispersio import signing

falhas = 0


def check(ok, msg):
    global falhas
    print(("OK  " if ok else "ERRO") + " " + msg)
    falhas += not ok


def cert(cn, others):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil")])
    b = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(7)
         .not_valid_before(datetime.datetime(2025, 1, 1)).not_valid_after(datetime.datetime(2035, 1, 1)))
    if others:
        b = b.add_extension(x509.SubjectAlternativeName(
            [x509.OtherName(x509.ObjectIdentifier(oid), val) for oid, val in others]), False)
    c = b.sign(key, hashes.SHA256())
    pfx = os.path.join(tempfile.mkdtemp(), "c.pfx")
    open(pfx, "wb").write(pkcs12.serialize_key_and_certificates(b"t", key, c, None,
                                                                serialization.BestAvailableEncryption(b"123")))
    return pfx


def octet(s):
    return core.OctetString(s.encode("latin-1")).dump()


doc = pymupdf.open()
doc.new_page()
pdf = doc.tobytes()

ecnpj = cert("EMPRESA TESTE LTDA:12345678000195", [
    ("2.16.76.1.3.4", octet("01021980" + "12345678909" + "0" * 11 + "123456789      " + "SSPGO     ")),
    ("2.16.76.1.3.2", core.PrintableString("MARIA DE SOUZA").dump()),
    ("2.16.76.1.3.3", octet("12345678000195"))])
ecpf = cert("JOAO DA SILVA:98765432100", [
    ("2.16.76.1.3.1", octet("15061990" + "98765432100" + "0" * 11 + "0" * 15 + " " * 10))])

for pfx, esperado in ((ecnpj, "e-CNPJ"), (ecpf, "e-CPF")):
    signer = signing.load_pfx(pfx, "123")
    out = signing.sign_pdf_bytes(pdf, signer, 0, (50, 50, 250, 110), 842, reason="teste")
    r = signing.validate(out)[0]
    c = r["cert"]
    print("   ", {k: v for k, v in c.items() if k in ("tipo", "nome", "cnpj", "responsavel", "responsavel_cpf", "titular_cpf")})
    check(c.get("tipo") == esperado, f"tipo {esperado}")
    if esperado == "e-CNPJ":
        check(c.get("nome") == "EMPRESA TESTE LTDA" and c.get("cnpj") == "12.345.678/0001-95", "empresa e CNPJ")
        check(c.get("responsavel") == "MARIA DE SOUZA" and c.get("responsavel_cpf") == "123.456.789-09"
              and c.get("responsavel_nascimento") == "01/02/1980", "responsável, CPF e nascimento")
        check(signing.signer_label(r) == "EMPRESA TESTE LTDA (por MARIA DE SOUZA)", "rótulo da lista")
        res_cnpj = r
    else:
        check(c.get("titular_cpf") == "987.654.321-00" and not c.get("responsavel"), "e-CPF: CPF do titular")
        check(signing.signer_label(r) == "JOAO DA SILVA", "rótulo e-CPF")

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from dispersio import dialogs
dlg = dialogs.SignatureInfoDialog(None, res_cnpj)
from PySide6.QtWidgets import QLabel
txt = " ".join(w.text() for w in dlg.findChildren(QLabel))
check("Responsável" in txt and "MARIA DE SOUZA" in txt and "123.456.789-09" in txt, "janela de validação mostra o responsável")

from dispersio.mainwindow import MainWindow
win = MainWindow(); win.resize(1200, 800); win.show()
signer = signing.load_pfx(ecnpj, "123")
assinado = signing.sign_pdf_bytes(pdf, signer, 0, (50, 50, 250, 110), 842)
caminho = os.path.join(tempfile.mkdtemp(), "assinado.pdf")
open(caminho, "wb").write(assinado)
win.open_path(caminho)
import time
fim = time.time() + 30
tab = win.cur()
while time.time() < fim and not tab.sig_results:
    app.processEvents()
    time.sleep(0.05)
for _ in range(20):
    app.processEvents()
barra = tab.sig_bar.text.text()
print("   barra:", barra)
check("Assinado por: EMPRESA TESTE LTDA — responsável: <b>MARIA DE SOUZA</b>, CPF 123.456.789-09" in barra,
      "faixa do documento mostra quem assinou pela empresa")

print("RESULTADO:", "tudo certo" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
