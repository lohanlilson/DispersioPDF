package io.github.lohanlilson.dispersio

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.util.Log
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.zxing.BarcodeFormat
import com.google.zxing.common.BitMatrix
import com.google.zxing.oned.ITFWriter
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate

/** Boleto, Pix e páginas de lado: leitura do código de barras/QR desenhado e endireitar páginas. */
@RunWith(AndroidJUnit4::class)
class BoletoTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val PIX = "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR" +
        "5913Fulano de Tal6008BRASILIA62070503***63041D3D"
    private val TXT = listOf("CONTRATO DE CESSÃO DE CRÉDITOS", "Pelo presente instrumento particular, de um lado a cedente,",
        "empresa com sede nesta capital, e de outro lado a cessionária, têm entre si", "justo e contratado o seguinte:",
        "Cláusula primeira. A cedente transfere à cessionária os créditos", "descritos no anexo deste contrato, com todos os direitos",
        "e garantias, pelo preço certo e ajustado entre as partes.", "Cláusula segunda. O pagamento será feito por transferência",
        "bancária na data da assinatura deste instrumento, servindo", "o comprovante como recibo de quitação plena e irrevogável.")

    private fun boleto(): String {
        val fator = 1000 + java.time.temporal.ChronoUnit.DAYS.between(LocalDate.of(2025, 2, 22), LocalDate.of(2026, 11, 10))
        val sem = "237" + "9" + "%04d".format(fator) + "%010d".format(123456L) + "0123456789012345678901234"
        return sem.substring(0, 4) + Pagamentos.mod11Boleto(sem) + sem.substring(4)
    }

    private fun draw(c: Canvas, m: BitMatrix, x: Float, y: Float, w: Float, h: Float) {
        val p = Paint().apply { color = Color.BLACK }
        val sx = w / m.width; val sy = h / m.height
        for (j in 0 until m.height) for (i in 0 until m.width) if (m[i, j]) c.drawRect(x + i * sx, y + j * sy, x + (i + 1) * sx, y + (j + 1) * sy, p)
    }

    private fun text(c: Canvas) {
        val p = Paint().apply { color = Color.BLACK; textSize = 13f }
        (TXT + TXT).forEachIndexed { k, s -> c.drawText(s, 50f, 90f + k * 19f, p) }
    }

    private fun makePdf(): File {
        val doc = PdfDocument()
        val bc = boleto()
        // 1: boleto (linha digitável em texto + código de barras desenhado)
        doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create()).also { pg ->
            val p = Paint().apply { color = Color.BLACK; textSize = 12f }
            pg.canvas.drawText("Banco Bradesco 237-2", 40f, 60f, p)
            pg.canvas.drawText(Pagamentos.fmtBoleto(Pagamentos.barcodeToLine(bc)), 40f, 90f, p)
            draw(pg.canvas, ITFWriter().encode(bc, BarcodeFormat.ITF, 0, 0), 40f, 110f, 420f, 50f)
            doc.finishPage(pg)
        }
        // 2: Pix só em QR Code
        doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 2).create()).also { pg ->
            draw(pg.canvas, QRCodeWriter().encode(PIX, BarcodeFormat.QR_CODE, 0, 0), 60f, 60f, 220f, 220f)
            doc.finishPage(pg)
        }
        // 3: texto digital de cabeça para baixo
        doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 3).create()).also { pg ->
            pg.canvas.rotate(180f, 297.5f, 421f); text(pg.canvas); doc.finishPage(pg)
        }
        // 4: página "escaneada" (imagem) de cabeça para baixo
        val bmp = Bitmap.createBitmap(1240, 1754, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.WHITE)
            val c = Canvas(this); c.scale(1240 / 595f, 1754 / 842f); text(c)
        }
        val up = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, Matrix().apply { postRotate(180f) }, true)
        doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 4).create()).also { pg ->
            pg.canvas.drawBitmap(up, null, android.graphics.Rect(0, 0, 595, 842), null); doc.finishPage(pg)
        }
        // 5: certa
        doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 5).create()).also { pg -> text(pg.canvas); doc.finishPage(pg) }
        val f = File(ctx.filesDir, "recebidos/boleto.pdf").apply { parentFile?.mkdirs(); delete() }
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private fun waitFor(ms: Long, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(100) }
        return cond()
    }

    @After
    fun limpar() { ctx.getSharedPreferences("recentes", 0).edit().clear().commit() }

    @Test
    fun boletoPixEPaginasDeLado() {
        AppVm.AUTOSAVE_MS = 600_000
        val f = makePdf()
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            assertTrue(waitFor(15_000) { vm.doc != null && !vm.loading })
            val d = vm.doc!!
            val t0 = System.currentTimeMillis()
            assertTrue("procurou boletos", waitFor(60_000) { d.payments != null })
            Log.i("DispersioTest", "DESEMPENHO boletos/Pix em 5 páginas: ${System.currentTimeMillis() - t0} ms")
            val pay = d.payments!!
            pay.forEach { Log.i("DispersioTest", "achado: pág ${it.page + 1} ${it.kind} ${it.ok} ${it.source} ${it.title} ${it.summary}") }
            val b = pay.first { it.kind == "boleto" }
            assertTrue(b.ok); assertEquals("texto e código", b.source); assertEquals("R$ 1.234,56", b.details.toMap()["Valor"])
            val pix = pay.first { it.kind == "pix" }
            assertTrue(pix.ok); assertEquals(1, pix.page); assertEquals("código", pix.source)

            assertTrue("procurou páginas de lado", waitFor(90_000) { d.orientFixes.isNotEmpty() })
            Log.i("DispersioTest", "DESEMPENHO posição das páginas: ${System.currentTimeMillis() - t0} ms; ${d.orientFixes}")
            assertEquals(mapOf(2 to 180, 3 to 180), d.orientFixes)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.straighten(d, d.orientFixes) }
            assertTrue(waitFor(20_000) { d.orientFixes.isEmpty() && !d.busy && d.dirty })
            val rot = runBlocking { (0 until 5).map { vm.engine.pageRotation(d.pdf, it) } }
            assertEquals(listOf(0, 0, 180, 180, 0), rot)
            val again = com.tom_roush.pdfbox.pdmodel.PDDocument.load(d.work!!).use { pd ->
                runBlocking { Orientation.fixes(vm.engine, d.pdf, 0 until 5, textRot = { Orientation.textRotation(pd, it) }) }
            }
            assertEquals(emptyMap<Int, Int>(), again)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.undo(d) }
            assertTrue(waitFor(20_000) { !d.busy && runBlocking { vm.engine.pageRotation(d.pdf, 2) } == 0 })
            assertFalse(d.canUndo)
        }
    }
}
