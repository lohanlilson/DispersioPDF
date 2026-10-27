package io.github.lohanlilson.dispersio

import android.content.Context
import android.graphics.RectF
import android.security.KeyChain
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.PDResources
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.common.PDStream
import com.tom_roush.pdfbox.pdmodel.font.PDFont
import com.tom_roush.pdfbox.pdmodel.font.PDType0Font
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.graphics.form.PDFormXObject
import com.tom_roush.pdfbox.pdmodel.graphics.state.PDExtendedGraphicsState
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAppearanceDictionary
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAppearanceStream
import com.tom_roush.pdfbox.pdmodel.interactive.digitalsignature.PDSignature
import com.tom_roush.pdfbox.pdmodel.interactive.digitalsignature.SignatureInterface
import com.tom_roush.pdfbox.pdmodel.interactive.digitalsignature.SignatureOptions
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDAcroForm
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDSignatureField
import com.tom_roush.pdfbox.util.Matrix
import org.bouncycastle.asn1.ASN1EncodableVector
import org.bouncycastle.asn1.ASN1Primitive
import org.bouncycastle.asn1.DERSet
import org.bouncycastle.asn1.cms.Attribute
import org.bouncycastle.asn1.cms.AttributeTable
import org.bouncycastle.asn1.ess.ESSCertIDv2
import org.bouncycastle.asn1.ess.SigningCertificateV2
import org.bouncycastle.asn1.nist.NISTObjectIdentifiers
import org.bouncycastle.asn1.pkcs.PKCSObjectIdentifiers
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.asn1.x500.style.BCStyle
import org.bouncycastle.asn1.x509.AlgorithmIdentifier
import org.bouncycastle.asn1.x509.GeneralName
import org.bouncycastle.asn1.x509.GeneralNames
import org.bouncycastle.asn1.x509.IssuerSerial
import org.bouncycastle.cert.X509CertificateHolder
import org.bouncycastle.cert.jcajce.JcaCertStore
import org.bouncycastle.cms.CMSProcessableByteArray
import org.bouncycastle.cms.CMSSignedData
import org.bouncycastle.cms.CMSSignedDataGenerator
import org.bouncycastle.cms.DefaultSignedAttributeTableGenerator
import org.bouncycastle.cms.SignerInformation
import org.bouncycastle.cms.SignerInformationStore
import org.bouncycastle.cms.jcajce.JcaSignerInfoGeneratorBuilder
import org.bouncycastle.cms.jcajce.JcaSimpleSignerInfoVerifierBuilder
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.bouncycastle.operator.jcajce.JcaDigestCalculatorProviderBuilder
import org.bouncycastle.tsp.TSPAlgorithms
import org.bouncycastle.tsp.TimeStampRequestGenerator
import org.bouncycastle.tsp.TimeStampResponse
import org.bouncycastle.tsp.TimeStampToken
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.InputStream
import java.math.BigInteger
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/** Certificado pronto para assinar. */
class SigningCert(val key: PrivateKey, val chain: List<X509Certificate>) {
    val cert get() = chain.first()
    val subject: String get() = Certs.cn(cert)
}

data class SignResult(val bytes: ByteArray, val timestamp: Boolean, val problem: String?)

data class SigInfo(
    val field: String, val signer: String, val document: String?, val date: Date?, val tsaDate: Date?,
    val intact: Boolean, val coversWhole: Boolean, val reason: String?, val location: String?,
    val issuer: String, val validUntil: Date?, val error: String?, val revisionEnd: Int = 0,
    val identity: IcpTrust.Identity? = null,
) {
    val ok get() = intact && error == null
    /** assinatura íntegra mas com certificado revogado/vencido */
    val badCert get() = identity?.status == IcpTrust.Status.REVOKED || identity?.status == IcpTrust.Status.EXPIRED
    val untrusted get() = identity == null || identity.status == IcpTrust.Status.UNTRUSTED
}

