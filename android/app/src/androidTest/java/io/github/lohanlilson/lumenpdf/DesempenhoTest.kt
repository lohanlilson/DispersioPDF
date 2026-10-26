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

    @org.junit.After
    fun limparRecentes() { ctx.getSharedPreferences("recentes", 0).edit().clear().commit() }

    @Test
    fun edicaoEmPdfGrande() {
        val src = big()
        Log.i("LumenTest", "DESEMPENHO arquivo: ${src.length() / 1_000_000} MB, 40 páginas")
        val rect = RectF(40f, 790f, 300f, 776f)
        val out = File(ctx.cacheDir, "g1.pdf")
        t("1 gravar destaque (incremental)") { Editor.apply(src, out, null) { d -> Editor.markup(d, 0, listOf(rect), Markup.HIGHLIGHT, 0xFFFFD400) } }
        val e = PdfEngine(ctx)
        val first = t("2a abrir (sem tamanhos conhecidos)") { runBlocking { e.open(ctx, Uri.fromFile(src), null) } }
        runBlocking { kotlinx.coroutines.delay(4000) }   // medição das demais páginas em segundo plano
        val known = first.sizes.toList()
        Log.i("LumenTest", "DESEMPENHO 2b todas medidas em segundo plano: ${first.measured.all { it }}")
        val pdf = t("2c reabrir depois da edição (tamanhos conhecidos)") { runBlocking { e.open(ctx, Uri.fromFile(out), null, known) } }
        val parsed = t("3a campos + comentários (uma leitura)") { PDDocument.load(out).use { Parsed(Editor.fields(it), Editor.annotations(it)) } }
        t("3b posições na tela (uma abertura por página)") { runBlocking { e.fracOfAll(pdf, parsed.annots.map { it.page to it.rect }) } }
        t("desenhar página 1") { runBlocking { e.render(pdf, 0, 1080) } }
        PDDocument.load(out).use { doc ->
            t("4a editar texto: 1º toque na página") { TextEdit.analyze(doc, 0, rect, 60f, 783f) }
            t("4b editar texto: toques seguintes") { TextEdit.analyze(doc, 0, rect, 60f, 783f) }
        }
        runBlocking { e.close(first); e.close(pdf) }
    }

    @Test
    fun edicaoCompletaPeloApp() {
        val src = big()
        val intent = android.content.Intent(android.content.Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(src), "application/pdf")
            .setClass(ctx, MainActivity::class.java)
        androidx.test.core.app.ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = androidx.lifecycle.ViewModelProvider(it)[AppVm::class.java] }
            var tries = 0
            while ((vm.doc == null || vm.loading) && tries++ < 300) Thread.sleep(50)
            Thread.sleep(5000)
            val d = vm.doc!!
            repeat(3) { k ->
                val sel = runBlocking { vm.engine.pageChars(d.pdf, 0) }.let { it.wordSelection(it.charAt(0.12f, 0.08f + k * 0.013f, false), it.charAt(0.5f, 0.08f + k * 0.013f, false)) }
                val a = System.nanoTime()
                InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.markup(d, sel, Markup.HIGHLIGHT, 0xFFFFD400) }
                var n = 0
                while ((d.busy || d.pendingMarks.isNotEmpty()) && n++ < 600) Thread.sleep(20)
                val annots = d.annots.size
                Log.i("LumenTest", "DESEMPENHO 5 destaque pelo app, do toque até a tela atualizada (${k + 1}ª vez): ${(System.nanoTime() - a) / 1_000_000} ms, comentários=$annots")
            }
        }
        ctx.getSharedPreferences("recentes", 0).edit().clear().commit()
    }
}
