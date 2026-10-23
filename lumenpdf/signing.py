"""Assinatura digital com certificado (A1 .pfx/.p12 e A3 via PKCS#11) e validação, usando pyHanko."""
import io
from datetime import datetime


def _box_pdf_coords(page_height, rect):
    """Converte retângulo (x0,y0,x1,y1) com origem no topo (PyMuPDF) para origem na base (PDF)."""
    x0, y0, x1, y1 = rect
    return (x0, page_height - y1, x1, page_height - y0)


def _font(size, bold=False):
    import os
    from PIL import ImageFont
    windir = os.environ.get("WINDIR", r"C:\Windows")
    names = (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"])
    cands = [os.path.join(windir, "Fonts", n) for n in names] + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf"]
    for c in cands:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size)


def _fit_lines(draw, text, font_fn, max_w, max_h, start, bold=False, max_lines=4):
    """Quebra o texto em linhas e reduz a fonte até caber na área."""
    size = start
    while size > 8:
        font = font_fn(size, bold)
        lines = []
        for para in text.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = (cur + " " + word).strip()
                if draw.textlength(trial, font=font) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        lh = int(size * 1.22)
        if len(lines) <= max_lines and lh * len(lines) <= max_h and all(draw.textlength(l, font=font) <= max_w for l in lines):
            return font, lines, lh
        size -= 2
    font = font_fn(8, bold)
    return font, text.split("\n")[:max_lines], 10