object Certs {
    val BC = BouncyCastleProvider()
    val TSA = listOf("http://timestamp.digicert.com", "http://timestamp.sectigo.com")

    fun cn(c: X509Certificate): String = runCatching {
        X500Name.getInstance(c.subjectX500Principal.encoded).getRDNs(BCStyle.CN).first().first.value.toString()
    }.getOrDefault(c.subjectX500Principal.name)

    /** ICP-Brasil: "NOME:CPF" -> ("NOME", "CPF"). */
    fun splitName(cn: String): Pair<String, String?> {
        val parts = cn.split(":")
        return if (parts.size == 2 && parts[1].all { it.isDigit() }) parts[0].trim() to parts[1] else cn to null
    }

    fun fromPfx(file: File, password: String): SigningCert {
        val ks = KeyStore.getInstance("PKCS12", BC)
        file.inputStream().use { ks.load(it, password.toCharArray()) }
        val alias = ks.aliases().toList().firstOrNull { ks.isKeyEntry(it) } ?: error("O arquivo não contém chave privada")
        val key = ks.getKey(alias, password.toCharArray()) as PrivateKey
        val chain = ks.getCertificateChain(alias).map { it as X509Certificate }
        return SigningCert(key, chain)
    }

    /** Certificado instalado no Android (escolhido na janela do sistema). Chamar fora da thread principal. */
    fun fromKeyChain(ctx: Context, alias: String): SigningCert {
        val key = KeyChain.getPrivateKey(ctx, alias) ?: error("Sem acesso à chave do certificado")
        val chain = KeyChain.getCertificateChain(ctx, alias)?.toList() ?: error("Certificado não encontrado")
        return SigningCert(key, chain)
    }

    fun storedPfx(ctx: Context): List<File> =
        File(ctx.filesDir, "certificados").listFiles()?.filter { it.isFile }?.sortedByDescending { it.lastModified() } ?: emptyList()
}

/** Assinatura CMS destacada (PAdES), com o atributo signing-certificate-v2 e carimbo de tempo opcional. */
private class CmsSigner(val sc: SigningCert, val tsa: Boolean) : SignatureInterface {
    var stamped = false
    var problem: String? = null

    override fun sign(content: InputStream): ByteArray {
        val cert = sc.cert
        val algo = if (sc.key.algorithm.equals("EC", true)) "SHA256withECDSA" else "SHA256withRSA"
        val signer = JcaContentSignerBuilder(algo).build(sc.key)
        val digests = JcaDigestCalculatorProviderBuilder().setProvider(Certs.BC).build()
        val certHash = MessageDigest.getInstance("SHA-256").digest(cert.encoded)
        val issuer = GeneralNames(GeneralName(X500Name.getInstance(cert.issuerX500Principal.encoded)))
        val ess = ESSCertIDv2(AlgorithmIdentifier(NISTObjectIdentifiers.id_sha256), certHash, IssuerSerial(issuer, cert.serialNumber))
        val attrs = ASN1EncodableVector().apply {
            add(Attribute(PKCSObjectIdentifiers.id_aa_signingCertificateV2, DERSet(SigningCertificateV2(arrayOf(ess)))))
        }
        val info = JcaSignerInfoGeneratorBuilder(digests)
            .setSignedAttributeGenerator(DefaultSignedAttributeTableGenerator(AttributeTable(attrs)))
            .build(signer, cert)
        val gen = CMSSignedDataGenerator()
        gen.addSignerInfoGenerator(info)
        gen.addCertificates(JcaCertStore(sc.chain))
        var signed = gen.generate(CMSProcessableByteArray(content.readBytes()), false)
        if (tsa) {
            for (url in Certs.TSA) {
                try {
                    signed = timestamp(signed, url)
                    stamped = true
                    break
                } catch (e: Exception) {
                    problem = "carimbo de tempo indisponível (${e.message ?: e.javaClass.simpleName})"
                }
            }
            if (stamped) problem = null
        }
        return signed.encoded
    }

