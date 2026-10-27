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

    /** Desenha o carimbo (como no Dispersio do computador): símbolo esmaecido, nome à esquerda, detalhes à direita. */
    private fun drawStamp(doc: PDDocument, cs: PDPageContentStream, w: Float, h: Float, cn: String, reason: String, location: String) {
        // símbolo do prisma, em vetor e esmaecido
        val gs = PDExtendedGraphicsState().apply { nonStrokingAlphaConstant = 0.22f; strokingAlphaConstant = 0.22f }
        cs.saveGraphicsState()
        cs.setGraphicsStateParameters(gs)
        val side = minOf(w, h) * 1.1f
        val u = side / 1024f
        val ox = w / 2 - 512 * u
        val oy = h / 2 - 512 * u
        fun px(x: Float) = ox + x * u
        fun py(y: Float) = oy + (1024 - y) * u
        cs.setStrokingColor(0.43f, 0.24f, 0.94f)
        cs.setLineWidth(30 * u)
        cs.setLineCapStyle(1)
        cs.moveTo(px(60f), py(660f)); cs.lineTo(px(430f), py(560f)); cs.stroke()
        val apex = px(600f) to py(520f)
        listOf(Triple(380f, floatArrayOf(0.67f, 0.55f, 1f), 0), Triple(520f, floatArrayOf(0.43f, 0.24f, 0.94f), 1),
            Triple(660f, floatArrayOf(1f, 0.69f, 0.27f), 2)).forEach { (ey, c, _) ->
            val ex = px(980f); val eyy = py(ey)
            val ang = Math.atan2((eyy - apex.second).toDouble(), (ex - apex.first).toDouble()) + Math.PI / 2
            val dx = (Math.cos(ang) * 40 * u).toFloat(); val dy = (Math.sin(ang) * 40 * u).toFloat()
            cs.setNonStrokingColor(c[0], c[1], c[2])
            cs.moveTo(apex.first, apex.second); cs.lineTo(ex - dx, eyy - dy); cs.lineTo(ex + dx, eyy + dy); cs.closePath(); cs.fill()
        }
        cs.setNonStrokingColor(0.36f, 0.18f, 0.82f)
        cs.moveTo(px(500f), py(250f)); cs.lineTo(px(730f), py(690f)); cs.lineTo(px(270f), py(690f)); cs.closePath(); cs.fill()
        cs.restoreGraphicsState()

        val (name, _) = Certs.splitName(cn)
        val now = Calendar.getInstance()
        val tz = SimpleDateFormat("Z", Locale.US).format(now.time)
        var details = "Assinado de forma digital por $cn\nData: " +
            SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale("pt", "BR")).format(now.time) + " ${tz.take(3)}'${tz.drop(3)}'"
        if (reason.isNotBlank()) details += "\nMotivo: $reason"
        if (location.isNotBlank()) details += "\nLocal: $location"
        val pad = minOf(3f, h * 0.06f)
        val split = w * 0.46f
        val bold = font(doc, true)
        val reg = font(doc, false)
        cs.setNonStrokingColor(0.08f, 0.08f, 0.10f)
        for ((f, text, x, mw, start, maxL) in listOf(
            Sextuple(bold, name, pad, split - 2 * pad, h * 0.30f, 3),
            Sextuple(reg, details, split + pad, w - split - 2 * pad, h * 0.16f, 8))) {
            val (size, lines) = fit(f, text, mw, h - 2 * pad, start, maxL)
            val lh = size * 1.18f
            var y = h - (h - lh * lines.size) / 2 - size * 0.92f
            for (l in lines) {
                cs.beginText(); cs.setFont(f, size)
                if (f === bold) {
                    // negrito garantido mesmo sem a fonte bold no aparelho: contorno + preenchimento
                    cs.setRenderingMode(com.tom_roush.pdfbox.pdmodel.graphics.state.RenderingMode.FILL_STROKE)
                    cs.setStrokingColor(0.08f, 0.08f, 0.10f)
                    cs.setLineWidth(size * 0.045f)
                } else cs.setRenderingMode(com.tom_roush.pdfbox.pdmodel.graphics.state.RenderingMode.FILL)
                cs.newLineAtOffset(x, y); cs.showText(l); cs.endText()
                y -= lh
            }
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
