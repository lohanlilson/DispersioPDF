package io.github.lohanlilson.lumenpdf

import android.content.Context
import org.bouncycastle.asn1.ASN1OctetString
import org.bouncycastle.asn1.ASN1Primitive
import org.bouncycastle.asn1.x509.AccessDescription
import org.bouncycastle.asn1.x509.AuthorityInformationAccess
import org.bouncycastle.asn1.x509.CRLDistPoint
import org.bouncycastle.asn1.x509.DistributionPointName
import org.bouncycastle.asn1.x509.Extension
import org.bouncycastle.asn1.x509.GeneralName
import org.bouncycastle.asn1.x509.GeneralNames
import java.io.ByteArrayInputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509CRL
import java.security.cert.X509Certificate
import java.util.Date

/**
 * Confere a identidade de quem assinou: cadeia até uma AC Raiz da ICP-Brasil (certificados públicos do ITI,
 * embutidos no app) e, com internet, a lista de certificados revogados (LCR) de cada AC.
 */
object IcpTrust {
    enum class Status { TRUSTED, NO_REVOCATION_CHECK, REVOKED, EXPIRED, UNTRUSTED }

    data class Identity(val status: Status, val detail: String, val chain: List<String>, val revokedAt: Date? = null)

    private val cf: CertificateFactory = CertificateFactory.getInstance("X.509")
    private var roots: List<X509Certificate> = emptyList()
    private var acs: List<X509Certificate> = emptyList()
    private var cacheDir: File? = null
    private var loaded = false

    /** usado nos testes: raízes e LCRs adicionais / simuladas */
    var extraRoots: List<X509Certificate> = emptyList()
    var crlFetcher: ((String) -> ByteArray?)? = null

    @Synchronized
    fun init(ctx: Context) {
        if (loaded) return
        roots = ctx.assets.open("icp/raizes.pem").use { s -> cf.generateCertificates(s).map { it as X509Certificate } }
        acs = ctx.assets.open("icp/acs.pem").use { s -> cf.generateCertificates(s).map { it as X509Certificate } }
        cacheDir = File(ctx.cacheDir, "lcr").apply { mkdirs() }
        loaded = true
    }

    val rootCount get() = roots.size
    val acCount get() = acs.size

    private fun signedBy(c: X509Certificate, issuer: X509Certificate) =
        c.issuerX500Principal == issuer.subjectX500Principal && runCatching { c.verify(issuer.publicKey); true }.getOrDefault(false)

    private fun isCa(c: X509Certificate) = c.basicConstraints >= 0

    private fun allRoots() = roots + extraRoots

    /** Monta a cadeia do certificado até uma raiz confiável. Devolve null se não chegar a nenhuma. */
    fun buildChain(cert: X509Certificate, embedded: Collection<X509Certificate>, online: Boolean): List<X509Certificate>? {
        val chain = mutableListOf(cert)
        var cur = cert
        repeat(10) {
            allRoots().firstOrNull { signedBy(cur, it) }?.let { r ->
                if (r != cur) chain += r
                return chain
            }
            val next = (embedded.asSequence() + acs.asSequence()).firstOrNull { it != cur && isCa(it) && signedBy(cur, it) }
                ?: (if (online) aiaIssuer(cur)?.takeIf { isCa(it) && signedBy(cur, it) } else null)
                ?: return null
            if (next in chain) return null
            chain += next
            cur = next
        }
        return null
    }

    private fun ext(c: X509Certificate, oid: String): ASN1Primitive? = c.getExtensionValue(oid)?.let {
        ASN1Primitive.fromByteArray(ASN1OctetString.getInstance(it).octets)
    }

    private fun uris(names: GeneralNames?): List<String> = names?.names
        ?.filter { it.tagNo == GeneralName.uniformResourceIdentifier }
        ?.map { it.name.toString() }
        ?.filter { it.startsWith("http", true) } ?: emptyList()

    fun crlUrls(c: X509Certificate): List<String> = runCatching {
        val dp = CRLDistPoint.getInstance(ext(c, Extension.cRLDistributionPoints.id) ?: return emptyList())
        dp.distributionPoints.flatMap { p ->
            val n = p.distributionPoint
            if (n != null && n.type == DistributionPointName.FULL_NAME) uris(GeneralNames.getInstance(n.name)) else emptyList()
        }
    }.getOrDefault(emptyList())