    private fun timestamp(signed: CMSSignedData, url: String): CMSSignedData {
        val si = signed.signerInfos.signers.first()
        val digest = MessageDigest.getInstance("SHA-256").digest(si.signature)
        val req = TimeStampRequestGenerator().apply { setCertReq(true) }
            .generate(TSPAlgorithms.SHA256, digest, BigInteger(64, SecureRandom()))
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 15000
            readTimeout = 20000
            setRequestProperty("Content-Type", "application/timestamp-query")
        }
        c.outputStream.use { it.write(req.encoded) }
        val bytes = c.inputStream.use { it.readBytes() }
        val resp = TimeStampResponse(bytes)
        resp.validate(req)
        val token = resp.timeStampToken ?: error("resposta sem carimbo")
        val v = si.unsignedAttributes?.toASN1EncodableVector() ?: ASN1EncodableVector()
        v.add(Attribute(PKCSObjectIdentifiers.id_aa_signatureTimeStampToken, DERSet(ASN1Primitive.fromByteArray(token.encoded))))
        val newSi = SignerInformation.replaceUnsignedAttributes(si, AttributeTable(v))
        return CMSSignedData.replaceSigners(signed, SignerInformationStore(newSi))
    }
}

object PdfSigner {
    private fun font(doc: PDDocument, bold: Boolean): PDFont {
        val names = if (bold) listOf("Roboto-Bold.ttf", "NotoSans-Bold.ttf", "DroidSans-Bold.ttf")
        else listOf("Roboto-Regular.ttf", "NotoSans-Regular.ttf", "DroidSans.ttf")
        for (n in names) {
            val f = File("/system/fonts/$n")
            if (f.exists()) runCatching { return PDType0Font.load(doc, f) }
        }
        return if (bold) PDType1Font.HELVETICA_BOLD else PDType1Font.HELVETICA
    }

    private fun fit(font: PDFont, text: String, maxW: Float, maxH: Float, start: Float, maxLines: Int): Pair<Float, List<String>> {
        var size = start
        while (size > 3.5f) {
            val lines = ArrayList<String>()
            for (para in text.split("\n")) {
                var cur = ""
                for (w in para.split(" ")) {
                    val trial = if (cur.isEmpty()) w else "$cur $w"
                    if (cur.isEmpty() || font.getStringWidth(trial) / 1000 * size <= maxW) cur = trial else { lines += cur; cur = w }
                }
                lines += cur
            }
            if (lines.size <= maxLines && lines.size * size * 1.18f <= maxH &&
                lines.all { font.getStringWidth(it) / 1000 * size <= maxW }) return size to lines
            size -= 0.25f
        }
        return 3.5f to text.split("\n").take(maxLines)
    }

    private val STAMP_BG = floatArrayOf(0.13f, 0.08f, 0.33f)
    private val STAMP_LABEL = floatArrayOf(0.74f, 0.64f, 0.96f)
    private val STAMP_NAME = floatArrayOf(1f, 1f, 1f)
    private val STAMP_TEXT = floatArrayOf(0.85f, 0.83f, 0.95f)
    private val PRISM_FILL = floatArrayOf(0.91f, 0.88f, 0.99f)
    private val RAYS = listOf(floatArrayOf(0.74f, 0.64f, 0.96f), floatArrayOf(0.45f, 0.62f, 0.97f), floatArrayOf(0.97f, 0.76f, 0.42f))
    private val RAY_Y = listOf(floatArrayOf(488f, 492f, 360f, 430f), floatArrayOf(500f, 506f, 490f, 550f), floatArrayOf(512f, 520f, 620f, 690f))

