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


def _font_file(bold=False):
    import os
    windir = os.environ.get("WINDIR", r"C:\Windows")
    names = (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"])
    cands = [os.path.join(windir, "Fonts", n) for n in names] + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf"]
    return next((c for c in cands if os.path.exists(c)), None)


def _wrap(font, text, size, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if font.text_length(trial, size) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _fit(font, text, max_w, max_h, start, max_lines, lh=1.18):
    size = start
    while size > 4:
        lines = _wrap(font, text, size, max_w)
        if len(lines) <= max_lines and size * lh * len(lines) <= max_h and \
                all(font.text_length(l, size) <= max_w for l in lines):
            return size, lines
        size -= 0.25
    return 4, _wrap(font, text, 4, max_w)[:max_lines]


def _prism_vector(page, cx, cy, side, opacity=0.24):
    """Símbolo do Lumen (feixe + prisma + leque de luz) em vetor — nítido em qualquer zoom e na impressão."""
    import math
    import pymupdf
    u = side / 1024
    ox, oy = cx - 512 * u, cy - 512 * u
    P = lambda x, y: pymupdf.Point(ox + x * u, oy + y * u)  # noqa: E731
    violet, light, mid, gold = (0.43, 0.24, 0.94), (0.67, 0.55, 1.0), (0.43, 0.24, 0.94), (1.0, 0.69, 0.27)
    page.draw_line(P(60, 660), P(430, 560), color=violet, width=30 * u, lineCap=1, stroke_opacity=opacity)
    apex = P(600, 520)
    for (ex, ey), c in zip([(980, 380), (980, 520), (980, 660)], [light, mid, gold]):
        e = P(ex, ey)
        ang = math.atan2(e.y - apex.y, e.x - apex.x) + math.pi / 2
        dx, dy = math.cos(ang) * 40 * u, math.sin(ang) * 40 * u
        page.draw_polyline([apex, pymupdf.Point(e.x - dx, e.y - dy), pymupdf.Point(e.x + dx, e.y + dy)],
                           color=None, fill=c, closePath=True, fill_opacity=opacity)
    # prisma com cantos arredondados (polígono único, sem sobreposição de traço e preenchimento)
    corners, r = [(500, 250), (730, 690), (270, 690)], 34
    pts = []
    for k, (x, y) in enumerate(corners):
        a, b = corners[k - 1], corners[(k + 1) % 3]
        v1 = (a[0] - x, a[1] - y); v2 = (b[0] - x, b[1] - y)
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        n1 = (v1[0] / l1, v1[1] / l1); n2 = (v2[0] / l2, v2[1] / l2)
        half = math.acos(max(-1, min(1, n1[0] * n2[0] + n1[1] * n2[1]))) / 2
        dist = r / math.tan(half)
        p1 = (x + n1[0] * dist, y + n1[1] * dist); p2 = (x + n2[0] * dist, y + n2[1] * dist)
        bis = (n1[0] + n2[0], n1[1] + n2[1]); bl = math.hypot(*bis)
        c = (x + bis[0] / bl * r / math.sin(half), y + bis[1] / bl * r / math.sin(half))
        a1, a2 = math.atan2(p1[1] - c[1], p1[0] - c[0]), math.atan2(p2[1] - c[1], p2[0] - c[0])
        while a2 - a1 > math.pi: a2 -= 2 * math.pi  # noqa: E701
        while a1 - a2 > math.pi: a2 += 2 * math.pi  # noqa: E701
        for t in range(9):
            ang = a1 + (a2 - a1) * t / 8
            pts.append(P(c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)))
    page.draw_polyline(pts, color=None, fill=(0.36, 0.18, 0.82), closePath=True, fill_opacity=opacity)


def stamp_pdf(signer_name, box_w, box_h, reason="", location="", when=None):
    """Aparência da assinatura em vetor (como Acrobat/Foxit): símbolo do programa esmaecido ao fundo, nome do
    signatário em destaque à esquerda e detalhes à direita. Texto real com fonte embutida (nítido e pesquisável)."""
    import pymupdf
    when = when or datetime.now().astimezone()
    W, H = max(box_w, 20), max(box_h, 10)
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _prism_vector(page, W / 2, H / 2, min(W, H) * 1.15)
    name = signer_name.split(":")[0].strip() if ":" in signer_name and signer_name.split(":")[-1].strip().isdigit() \
        else signer_name
    tz = when.strftime("%z")
    details = (f"Assinado de forma digital por {signer_name}\n"
               f"Data: {when:%d/%m/%Y %H:%M:%S} {tz[:3]}'{tz[3:]}'")
    if reason:
        details += f"\nMotivo: {reason}"
    if location:
        details += f"\nLocal: {location}"
    fb, fr = _font_file(True), _font_file(False)
    fbold = pymupdf.Font(fontfile=fb) if fb else pymupdf.Font("hebo")
    freg = pymupdf.Font(fontfile=fr) if fr else pymupdf.Font("helv")
    page.insert_font(fontname="LB", fontfile=fb) if fb else page.insert_font(fontname="LB", fontbuffer=fbold.buffer)
    page.insert_font(fontname="LR", fontfile=fr) if fr else page.insert_font(fontname="LR", fontbuffer=freg.buffer)
    pad = min(3.0, H * 0.06)
    split = W * 0.46
    ink = (0.08, 0.08, 0.10)
    for font, fname, text, x, w, start, maxl in (
            (fbold, "LB", name, pad, split - 2 * pad, H * 0.30, 3),
            (freg, "LR", details, split + pad, W - split - 2 * pad, H * 0.16, 8)):
        size, lines = _fit(font, text, w, H - 2 * pad, start, maxl)
        lh = size * 1.18
        asc = font.ascender * size
        y = (H - lh * len(lines)) / 2 + asc
        for l in lines:
            page.insert_text((x, y), l, fontname=fname, fontsize=size, color=ink)
            y += lh
    doc.subset_fonts()
    return doc.tobytes(garbage=3, deflate=True)


def _stamp(signer_name, box_w, box_h, reason="", location=""):
    import os
    import tempfile
    from pyhanko import stamp
    from pyhanko.pdf_utils import content, layout
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="lumen-carimbo-")
    with os.fdopen(fd, "wb") as f:
        f.write(stamp_pdf(signer_name, box_w, box_h, reason, location))
    return stamp.TextStampStyle(
        stamp_text="",
        border_width=0,
        background=content.ImportedPdfPage(path),
        background_opacity=1.0,
        background_layout=layout.SimpleBoxLayoutRule(
            x_align=layout.AxisAlignment.ALIGN_MID, y_align=layout.AxisAlignment.ALIGN_MID,
            margins=layout.Margins(0, 0, 0, 0), inner_content_scaling=layout.InnerScaling.STRETCH_FILL),
    )