    private fun aiaIssuer(c: X509Certificate): X509Certificate? = runCatching {
        val aia = AuthorityInformationAccess.getInstance(ext(c, Extension.authorityInfoAccess.id) ?: return null)
        aia.accessDescriptions.filter { it.accessMethod == AccessDescription.id_ad_caIssuers }
            .flatMap { uris(GeneralNames(it.accessLocation)) }
            .firstNotNullOfOrNull { u ->
                runCatching { download(u, 2_000_000)?.let { b -> cf.generateCertificates(ByteArrayInputStream(b)).firstOrNull() as? X509Certificate } }.getOrNull()
            }
    }.getOrNull()

    private fun download(url: String, max: Int): ByteArray? {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 10_000
        c.readTimeout = 30_000
        c.instanceFollowRedirects = true
        try {
            if (c.responseCode !in 200..299) return null
            c.inputStream.use { s ->
                val out = java.io.ByteArrayOutputStream()
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = s.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    if (out.size() > max) return null
                }
                return out.toByteArray()
            }
        } finally {
            c.disconnect()
        }
    }

    private fun sha1(s: String) = MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }

    /** LCR da URL (guardada no aparelho até a próxima atualização prevista). */
    private fun crl(url: String): X509CRL? {
        crlFetcher?.let { f -> return f(url)?.let { cf.generateCRL(ByteArrayInputStream(it)) as X509CRL } }
        val file = cacheDir?.let { File(it, sha1(url) + ".crl") }
        if (file != null && file.exists()) {
            val cached = runCatching { file.inputStream().use { cf.generateCRL(it) as X509CRL } }.getOrNull()
            val next = cached?.nextUpdate
            if (cached != null && next != null && next.after(Date())) return cached
        }
        val bytes = runCatching { download(url, 80_000_000) }.getOrNull() ?: return null
        val crl = runCatching { cf.generateCRL(ByteArrayInputStream(bytes)) as X509CRL }.getOrNull() ?: return null
        runCatching { file?.writeBytes(bytes) }
        return crl
    }

    private fun name(c: X509Certificate) = Certs.cn(c)

    /**
     * at = momento da assinatura (carimbo de tempo, se houver). online = consultar as LCRs.
     */
    fun check(cert: X509Certificate, embedded: Collection<X509Certificate>, at: Date, online: Boolean): Identity {
        val chain = buildChain(cert, embedded, online)
            ?: return Identity(Status.UNTRUSTED,
                "Certificado fora da ICP-Brasil (ou cadeia incompleta): a identidade de quem assinou não foi confirmada.",
                listOf(name(cert)))
        val names = chain.map { name(it) }
        chain.firstOrNull { runCatching { it.checkValidity(at); false }.getOrDefault(true) }?.let { c ->
            return Identity(Status.EXPIRED,
                if (c == cert) "O certificado estava fora da validade na data da assinatura."
                else "O certificado da AC “${name(c)}” estava fora da validade na data da assinatura.", names)
        }
        if (!online) return Identity(Status.NO_REVOCATION_CHECK, "Cadeia ICP-Brasil confirmada. Revogação ainda não consultada.", names)
        var unchecked: String? = null
        for (i in 0 until chain.size - 1) {
            val c = chain[i]
            val issuer = chain[i + 1]
            val urls = crlUrls(c)
            if (urls.isEmpty()) continue
            val list = urls.firstNotNullOfOrNull { u -> crl(u)?.takeIf { l -> runCatching { l.verify(issuer.publicKey); true }.getOrDefault(false) } }
            if (list == null) {
                unchecked = name(issuer)
                continue
            }
            list.getRevokedCertificate(c)?.let { e ->
                val d = e.revocationDate
                if (d == null || !d.after(at)) {
                    return Identity(Status.REVOKED,
                        (if (c == cert) "O certificado de quem assinou foi revogado" else "O certificado da AC “${name(c)}” foi revogado") +
                            (d?.let { " em ${java.text.SimpleDateFormat("dd/MM/yyyy", java.util.Locale("pt", "BR")).format(it)}" } ?: "") +
                            ", antes da assinatura.", names, d)
                }
            }
        }
        if (unchecked != null) return Identity(Status.NO_REVOCATION_CHECK,
            "Cadeia ICP-Brasil confirmada. Não foi possível consultar a lista de revogação da “$unchecked” (sem internet?).", names)
        return Identity(Status.TRUSTED, "Identidade confirmada: certificado ICP-Brasil válido na data da assinatura e não revogado.", names)
    }
}