    /** CPF mascarado (LGPD); CNPJ é público e sai completo. Mesma regra do computador (signing.mask_doc_id). */
    fun maskDocId(id: String?): String {
        val d = id.orEmpty().filter { it.isDigit() }
        return when (d.length) {
            11 -> "CPF ***.${d.substring(3, 6)}.${d.substring(6, 9)}-**"
            14 -> "CNPJ ${d.substring(0, 2)}.${d.substring(2, 5)}.${d.substring(5, 8)}/${d.substring(8, 12)}-${d.substring(12)}"
            else -> ""
        }
    }

    private fun roundedTriangle(r: Float): List<Pair<Float, Float>> {
        val corners = listOf(490f to 330f, 640f to 630f, 340f to 630f)
        val pts = ArrayList<Pair<Float, Float>>()
        for (k in 0 until 3) {
            val (x, y) = corners[k]; val a = corners[(k + 2) % 3]; val b = corners[(k + 1) % 3]
            val v1x = a.first - x; val v1y = a.second - y; val v2x = b.first - x; val v2y = b.second - y
            val l1 = Math.hypot(v1x.toDouble(), v1y.toDouble()); val l2 = Math.hypot(v2x.toDouble(), v2y.toDouble())
            val n1x = v1x / l1; val n1y = v1y / l1; val n2x = v2x / l2; val n2y = v2y / l2
            val half = Math.acos((n1x * n2x + n1y * n2y).coerceIn(-1.0, 1.0)) / 2
            val dist = r / Math.tan(half)
            val p1x = x + n1x * dist; val p1y = y + n1y * dist; val p2x = x + n2x * dist; val p2y = y + n2y * dist
            val bx = n1x + n2x; val by = n1y + n2y; val bl = Math.hypot(bx, by)
            val cx = x + bx / bl * r / Math.sin(half); val cy = y + by / bl * r / Math.sin(half)
            val a1 = Math.atan2(p1y - cy, p1x - cx); var a2 = Math.atan2(p2y - cy, p2x - cx)
            while (a2 - a1 > Math.PI) a2 -= 2 * Math.PI
            while (a1 - a2 > Math.PI) a2 += 2 * Math.PI
            for (t in 0..8) {
                val ang = a1 + (a2 - a1) * t / 8
                pts += (cx + r * Math.cos(ang)).toFloat() to (cy + r * Math.sin(ang)).toFloat()
            }
        }
        return pts
    }

    /** Símbolo do Dispersio em vetor (feixe branco, prisma e três raios). (cx, cy) com y para cima. */
    private fun drawPrism(cs: PDPageContentStream, cx: Float, cy: Float, side: Float) {
        val u = side / 1024f
        fun px(x: Float) = cx + (x - 512f) * u
        fun py(y: Float) = cy - (y - 512f) * u
        cs.setStrokingColor(1f, 1f, 1f); cs.setLineWidth(26 * u); cs.setLineCapStyle(1)
        cs.moveTo(px(40f), py(640f)); cs.lineTo(px(400f), py(550f)); cs.stroke()
        for ((i, c) in RAYS.withIndex()) {
            val r = RAY_Y[i]
            cs.setNonStrokingColor(c[0], c[1], c[2])
            cs.moveTo(px(590f), py(r[0])); cs.lineTo(px(990f), py(r[2])); cs.lineTo(px(990f), py(r[3])); cs.lineTo(px(590f), py(r[1]))
            cs.closePath(); cs.fill()
        }
        cs.setNonStrokingColor(PRISM_FILL[0], PRISM_FILL[1], PRISM_FILL[2])
        val pts = roundedTriangle(30f)
        cs.moveTo(px(pts[0].first), py(pts[0].second))
        for (p in pts.drop(1)) cs.lineTo(px(p.first), py(p.second))
        cs.closePath(); cs.fill()
    }

