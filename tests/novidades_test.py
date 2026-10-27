"""Comparação de documentos, alterações após assinatura e detecção automática de campos."""
import datetime, os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
QMessageBox.information = staticmethod(lambda *a, **k: None)
from dispersio import ops, signing
from dispersio.compare import CompareWindow, report_html

tmp = tempfile.mkdtemp()


def signer(cn):
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(1)
         .not_valid_before(datetime.datetime(2025, 1, 1)).not_valid_after(datetime.datetime(2035, 1, 1)).sign(k, hashes.SHA256()))
    p = os.path.join(tmp, cn + ".pfx")
    open(p, "wb").write(pkcs12.serialize_key_and_certificates(b"t", k, c, None, serialization.BestAvailableEncryption(b"1")))
    return signing.load_pfx(p, "1")


def doc(texts):
    d = pymupdf.open()
    for t in texts:
        d.new_page().insert_textbox(pymupdf.Rect(60, 60, 540, 780), t, fontsize=11)
    return d


# 1) comparação: alteração, inserção e remoção, inclusive em outra página
a = doc(["O preço é R$ 10.000,00 pagos à vista.", "Prazo de 30 dias. Foro de Goiânia."])
b = doc(["O preço é R$ 12.500,00 pagos em duas parcelas à vista.", "Prazo de 30 dias."])
r = ops.compare_docs(a, b)
kinds = sorted(c["kind"] for c in r["changes"])
assert kinds == ["alterado", "inserido", "removido"], [(c["kind"], c["text_a"], c["text_b"]) for c in r["changes"]]
assert "12.500,00" in report_html(r, "a", "b")
w = CompareWindow(None, a, "a.pdf", b, "b.pdf")
w.step(1)
assert w.cur >= 0 and w.views[0].marks and w.views[1].marks
w.close()
print("comparação ok")

# 2) o que mudou depois da assinatura (o carimbo de assinaturas posteriores não conta como texto)
base = doc(["CONTRATO. Valor R$ 10.000,00."]).tobytes()
s1 = signing.sign_pdf_bytes(base, signer("FULANO"), 0, (300, 600, 540, 670), 842)
f = os.path.join(tmp, "x.pdf")
open(f, "wb").write(s1)
d = pymupdf.open(f)
d[0].insert_text((60, 300), "Cláusula nova depois da assinatura.", fontsize=11)
d.saveIncr()
d.close()
s2 = signing.sign_pdf_bytes(open(f, "rb").read(), signer("BELTRANO"), 0, (50, 600, 290, 670), 842)
res = signing.validate(s2)
first = [x for x in res if x["signer"].startswith("FULANO")][0]
assert first["later_changes"]
r = ops.compare_docs(pymupdf.open("pdf", signing.signed_revision(s2, first)), pymupdf.open("pdf", s2))
assert [c["text_b"] for c in r["changes"]] == ["Cláusula nova depois da assinatura."], r["changes"]
print("alterações após assinatura ok")

# 3) detecção de campos: sublinhado, pontilhado, ( ), caixa, linha de assinatura; ignora tabela preenchida
d = pymupdf.open()
p = d.new_page()
p.insert_text((60, 110), "Nome completo: ________________________________", fontsize=11)
p.insert_text((60, 140), "CPF: ............................", fontsize=11)
p.insert_text((60, 170), "Aceita?  ( ) Sim   ( ) Não", fontsize=11)
p.insert_text((60, 270), "Observações:", fontsize=11)
p.draw_rect(pymupdf.Rect(60, 278, 540, 330))
for i, row in enumerate([("Banco", "Agência"), ("Bradesco", "1234")]):
    for j, c in enumerate(row):
        rr = pymupdf.Rect(60 + j * 150, 380 + i * 20, 210 + j * 150, 400 + i * 20)
        p.draw_rect(rr)
        p.insert_text((rr.x0 + 4, rr.y1 - 6), c, fontsize=10)
p.draw_line((70, 520), (260, 520))
p.insert_text((100, 534), "Assinatura do Cedente", fontsize=10)
n = ops.create_detected_fields(d)
assert n == {"text": 3, "check": 2, "signature": 1}, n
names = {w.field_name for w in d[0].widgets()}
assert {"Nome completo", "CPF", "Sim", "Não", "Observações", "Assinatura do Cedente"} <= names, names
assert ops.create_detected_fields(d) == {"text": 0, "check": 0, "signature": 0}  # não duplica
# assina no campo detectado
data = d.tobytes()
pg = pymupdf.open("pdf", data)[0]
sw = [x for x in pg.widgets(types=[pymupdf.PDF_WIDGET_TYPE_SIGNATURE])][0]
out = signing.sign_pdf_bytes(data, signer("CEDENTE"), 0, tuple(sw.rect), pg.mediabox.height,
                             field_name=sw.field_name, existing_field=True)
v = signing.validate(out)
assert len(v) == 1 and v[0]["intact"] and v[0]["valid"] and v[0]["field"] == "Assinatura do Cedente", v
assert ops.has_empty_signature_fields(pymupdf.open("pdf", data)) and not ops.has_empty_signature_fields(pymupdf.open("pdf", out))
print("detecção de campos ok")
