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
import com.tom_roush.pdfbox.text.PDFTextStripper
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Ferramentas da versão 0.2.0: comentários, editar texto, marca d'água, numeração, comprimir, senha, fotos. */
@RunWith(AndroidJUnit4::class)
class ToolsTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val dir get() = File(ctx.cacheDir, "ferramentas").apply { mkdirs() }

    private fun pdf(withPhoto: Boolean = false): File {
        val doc = PdfDocument()
        val p = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        p.canvas.drawText("Valor total: R$ 10.000,00", 60f, 100f, Paint().apply { color = Color.BLACK; textSize = 18f })
        if (withPhoto) {
            val bmp = Bitmap.createBitmap(1800, 1200, Bitmap.Config.ARGB_8888)
            for (y in 0 until 1200 step 3) for (x in 0 until 1800 step 3) bmp.setPixel(x, y, Color.rgb(x % 255, y % 255, (x + y) % 255))
            p.canvas.drawBitmap(bmp, null, android.graphics.Rect(60, 200, 535, 520), null)
        }
        doc.finishPage(p)
        val f = File(dir, if (withPhoto) "foto.pdf" else "base.pdf")
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private fun text(f: File, pwd: String = "") = PDDocument.load(f, pwd).use { PDFTextStripper().getText(it) }

    @Test
    fun comentariosEditarTexto() = runBlocking {
        val src = pdf()
        val a = File(dir, "a.pdf")
        Editor.apply(src, a, null) { d -> Editor.note(d, 0, 300f, 700f, "Conferir", 0xFFFFD400) + Editor.ink(d, 0, listOf(floatArrayOf(100f, 400f, 200f, 450f)), 0xFFD7373F, 2f) }
        val refs = PDDocument.load(a).use { Editor.annotations(it) }
        assertEquals(listOf("Text", "Ink"), refs.map { it.subtype })
        val b = File(dir, "b.pdf")
        Editor.apply(a, b, null) { d -> Editor.moveAnnot(d, refs[1], 50f, -20f) + Editor.recolorAnnot(d, refs[0], 0xFF1473E6) }
        val moved = PDDocument.load(b).use { Editor.annotations(it) }
        assertEquals(refs[1].rect.left + 50f, moved[1].rect.left, 0.5f)
        val c = File(dir, "c.pdf")
        Editor.apply(b, c, null) { d -> Editor.deleteAnnot(d, moved[0]) }
        assertEquals(listOf("Ink"), PDDocument.load(c).use { Editor.annotations(it) }.map { it.subtype })
        // editar a linha "Valor total": localiza pelo PDFium e troca
        val engine = (ctx.applicationContext as LumenApp).engine
        val pdf = engine.open(ctx, Uri.fromFile(c))
        val line = engine.lineAt(pdf, 0, 70f / 595f, 95f / 595f)
        engine.close(pdf)
        Log.i("LumenTest", "linha: $line")
        assertTrue("linha não encontrada: $line", line != null && line.text.contains("10.000,00"))
        val e = File(dir, "e.pdf")
        Editor.apply(c, e, null) { d -> Editor.replaceText(d, 0, line!!.rect, line.x, line.baseline, "Valor total: R$ 12.500,00", line.size, 0xFF1C1B22) }
        assertTrue(text(e).contains("12.500,00"))
    }

    @Test
    fun marcaNumeracaoComprimirSenhaFotos() {
        val src = pdf(withPhoto = true)
        val w = File(dir, "w.pdf")
        Editor.applyFull(src, w, null) { d, _ -> Editor.watermark(d, "CONFIDENCIAL", 0.2f, 0xFFD7373F); Editor.pageNumbers(d, "Página {n} de {total}") }
        val t = text(w).replace(Regex("\\s"), "")
        Log.i("LumenTest", "marca/numeração: $t")
        assertTrue("numeração: $t", t.contains("Página1de1"))
        assertTrue("marca d'água: $t", t.contains("CONFIDENCIAL") || t.reversed().contains("CONFIDENCIAL"))
        val small = File(dir, "small.pdf")
        var n = 0
        Editor.applyFull(src, small, null) { d, _ -> n = Editor.compress(d, 600, 0.5f) }
        Log.i("LumenTest", "comprimir: ${src.length()} -> ${small.length()} ($n imagens)")
        assertTrue(n >= 1 && small.length() < src.length())
        val locked = File(dir, "locked.pdf")
        Editor.applyFull(src, locked, null) { d, _ -> Editor.protect(d, "1234", "", true, false, false) }
        assertTrue(runCatching { PDDocument.load(locked).close() }.isFailure)
        assertTrue(text(locked, "1234").contains("Valor total"))
        val open = File(dir, "open.pdf")
        Editor.applyFull(locked, open, "1234") { d, _ -> Editor.unprotect(d) }
        assertTrue(text(open).contains("Valor total"))
        val fotos = File(dir, "fotos.pdf")
        Editor.imagesToPdf(listOf(Bitmap.createBitmap(1200, 800, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) },
            Bitmap.createBitmap(800, 1200, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.RED) }), fotos)
        PDDocument.load(fotos).use { d ->
            assertEquals(2, d.numberOfPages)
            assertTrue(d.getPage(0).mediaBox.width > d.getPage(0).mediaBox.height)
        }
    }
}