TSA_SERVERS = {
    "DigiCert (gratuito)": "http://timestamp.digicert.com",
    "Sectigo (gratuito)": "http://timestamp.sectigo.com",
    "GlobalSign (gratuito)": "http://timestamp.globalsign.com/tsa/r6advanced1",
    "FreeTSA (gratuito)": "https://freetsa.org/tsr",
}
DEFAULT_TSA = TSA_SERVERS["DigiCert (gratuito)"]


def _ltv_context(signer):
    """Contexto para embutir dados de validação (cadeia + OCSP/CRL) — busca online as revogações."""
    from pyhanko_certvalidator import ValidationContext
    _validation_context()  # carrega raízes do Windows em cache
    roots, others = _VC_CERTS or ([], [])
    roots, others = list(roots), list(others)
    chain = [signer.signing_cert] + list(getattr(signer, "cert_registry", None) or [])
    for c in chain:
        if c.self_signed != "no" and c not in roots:
            roots.append(c)
        elif c not in others:
            others.append(c)
    return ValidationContext(trust_roots=roots or None, other_certs=others, allow_fetching=True,
                             revocation_mode="soft-fail")


def sign_pdf_bytes(pdf_bytes, signer, page_index, unrot_rect, page_height, reason="", location="",
                   field_name=None, visible=True, tsa_url=None, ltv=False, report=None):
    """Assina em PAdES. Com tsa_url aplica carimbo de tempo; com ltv embute os dados de validação de longo prazo.
    Se a internet/servidor falhar, assina com o que for possível e descreve o resultado em report."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers, timestamps
    from pyhanko.sign.fields import SigFieldSpec, append_signature_field, SigSeedSubFilter

    report = report if report is not None else {}
    field_name = field_name or f"Assinatura_{datetime.now():%Y%m%d%H%M%S%f}"
    x0, y0, x1, y1 = unrot_rect
    style = _stamp(cert_subject(signer), abs(x1 - x0), abs(y1 - y0), reason, location)

    def attempt(use_tsa, use_ltv):
        w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
        if visible:
            append_signature_field(w, SigFieldSpec(sig_field_name=field_name, on_page=page_index,
                                                   box=_box_pdf_coords(page_height, unrot_rect)))
        else:
            append_signature_field(w, SigFieldSpec(sig_field_name=field_name))
        extra = {}
        if use_ltv:
            extra = dict(embed_validation_info=True, validation_context=_ltv_context(signer))
        meta = signers.PdfSignatureMetadata(field_name=field_name, reason=reason or None,
                                            location=location or None, md_algorithm="sha256",
                                            subfilter=SigSeedSubFilter.PADES, **extra)
        tsa = timestamps.HTTPTimeStamper(use_tsa, timeout=20) if use_tsa else None
        out = io.BytesIO()
        signers.PdfSigner(meta, signer=signer, timestamper=tsa, stamp_style=style).sign_pdf(w, output=out)
        return out.getvalue()

    plans = []
    if tsa_url and ltv:
        plans.append((tsa_url, True))
    if tsa_url:
        plans.append((tsa_url, False))
    if ltv and not tsa_url:
        plans.append((None, True))
    plans.append((None, False))
    errors_ = []
    for use_tsa, use_ltv in plans:
        try:
            data = attempt(use_tsa, use_ltv)
            report.update(tsa=bool(use_tsa), ltv=use_ltv, tsa_url=use_tsa or "", problems=errors_)
            return data
        except Exception as e:
            what = ("carimbo de tempo + LTV" if use_tsa and use_ltv else "carimbo de tempo" if use_tsa
                    else "dados de validação (LTV)" if use_ltv else "assinatura")
            errors_.append(f"{what}: {e}")
            if (use_tsa, use_ltv) == plans[-1]:
                raise


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


def _certifi_roots():
    """Raízes públicas (Mozilla/certifi) — usadas junto com as do Windows; garantem as das TSAs."""
    try:
        import certifi
        from asn1crypto import pem, x509 as ax
        data = open(certifi.where(), "rb").read()
        return [ax.Certificate.load(der) for _, _, der in pem.unarmor(data, multiple=True)]
    except Exception:
        return []


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
    roots += _certifi_roots()
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
        info = dict(tsa_time=None, tsa_valid=False, tsa_trusted=False,
                    ltv=b"/DSS" in pdf_bytes, field=sig.field_name, index=idx + 1, total=len(sigs), signer="?", time=None, intact=False,
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
                tv = st.timestamp_validity
                if tv is not None:
                    info["tsa_time"] = tv.timestamp
                    info["tsa_valid"] = bool(tv.intact and tv.valid)
                    info["tsa_trusted"] = bool(tv.trusted)
            except Exception:
                pass
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
