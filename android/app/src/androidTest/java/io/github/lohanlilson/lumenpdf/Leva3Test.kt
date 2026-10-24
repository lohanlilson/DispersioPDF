package io.github.lohanlilson.lumenpdf

import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.pdf.PdfDocument
import android.util.Log
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationWidget
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDAcroForm
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDTextField
import com.tom_roush.pdfbox.pdmodel.PDResources
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.asn1.x509.BasicConstraints
import org.bouncycastle.asn1.x509.CRLDistPoint
import org.bouncycastle.asn1.x509.CRLReason
import org.bouncycastle.asn1.x509.DistributionPoint
import org.bouncycastle.asn1.x509.DistributionPointName
import org.bouncycastle.asn1.x509.Extension
import org.bouncycastle.asn1.x509.GeneralName
import org.bouncycastle.asn1.x509.GeneralNames
import org.bouncycastle.asn1.x509.KeyUsage
import org.bouncycastle.cert.X509v2CRLBuilder
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.math.BigInteger
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.cert.X509Certificate
import java.util.Date

/** Validação ICP-Brasil, senha com digital, meus dados e atalhos do ícone. */
@RunWith(AndroidJUnit4::class)
class Leva3Test {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val day = 86_400_000L

    @After
    fun limpar() {
        IcpTrust.extraRoots = emptyList()
        IcpTrust.crlFetcher = null
        PasswordVault.requireAuth = true
    }

    private fun kp(): KeyPair = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
    private fun conv(h: org.bouncycastle.cert.X509CertificateHolder): X509Certificate =
        JcaX509CertificateConverter().setProvider(Certs.BC).getCertificate(h)