    private fun roundedRect(cs: PDPageContentStream, w: Float, h: Float, r: Float) {
        val k = 0.5523f * r
        cs.moveTo(r, 0f); cs.lineTo(w - r, 0f); cs.curveTo(w - r + k, 0f, w, r - k, w, r)
        cs.lineTo(w, h - r); cs.curveTo(w, h - r + k, w - r + k, h, w - r, h)
        cs.lineTo(r, h); cs.curveTo(r - k, h, 0f, h - r + k, 0f, h - r)
        cs.lineTo(0f, r); cs.curveTo(0f, r - k, r - k, 0f, r, 0f); cs.closePath()
    }

    private class StampLine(val text: String, val kind: Int, var size: Float)  // 0 rótulo, 1 nome, 2 detalhe

    /** Carimbo "cartão escuro" com as cores do ícone — mesmo desenho do computador (signing.stamp_pdf). */
    private fun drawStamp(doc: PDDocument, cs: PDPageContentStream, w: Float, h: Float, cn: String, reason: String, location: String) {
        val bold = font(doc, true)
        val reg = font(doc, false)
        fun width(t: String, b: Boolean, s: Float) = runCatching { (if (b) bold else reg).getStringWidth(t) / 1000f * s }.getOrDefault(t.length * s * 0.6f)
        val (name, docId) = Certs.splitName(cn)
        val now = Calendar.getInstance()
        val details = listOf(maskDocId(docId),
            SimpleDateFormat("dd/MM/yyyy HH:mm:ss XXX", Locale("pt", "BR")).format(now.time),
            listOf(reason.trim(), location.trim()).filter { it.isNotEmpty() }.joinToString(" · ")).filter { it.isNotEmpty() }

        val pad = maxOf(2f, minOf(w, h) * 0.11f)
        val unit = minOf(h, w * 0.42f)
        val side = minOf(unit * 0.9f, w * 0.3f)
        val maxW = w - pad - side * 0.98f
        var size = unit * 0.16f
        while (size > unit * 0.11f && width(name, true, size) > maxW) size -= 0.25f
        var names = listOf(name)
        if (width(name, true, size) > maxW) {
            val words = name.split(" ").filter { it.isNotEmpty() }
            var first = ""
            for (k in 1..words.size) { val t = words.take(k).joinToString(" "); if (width(t, true, size) <= maxW) first = t }
            if (first.isEmpty()) first = words.firstOrNull() ?: name
            names = listOf(first, name.substring(minOf(name.length, first.length)).trim())
        }
        for (t in names) while (size > 3f && width(t, true, size) > maxW) size -= 0.2f
        var label = minOf(unit * 0.089f, size * 0.62f)
        var text = minOf(unit * 0.092f, size * 0.66f)
        for (t in details) while (text > 3f && width(t, false, text) > maxW) text -= 0.2f
        while (label > 3f && width("ASSINADO DIGITALMENTE", true, label) > maxW) label -= 0.2f
        val rows = listOf(StampLine("ASSINADO DIGITALMENTE", 0, label)) + names.map { StampLine(it, 1, size) } + details.map { StampLine(it, 2, text) }
        val gap = floatArrayOf(1.55f, 1.32f, 1.42f)
        val total = rows.sumOf { (it.size * gap[it.kind]).toDouble() }.toFloat()
        val k = if (total > 0) minOf(1f, (h - 2 * pad) / total) else 1f

        cs.setNonStrokingColor(STAMP_BG[0], STAMP_BG[1], STAMP_BG[2])
        roundedRect(cs, w, h, minOf(w, h) * 0.08f); cs.fill()
        drawPrism(cs, w - side * 0.5f - minOf(w, h) * 0.03f, h / 2, side)

        var top = (h - total * k) / 2  // medido de cima, como no computador
        for (r in rows) {
            val sz = r.size * k
            val c = when (r.kind) { 0 -> STAMP_LABEL; 1 -> STAMP_NAME; else -> STAMP_TEXT }
            val f = if (r.kind == 2) reg else bold
            cs.beginText(); cs.setFont(f, sz)
            cs.setNonStrokingColor(c[0], c[1], c[2])
            if (f === bold) {
                // negrito garantido mesmo sem a fonte bold no aparelho: contorno + preenchimento
                cs.setRenderingMode(com.tom_roush.pdfbox.pdmodel.graphics.state.RenderingMode.FILL_STROKE)
                cs.setStrokingColor(c[0], c[1], c[2]); cs.setLineWidth(sz * 0.03f)
            } else cs.setRenderingMode(com.tom_roush.pdfbox.pdmodel.graphics.state.RenderingMode.FILL)
            cs.newLineAtOffset(pad, h - (top + sz * 0.95f)); cs.showText(r.text); cs.endText()
            top += sz * gap[r.kind]
        }
    }

