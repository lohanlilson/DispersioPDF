package io.github.lohanlilson.lumenpdf

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.pdmodel.PDDocument
import kotlinx.coroutines.runBlocking
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.random.Random

/** Mede quanto custa cada etapa de uma edição num PDF grande (só registra os tempos). */
@RunWith(AndroidJUnit4::class)
class DesempenhoTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun big(): File {
        val f = File(ctx.cacheDir, "grande.pdf")
        if (f.exists() && f.length() > 20_000_000) return f
        val doc = PdfDocument()
        val rnd = Random(1)
        val px = IntArray(500 * 700) { rnd.nextInt() or 0xFF000000.toInt() }
        val bmp = Bitmap.createBitmap(px, 500, 700, Bitmap.Config.ARGB_8888)
        val p = Paint().apply { color = Color.BLACK; textSize = 9f }
        for (n in 1..40) {
            val page = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, n).create())
            page.canvas.drawBitmap(bmp, null, android.graphics.Rect(60, 400, 535, 800), null)
            repeat(30) { k -> page.canvas.drawText("Página $n, cláusula ${k + 1}: texto de exemplo do contrato.", 40f, 60f + k * 11f, p) }
            doc.finishPage(page)
        }
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private inline fun <T> t(label: String, block: () -> T): T {
        val a = System.nanoTime()
        val r = block()
        Log.i("LumenTest", "DESEMPENHO $label: ${(System.nanoTime() - a) / 1_000_000} ms")
        return r
    }

    @Test
    fun edicaoEmPdfGrande() {
        val src = big()
        Log.i("LumenTest", "DESEMPENHO arquivo: ${src.length() / 1_000_000} MB")
        val rect = RectF(40f, 790f, 300f, 776f)
        val full = File(ctx.cacheDir, "g1.pdf")
        t("destaque (abrir+gravar completo)") { Editor.apply(src, full, null) { d -> Editor.markup(d, 0, listOf(rect), Markup.HIGHLIGHT, 0xFFFFD400) } }
        val inc = File(ctx.cacheDir, "g2.pdf")
        t("destaque (gravação incremental)") {
            PDDocument.load(src).use { d ->
                val ch = Editor.markup(d, 0, listOf(rect), Markup.HIGHLIGHT, 0xFFFFD400)
                inc.outputStream().buffered().use { o -> ch.forEach { it.isNeedToBeUpdated = true }; d.saveIncremental(o, ch.toHashSet()) }
            }
        }
        t("só abrir no PDFBox") { PDDocument.load(full).use { it.numberOfPages } }
        t("campos + comentários (2 aberturas)") {
            PDDocument.load(full).use { Editor.fields(it) }
            PDDocument.load(full).use { Editor.annotations(it) }
        }
        val e = PdfEngine(ctx)
        val pdf = t("reabrir no PDFium") { runBlocking { e.open(ctx, Uri.fromFile(full), null) } }
        t("desenhar página 1") { runBlocking { e.render(pdf, 0, 1080) } }
        t("editar texto: analisar o toque") { PDDocument.load(full).use { TextEdit.analyze(it, 0, rect, 60f, 783f) } }
        t("ler bytes (validação de assinaturas)") { full.readBytes().size }
        runBlocking { e.close(pdf) }
        // desenho à mão: cópia da lista de pontos a cada movimento (como no app)
        val pts = mutableListOf<androidx.compose.ui.geometry.Offset>()
        t("traço de 1500 pontos (cópias da lista)") {
            var last: List<androidx.compose.ui.geometry.Offset> = emptyList()
            repeat(1500) { k -> pts.add(androidx.compose.ui.geometry.Offset(k.toFloat(), k.toFloat())); last = pts.toList() }
            last.size
        }
    }
}