    private fun pdf(name: String): File {
        val doc = PdfDocument()
        val p = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        p.canvas.drawText("CONTRATO DE TESTE ICP", 50f, 80f, Paint().apply { color = Color.BLACK; textSize = 14f })
        doc.finishPage(p)
        val f = File(ctx.cacheDir, name)
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    @Test
    fun cadeiaIcpReal() {
        IcpTrust.init(ctx)
        Log.i("LumenTest", "ICP: ${IcpTrust.rootCount} raízes, ${IcpTrust.acCount} ACs")
        assertEquals(6, IcpTrust.rootCount)
        assertTrue(IcpTrust.acCount > 100)
        // uma AC de segundo nível real (emitida por outra AC, não pela raiz) monta a cadeia até a raiz sem internet
        val acs = ctx.assets.open("icp/acs.pem").use { s ->
            java.security.cert.CertificateFactory.getInstance("X.509").generateCertificates(s).map { it as X509Certificate }
        }
        val roots = ctx.assets.open("icp/raizes.pem").use { s ->
            java.security.cert.CertificateFactory.getInstance("X.509").generateCertificates(s).map { it as X509Certificate }
        }
        val now = Date()
        val leaf = acs.first { c ->
            runCatching { c.checkValidity(now); true }.getOrDefault(false) &&
                roots.none { it.subjectX500Principal == c.issuerX500Principal } &&
                acs.any { it.subjectX500Principal == c.issuerX500Principal }
        }
        val off = IcpTrust.check(leaf, emptyList(), now, online = false)
        Log.i("LumenTest", "offline ${Certs.cn(leaf)}: $off")
        assertEquals(IcpTrust.Status.NO_REVOCATION_CHECK, off.status)
        assertTrue(off.chain.size >= 3 && off.chain.last().contains("Raiz Brasileira"))
        // com internet: LCR real da AC (o emulador do teste automático tem internet)
        val on = IcpTrust.check(leaf, emptyList(), now, online = true)
        Log.i("LumenTest", "online: $on")
        assertTrue("$on", on.status == IcpTrust.Status.TRUSTED || on.status == IcpTrust.Status.NO_REVOCATION_CHECK)
    }

    @Test
    fun revogadoEForaDaIcp() {
        IcpTrust.init(ctx)
        val rootKp = kp()
        val rootName = X500Name("CN=AC Raiz de Teste, O=Teste")
        val root = conv(JcaX509v3CertificateBuilder(rootName, BigInteger.ONE, Date(System.currentTimeMillis() - 10 * day),
            Date(System.currentTimeMillis() + 3650 * day), rootName, rootKp.public)
            .addExtension(Extension.basicConstraints, true, BasicConstraints(true))
            .addExtension(Extension.keyUsage, true, KeyUsage(KeyUsage.keyCertSign or KeyUsage.cRLSign))
            .build(JcaContentSignerBuilder("SHA256withRSA").build(rootKp.private)))
        val eeKp = kp()
        val url = "http://lcr.teste.invalid/ac.crl"
        val ee = conv(JcaX509v3CertificateBuilder(rootName, BigInteger.valueOf(77), Date(System.currentTimeMillis() - 5 * day),
            Date(System.currentTimeMillis() + 365 * day), X500Name("CN=FULANO DE TAL:11122233344"), eeKp.public)
            .addExtension(Extension.cRLDistributionPoints, false, CRLDistPoint(arrayOf(DistributionPoint(
                DistributionPointName(GeneralNames(GeneralName(GeneralName.uniformResourceIdentifier, url))), null, null))))
            .build(JcaContentSignerBuilder("SHA256withRSA").build(rootKp.private)))
        val sc = SigningCert(eeKp.private, listOf(ee, root))
        val signed = PdfSigner.sign(pdf("icp.pdf"), null, sc, 0, RectF(300f, 200f, 540f, 140f), null, "", "", false).bytes

        // fora da ICP-Brasil
        var v = PdfSigner.validate(signed)
        assertTrue(v.single().ok)
        assertEquals(IcpTrust.Status.UNTRUSTED, v.single().identity?.status)

        // raiz aceita (como se fosse uma AC Raiz ICP-Brasil): cadeia ok, sem LCR consultada
        IcpTrust.extraRoots = listOf(root)
        v = PdfSigner.validate(signed)
        assertEquals(IcpTrust.Status.NO_REVOCATION_CHECK, v.single().identity?.status)

        fun crl(revoked: Boolean): ByteArray {
            val b = X509v2CRLBuilder(rootName, Date(System.currentTimeMillis() - day)).setNextUpdate(Date(System.currentTimeMillis() + day))
            if (revoked) b.addCRLEntry(BigInteger.valueOf(77), Date(System.currentTimeMillis() - 2 * day), CRLReason.keyCompromise)
            return b.build(JcaContentSignerBuilder("SHA256withRSA").build(rootKp.private)).encoded
        }
        IcpTrust.crlFetcher = { u -> assertEquals(url, u); crl(false) }
        v = PdfSigner.validate(signed, online = true)
        Log.i("LumenTest", "não revogado: ${v.single().identity}")
        assertEquals(IcpTrust.Status.TRUSTED, v.single().identity?.status)

        IcpTrust.crlFetcher = { crl(true) }
        v = PdfSigner.validate(signed, online = true)
        Log.i("LumenTest", "revogado: ${v.single().identity}")
        assertEquals(IcpTrust.Status.REVOKED, v.single().identity?.status)
        assertTrue(v.single().badCert)

        // LCR inacessível: cadeia confirmada, revogação não consultada
        IcpTrust.crlFetcher = { null }
        v = PdfSigner.validate(signed, online = true)
        assertEquals(IcpTrust.Status.NO_REVOCATION_CHECK, v.single().identity?.status)
    }

    @Test
    fun senhaGuardada() = kotlinx.coroutines.runBlocking {
        PasswordVault.requireAuth = false   // o emulador não tem digital cadastrada
        PasswordVault.forgetAll(ctx)
        assertTrue(!PasswordVault.has(ctx, "meu.pfx"))
        PasswordVault.store(ctx, "meu.pfx", "Senh@ çom acento 123")
        assertTrue(PasswordVault.has(ctx, "meu.pfx"))
        val enc = ctx.getSharedPreferences("cofre", 0).getString("meu.pfx", "")!!
        assertTrue("senha em texto puro", !enc.contains("Senh"))
        val act = launchActivity()
        val r = PasswordVault.unlock(act, "meu.pfx")
        assertEquals(PasswordVault.Result.Ok("Senh@ çom acento 123"), r)
        PasswordVault.forget(ctx, "meu.pfx")
        assertTrue(!PasswordVault.has(ctx, "meu.pfx"))
        act.finish()
    }

    private fun launchActivity(): MainActivity {
        val i = android.content.Intent(ctx, MainActivity::class.java).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        return InstrumentationRegistry.getInstrumentation().startActivitySync(i) as MainActivity
    }

    private fun formPdf(): File {
        val f = File(ctx.cacheDir, "formulario.pdf")
        PDDocument().use { doc ->
            val page = PDPage(PDRectangle.A4)
            doc.addPage(page)
            val form = PDAcroForm(doc)
            doc.documentCatalog.acroForm = form
            val res = PDResources()
            res.put(COSName.getPDFName("Helv"), PDType1Font.HELVETICA)
            form.defaultResources = res
            form.defaultAppearance = "/Helv 10 Tf 0 g"
            listOf("Nome completo", "CPF", "Nome da mãe", "E-mail", "Estado civil", "Data", "Observações").forEachIndexed { i, n ->
                val t = PDTextField(form)
                t.partialName = "campo$i"
                t.alternateFieldName = n
                val w: PDAnnotationWidget = t.widgets[0]
                w.rectangle = PDRectangle(150f, 750f - i * 40f, 300f, 20f)
                w.page = page
                page.annotations.add(w)
                form.fields.add(t)
            }
            doc.save(f)
        }
        return f
    }

    @Test
    fun meusDados() {
        Autofill.save(ctx, mapOf("nome" to "Fulano de Tal", "cpf" to "111.222.333-44", "email" to "fulano@exemplo.com", "estadocivil" to "Casado"))
        val f = formPdf()
        val fields = PDDocument.load(f).use { Editor.fields(it) }
        val plan = Autofill.plan(fields, Autofill.load(ctx))
        val got = plan.associate { it.field.label to it.value }
        Log.i("LumenTest", "autopreencher: $got")
        assertEquals("Fulano de Tal", got["Nome completo"])
        assertEquals("111.222.333-44", got["CPF"])
        assertEquals("fulano@exemplo.com", got["E-mail"])
        assertEquals("Casado", got["Estado civil"])
        assertNotNull(got["Data"])
        assertTrue("nome da mãe não é meu", "Nome da mãe" !in got && "Observações" !in got)
        val out = File(ctx.cacheDir, "formulario-preenchido.pdf")
        Editor.apply(f, out, null) { d -> plan.flatMap { Editor.setField(d, it.field.name, it.value) } }
        val after = PDDocument.load(out).use { Editor.fields(it) }.associate { it.label to it.value }
        assertEquals("Fulano de Tal", after["Nome completo"])
        assertEquals("", after["Nome da mãe"])
        Autofill.save(ctx, Autofill.ITEMS.associate { it.key to "" })
    }

    @Test
    fun atalhosDoIcone() {
        val fixed = ShortcutManagerCompat.getShortcuts(ctx, ShortcutManagerCompat.FLAG_MATCH_MANIFEST).map { it.id }
        Log.i("LumenTest", "atalhos fixos: $fixed")
        assertTrue(fixed.containsAll(listOf("escanear", "abrir")))
        Shortcuts.updateRecents(ctx, listOf(RecentDoc("content://x/contrato.pdf", "Contrato.pdf", 0, 1L), RecentDoc("content://x/b.pdf", "B.pdf", 0, 0L)))
        val dyn = ShortcutManagerCompat.getDynamicShortcuts(ctx)
        Log.i("LumenTest", "atalhos recentes: ${dyn.map { it.shortLabel }}")
        assertEquals(listOf("Contrato", "B"), dyn.sortedBy { it.rank }.map { it.shortLabel.toString() })
        ShortcutManagerCompat.removeAllDynamicShortcuts(ctx)
    }
}
