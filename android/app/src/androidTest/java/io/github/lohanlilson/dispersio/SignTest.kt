package io.github.lohanlilson.dispersio

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.util.Date

/** Assinatura com certificado: duas assinaturas seguidas e uma edição depois — todas devem continuar íntegras. */
@RunWith(AndroidJUnit4::class)
class SignTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun pfx(cn: String): File {
        val kp = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
        val name = X500Name("CN=$cn, O=Teste")
        val holder = JcaX509v3CertificateBuilder(name, BigInteger.valueOf(System.nanoTime()), Date(System.currentTimeMillis() - 86400000L),
            Date(System.currentTimeMillis() + 3650L * 86400000L), name, kp.public)
            .build(JcaContentSignerBuilder("SHA256withRSA").build(kp.private))
        val cert = JcaX509CertificateConverter().setProvider(Certs.BC).getCertificate(holder)
        val ks = KeyStore.getInstance("PKCS12", Certs.BC)
        ks.load(null, null)
        ks.setKeyEntry("chave", kp.private, "1234".toCharArray(), arrayOf(cert))
        val f = File(ctx.cacheDir, "$cn.pfx".replace(":", "_"))
        f.outputStream().use { ks.store(it, "1234".toCharArray()) }
        return f
    }

    private fun pdf(): File {
        val doc = PdfDocument()
        val p = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        p.canvas.drawText("CONTRATO DE CESSÃO — Valor R$ 10.000,00", 50f, 80f, Paint().apply { color = Color.BLACK; textSize = 14f })
        doc.finishPage(p)
        val f = File(ctx.cacheDir, "contrato.pdf")
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    @Test
    fun duasAssinaturasEEdicao() {
        val src = pdf()
        val a = Certs.fromPfx(pfx("FULANO DE TAL:11122233344"), "1234")
        val b = Certs.fromPfx(pfx("BELTRANO"), "1234")
        val s1 = PdfSigner.sign(src, null, a, 0, RectF(300f, 200f, 540f, 140f), null, "Concordo", "Goiânia", false)
        val f1 = File(ctx.cacheDir, "s1.pdf").apply { writeBytes(s1.bytes) }
        val s2 = PdfSigner.sign(f1, null, b, 0, RectF(50f, 200f, 290f, 140f), null, "", "", false)
        val f2 = File(ctx.cacheDir, "s2.pdf").apply { writeBytes(s2.bytes) }
        var v = PdfSigner.validate(s2.bytes)
        Log.i("DispersioTest", "assinaturas: $v")
        assertEquals(2, v.size)
        assertTrue("assinaturas inválidas: $v", v.all { it.ok })
        assertEquals("FULANO DE TAL", v[0].signer)
        assertEquals("11122233344", v[0].document)
        assertTrue(!v[0].coversWhole && v[1].coversWhole)
        // edição depois de assinado (gravação incremental): as assinaturas continuam íntegras
        val f3 = File(ctx.cacheDir, "s3.pdf")
        Editor.apply(f2, f3, null) { d -> Editor.note(d, 0, 100f, 500f, "Comentário depois", 0xFFFFD400) }
        v = PdfSigner.validate(f3.readBytes())
        Log.i("DispersioTest", "depois da edição: $v")
        assertTrue("edição invalidou: $v", v.size == 2 && v.all { it.ok })
        // aparência do carimbo renderizada pelo PDFium
        runBlocking {
            val engine = (ctx.applicationContext as DispersioApp).engine
            val pdf = engine.open(ctx, Uri.fromFile(f3))
            val bmp = engine.render(pdf, 0, 1000)
            val dir = File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }
            File(dir, "08_assinado.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
            f3.copyTo(File(dir, "assinado.pdf"), overwrite = true)
            engine.close(pdf)
        }
    }

    @Test
    fun carimboDeTempo() {
        // com internet, o carimbo de tempo é aplicado; sem, a assinatura sai assim mesmo e o problema é informado
        val r = PdfSigner.sign(pdf(), null, Certs.fromPfx(pfx("TSA TESTE"), "1234"), 0, RectF(300f, 200f, 540f, 140f), null, "", "", true)
        val v = PdfSigner.validate(r.bytes)
        Log.i("DispersioTest", "tsa=${r.timestamp} problema=${r.problem} validação=$v")
        assertTrue(v.single().ok)
        if (r.timestamp) assertTrue(v.single().tsaDate != null)
    }
}
