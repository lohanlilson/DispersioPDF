"""Testa as funções principais sem interface (assinatura com carimbo, OCR opcional, conversões)."""
import datetime
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from lumenpdf import ops, signing

tmp = tempfile.mkdtemp()
doc = pymupdf.open()
for i in range(3):
    p = doc.new_page()
    p.insert_text((72, 100), f"Página {i + 1} contrato CPF 123.456.789-00", fontsize=12)
data = doc.tobytes()

# assinatura digital com carimbo (logo)
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE CI:00000000000")])
c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(1)
     .not_valid_before(datetime.datetime(2025, 1, 1)).not_valid_after(datetime.datetime(2035, 1, 1)).sign(k, hashes.SHA256()))
pfx = os.path.join(tmp, "t.pfx")
open(pfx, "wb").write(pkcs12.serialize_key_and_certificates(b"t", k, c, None, serialization.BestAvailableEncryption(b"1")))
signer = signing.load_pfx(pfx, "1")
out = signing.sign_pdf_bytes(data, signer, 0, (300, 600, 540, 680), 842, "Teste", "Goiânia")
res = signing.validate(out)
assert res and res[0]["intact"] and res[0]["valid"], res
print("assinatura ok")

# conversões e operações
ops.to_docx(data, os.path.join(tmp, "x.docx"))
ops.to_xlsx(pymupdf.open("pdf", data), os.path.join(tmp, "x.xlsx"))
ops.compress(pymupdf.open("pdf", data), "media")
d2 = pymupdf.open("pdf", data)
ops.watermark(d2, "TESTE")
ops.page_numbers(d2)
assert ops.redact_pattern(d2, ops.PATTERNS["CPF"]) == 3
ops.apply_redactions(d2)
ops.encrypted_bytes(d2, "1", "2", ["print"])
print("operações ok")