def stamp_image(signer_name, box_w, box_h, reason="", location="", when=None, scale=4):
    """Desenha a aparência da assinatura (como Acrobat/Foxit): logo do programa esmaecido ao fundo, nome do
    signatário em destaque à esquerda e os detalhes à direita."""
    from PIL import Image, ImageDraw
    from . import resource
    when = when or datetime.now().astimezone()
    W, H = max(int(box_w * scale), 40), max(int(box_h * scale), 20)
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    try:
        logo = Image.open(resource("assets", "logo.png")).convert("RGBA")
        side = int(min(W, H) * 0.95)
        logo = logo.resize((side, side), Image.LANCZOS)
        alpha = logo.getchannel("A").point(lambda a: int(a * 0.22))
        logo.putalpha(alpha)
        img.alpha_composite(logo, ((W - side) // 2, (H - side) // 2))
    except Exception:
        pass
    d = ImageDraw.Draw(img)
    pad = int(3 * scale)
    name = signer_name.split(":")[0].strip() if ":" in signer_name and signer_name.split(":")[-1].strip().isdigit() else signer_name
    tz = when.strftime("%z")
    details = (f"Assinado de forma digital por {signer_name}\n"
               f"Data: {when:%d/%m/%Y %H:%M:%S} {tz[:3]}'{tz[3:]}'")
    if reason:
        details += f"\nMotivo: {reason}"
    if location:
        details += f"\nLocal: {location}"
    split = int(W * 0.46)
    nf, nlines, nlh = _fit_lines(d, name, _font, split - 2 * pad, H - 2 * pad, int(H * 0.30), bold=True, max_lines=3)
    y = (H - nlh * len(nlines)) // 2
    for l in nlines:
        d.text((pad, y), l, font=nf, fill=(20, 20, 20, 255))
        y += nlh
    df, dlines, dlh = _fit_lines(d, details, _font, W - split - 2 * pad, H - 2 * pad, int(H * 0.16), max_lines=8)
    y = (H - dlh * len(dlines)) // 2
    for l in dlines:
        d.text((split + pad, y), l, font=df, fill=(20, 20, 20, 255))
        y += dlh
    return img


def _stamp(signer_name, box_w, box_h, reason="", location=""):
    from pyhanko import stamp
    from pyhanko.pdf_utils import images, layout
    img = stamp_image(signer_name, box_w, box_h, reason, location)
    return stamp.TextStampStyle(
        stamp_text="",
        border_width=0,
        background=images.PdfImage(img),
        background_opacity=1.0,
        background_layout=layout.SimpleBoxLayoutRule(
            x_align=layout.AxisAlignment.ALIGN_MID, y_align=layout.AxisAlignment.ALIGN_MID,
            margins=layout.Margins(0, 0, 0, 0), inner_content_scaling=layout.InnerScaling.STRETCH_FILL),
    )


def sign_pdf_bytes(pdf_bytes, signer, page_index, unrot_rect, page_height, reason="", location="",
                   field_name=None, visible=True):
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.fields import SigFieldSpec, append_signature_field

    w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
    field_name = field_name or f"Assinatura_{datetime.now():%Y%m%d%H%M%S%f}"
    if visible:
        append_signature_field(w, SigFieldSpec(sig_field_name=field_name, on_page=page_index,
                                               box=_box_pdf_coords(page_height, unrot_rect)))
    else:
        append_signature_field(w, SigFieldSpec(sig_field_name=field_name))
    meta = signers.PdfSignatureMetadata(field_name=field_name, reason=reason or None,
                                        location=location or None, md_algorithm="sha256")
    x0, y0, x1, y1 = unrot_rect
    pdf_signer = signers.PdfSigner(meta, signer=signer,
                                   stamp_style=_stamp(cert_subject(signer), abs(x1 - x0), abs(y1 - y0), reason, location))
    out = io.BytesIO()
    pdf_signer.sign_pdf(w, output=out)
    return out.getvalue()


def load_pfx(path, password):
    from pyhanko.sign import signers
    signer = signers.SimpleSigner.load_pkcs12(pfx_file=path, passphrase=(password or "").encode() or None)
    if signer is None:
        raise ValueError("Não foi possível abrir o certificado. Verifique a senha.")
    return signer


def load_pkcs11(lib_path, pin, label=None):
    """Certificado A3 (token/cartão). lib_path ex.: C:\\Windows\\System32\\eTPKCS11.dll (SafeNet)."""
    try:
        from pyhanko.sign import pkcs11
    except ImportError:
        raise RuntimeError("Suporte a token A3 não instalado. Rode: python -m pip install python-pkcs11 "
                           "(no Windows exige o Microsoft C++ Build Tools ou uma versão do Python com pacote pronto).")
    session = pkcs11.open_pkcs11_session(lib_path, user_pin=pin)
    return pkcs11.PKCS11Signer(session, cert_label=label, key_label=label)


def _cn(cert):
    try:
        nat = cert.subject.native
        return nat.get("common_name") or cert.subject.human_friendly
    except Exception:
        return "?"


def cert_subject(signer):
    return _cn(signer.signing_cert)


_VC_CERTS = None


def _validation_context():
    """Contexto de validação com as raízes confiáveis do Windows (inclui ICP-Brasil quando instaladas)."""
    global _VC_CERTS
    from pyhanko_certvalidator import ValidationContext
    if _VC_CERTS is not None:
        roots, others = _VC_CERTS
        kw = dict(allow_fetching=False, revocation_mode="soft-fail")
        if roots:
            kw.update(trust_roots=roots, other_certs=others)
        return ValidationContext(**kw)
    roots, others = [], []
    try:
        from . import wincert
        if wincert.IS_WINDOWS:
            from asn1crypto import x509 as ax
            crypt32, _ = wincert._libs()
            for store, bucket in (("Root", roots), ("CA", others)):
                for der, _ in wincert._store_certs(crypt32, store):
                    try:
                        bucket.append(ax.Certificate.load(der))
                    except Exception:
                        pass
    except Exception:
        roots, others = [], []
    _VC_CERTS = (roots, others)
    kw = dict(allow_fetching=False, revocation_mode="soft-fail")
    if roots:
        kw.update(trust_roots=roots, other_certs=others)
    return ValidationContext(**kw)


def _cert_info(cert):
    try:
        subj = cert.subject.native
        iss = cert.issuer.native
        validity = cert["tbs_certificate"]["validity"]
        cn = subj.get("common_name", "")
        doc = cn.split(":")[-1] if ":" in cn and cn.split(":")[-1].strip().isdigit() else ""
        return {"nome": cn.split(":")[0] if doc else cn, "documento": doc,
                "organizacao": subj.get("organization_name", ""), "email": subj.get("email_address", ""),
                "emissor": iss.get("common_name", cert.issuer.human_friendly),
                "emissor_org": iss.get("organization_name", ""),
                "serie": format(cert.serial_number, "X"),
                "valido_de": validity["not_before"].native, "valido_ate": validity["not_after"].native,
                "assunto": cert.subject.human_friendly, "algoritmo": cert.signature_algo}
    except Exception:
        return {}


def validate(pdf_bytes, field=None):
    """Valida as assinaturas (ou só a do campo informado). Retorna dados completos de cada uma."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    import logging
    logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)
    try:
        vc = _validation_context()
    except Exception:
        vc = None
    results = []
    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    sigs = reader.embedded_signatures
    for idx, sig in enumerate(sigs):
        if field and sig.field_name != field:
            continue
        info = dict(field=sig.field_name, index=idx + 1, total=len(sigs), signer="?", time=None, intact=False,
                    valid=False, covers_all=False, trusted=False, error=None, modification=None,
                    reason="", location="", contact="", cert={}, chain=[], revision_end=None,
                    later_changes=False)
        try:
            so = sig.sig_object
            info["reason"] = str(so.get("/Reason", "") or "")
            info["location"] = str(so.get("/Location", "") or "")
            info["contact"] = str(so.get("/ContactInfo", "") or "")
            br = [int(x) for x in so["/ByteRange"]]
            info["revision_end"] = br[2] + br[3]
            info["later_changes"] = info["revision_end"] < len(pdf_bytes.rstrip(b"\r\n\x00 "))
        except Exception:
            pass
        info["signer"] = _cn(sig.signer_cert)
        info["cert"] = _cert_info(sig.signer_cert)
        try:
            st = validate_pdf_signature(sig, signer_validation_context=vc) if vc else validate_pdf_signature(sig)
            info.update(intact=st.intact, valid=st.valid, trusted=st.trusted, time=st.signer_reported_dt)
            try:
                info["covers_all"] = st.coverage.name == "ENTIRE_FILE"
                info["modification"] = st.modification_level.name if st.modification_level else None
            except Exception:
                pass
            try:
                path = st.validation_path
                if path is not None:
                    info["chain"] = [_cn(c) for c in path.iter_certs(include_root=True)]
            except Exception:
                pass
        except Exception as e:
            info["error"] = str(e)
        results.append(info)
    return results


def signed_revision(pdf_bytes, info):
    """Bytes do documento exatamente como estava quando esta assinatura foi aplicada."""
    end = info.get("revision_end")
    return pdf_bytes[:end] if end else None


def status_of(info):
    """(nível, título) — nível: ok | warn | bad."""
    if info.get("error") and not info.get("intact"):
        return "bad", "Assinatura inválida"
    if not info.get("intact") or not info.get("valid"):
        return "bad", "Assinatura INVÁLIDA — o documento foi alterado ou a assinatura está corrompida"
    if info.get("modification") not in (None, "NONE", "LTA_UPDATES", "FORM_FILLING"):
        return "warn", "Assinatura válida, mas o documento recebeu alterações depois de assinado"
    if not info.get("trusted"):
        return "warn", "Assinatura íntegra — identidade do signatário não verificada (certificado raiz não confiável neste computador)"
    return "ok", "Assinatura válida"