    private data class Sextuple<A, B, C, D, E, F>(val a: A, val b: B, val c: C, val d: D, val e: E, val f: F)

    /** Documento-modelo com o campo e a aparência da assinatura visível (técnica do PDFBox). */
    private fun template(src: PDDocument, pageIndex: Int, rect: PDRectangle, cn: String, reason: String, location: String): InputStream {
        PDDocument().use { doc ->
            val srcPage = src.getPage(pageIndex)
            val page = PDPage(srcPage.mediaBox)
            doc.addPage(page)
            val form = PDAcroForm(doc)
            doc.documentCatalog.acroForm = form
            val field = PDSignatureField(form)
            val widget = field.widgets[0]
            form.isSignaturesExist = true
            form.isAppendOnly = true
            form.cosObject.isDirect = true
            form.fields.add(field)
            widget.rectangle = rect
            val xo = PDFormXObject(PDStream(doc))
            xo.resources = PDResources()
            xo.formType = 1
            xo.bBox = PDRectangle(rect.width, rect.height)
            val ap = PDAppearanceDictionary()
            ap.cosObject.isDirect = true
            val apStream = PDAppearanceStream(xo.cosObject)
            ap.setNormalAppearance(apStream)
            widget.appearance = ap
            PDPageContentStream(doc, apStream).use { cs ->
                // deixa o carimbo "em pé" em páginas giradas
                val rot = ((srcPage.rotation % 360) + 360) % 360
                val w = rect.width; val h = rect.height
                when (rot) {
                    90 -> { cs.transform(Matrix(0f, 1f, -1f, 0f, w, 0f)); drawStamp(doc, cs, h, w, cn, reason, location) }
                    180 -> { cs.transform(Matrix(-1f, 0f, 0f, -1f, w, h)); drawStamp(doc, cs, w, h, cn, reason, location) }
                    270 -> { cs.transform(Matrix(0f, -1f, 1f, 0f, 0f, h)); drawStamp(doc, cs, h, w, cn, reason, location) }
                    else -> drawStamp(doc, cs, w, h, cn, reason, location)
                }
            }
            val out = ByteArrayOutputStream()
            doc.save(out)
            return ByteArrayInputStream(out.toByteArray())
        }
    }

    /**
     * Assina [src] (gravação incremental: assinaturas anteriores continuam válidas).
     * rect = área da assinatura em coordenadas do PDF; fieldName = campo de assinatura vazio já existente.
     */
    fun sign(src: File, password: String?, sc: SigningCert, pageIndex: Int, rect: RectF, fieldName: String?,
             reason: String, location: String, tsa: Boolean): SignResult {
        PDDocument.load(src, password ?: "").use { doc ->
            val sig = PDSignature()
            sig.setFilter(PDSignature.FILTER_ADOBE_PPKLITE)
            sig.setSubFilter(PDSignature.SUBFILTER_ETSI_CADES_DETACHED)
            sig.name = Certs.splitName(sc.subject).first
            if (reason.isNotBlank()) sig.reason = reason
            if (location.isNotBlank()) sig.location = location
            sig.signDate = Calendar.getInstance()
            if (fieldName != null) {
                val f = doc.documentCatalog.acroForm?.getField(fieldName) as? PDSignatureField
                f?.cosObject?.setItem(COSName.V, sig)
            }
            val r = PDRectangle(minOf(rect.left, rect.right), minOf(rect.top, rect.bottom),
                kotlin.math.abs(rect.right - rect.left), kotlin.math.abs(rect.top - rect.bottom))
            val opts = SignatureOptions()
            opts.preferredSignatureSize = SignatureOptions.DEFAULT_SIGNATURE_SIZE * 3
            opts.setVisualSignature(template(doc, pageIndex, r, sc.subject, reason, location))
            opts.page = pageIndex
            val signer = CmsSigner(sc, tsa)
            val out = ByteArrayOutputStream()
            opts.use {
                doc.addSignature(sig, signer, it)
                doc.saveIncremental(out)
            }
            return SignResult(out.toByteArray(), signer.stamped, signer.problem)
        }
    }

    // ------------------------------------------------------------ validação
    /** online = também consultar as listas de revogação (LCR) das ACs. */
    fun validate(bytes: ByteArray, online: Boolean = false): List<SigInfo> {
        val out = ArrayList<SigInfo>()
        PDDocument.load(bytes).use { doc ->
            val names = doc.signatureFields.associate { it.cosObject.getDictionaryObject(COSName.V) to it.fullyQualifiedName }
            for (sig in doc.signatureDictionaries) {
                val field = names[sig.cosObject] ?: ""
                try {
                    val contents = sig.getContents(bytes)
                    val signed = sig.getSignedContent(bytes)
                    val cms = CMSSignedData(CMSProcessableByteArray(signed), contents)
                    val si = cms.signerInfos.signers.first()
                    @Suppress("UNCHECKED_CAST")
                    val holder = (cms.certificates.getMatches(si.sid as org.bouncycastle.util.Selector<X509CertificateHolder>)
                        as Collection<X509CertificateHolder>).first()
                    val cert = org.bouncycastle.cert.jcajce.JcaX509CertificateConverter().setProvider(Certs.BC).getCertificate(holder)
                    val ok = si.verify(JcaSimpleSignerInfoVerifierBuilder().setProvider(Certs.BC).build(holder))
                    val br = sig.byteRange
                    val end = br[2] + br[3]
                    val covers = end >= bytes.size - 2 || bytes.copyOfRange(end, bytes.size).all { it == 0.toByte() || it == '\n'.code.toByte() || it == '\r'.code.toByte() }
                    val tsa = si.unsignedAttributes?.get(PKCSObjectIdentifiers.id_aa_signatureTimeStampToken)?.let {
                        runCatching { TimeStampToken(org.bouncycastle.asn1.cms.ContentInfo.getInstance(it.attrValues.getObjectAt(0))).timeStampInfo.genTime }.getOrNull()
                    }
                    val (name, docId) = Certs.splitName(Certs.cn(cert))
                    val conv = org.bouncycastle.cert.jcajce.JcaX509CertificateConverter().setProvider(Certs.BC)
                    @Suppress("UNCHECKED_CAST")
                    val embedded = (cms.certificates.getMatches(null) as Collection<X509CertificateHolder>)
                        .mapNotNull { h -> runCatching { conv.getCertificate(h) }.getOrNull() }
                    val at = tsa ?: sig.signDate?.time ?: Date()
                    val identity = runCatching { IcpTrust.check(cert, embedded, at, online) }.getOrNull()
                    out += SigInfo(field, name, docId, sig.signDate?.time, tsa, ok, covers, sig.reason, sig.location,
                        runCatching { X500Name.getInstance(cert.issuerX500Principal.encoded).getRDNs(BCStyle.CN).first().first.value.toString() }.getOrDefault(""),
                        cert.notAfter, null, end, identity)
                } catch (e: Exception) {
                    out += SigInfo(field, sig.name ?: "?", null, sig.signDate?.time, null, false, false, sig.reason, sig.location,
                        "", null, e.message ?: e.javaClass.simpleName)
                }
            }
        }
        return out
    }
}
