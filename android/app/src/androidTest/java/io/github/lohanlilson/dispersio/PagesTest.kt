package io.github.lohanlilson.dispersio

import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Organizar páginas: girar, excluir, reordenar, inserir, extrair e juntar. */
@RunWith(AndroidJUnit4::class)
class PagesTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun pdf(name: String, labels: List<String>): File {
        val doc = PdfDocument()
        labels.forEachIndexed { k, l ->
            val p = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, k + 1).create())
            p.canvas.drawText(l, 60f, 100f, Paint().apply { color = Color.BLACK; textSize = 20f })
            doc.finishPage(p)
        }
        val f = File(ctx.cacheDir, name)
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private fun order(f: File): List<String> = PDDocument.load(f).use { d ->
        (1..d.numberOfPages).map { i -> PDFTextStripper().apply { startPage = i; endPage = i }.getText(d).replace(Regex("\\s"), "") }
    }

    @Test
    fun operacoes() {
        val a = pdf("a.pdf", listOf("A1", "A2", "A3"))
        val b = pdf("b.pdf", listOf("B1", "B2"))
        val f1 = File(ctx.cacheDir, "o1.pdf")
        Editor.applyFull(a, f1, null) { d, _ -> Editor.rotate(d, listOf(0), 90); Editor.reorder(d, listOf(2, 0, 1)) }
        assertEquals(listOf("A3", "A1", "A2"), order(f1))
        PDDocument.load(f1).use { assertEquals(90, it.getPage(1).rotation) }
        val f2 = File(ctx.cacheDir, "o2.pdf")
        Editor.applyFull(f1, f2, null) { d, keep -> Editor.insertPdf(d, b, 1, keep); Editor.delete(d, listOf(4)) }
        assertEquals(listOf("A3", "B1", "B2", "A1"), order(f2))
        val f3 = File(ctx.cacheDir, "o3.pdf")
        Editor.applyFull(f2, f3, null) { d, _ -> Editor.insertBlank(d, 0) }
        assertEquals(5, PDDocument.load(f3).use { it.numberOfPages })
        val ex = File(ctx.cacheDir, "ex.pdf")
        Editor.extract(f2, null, listOf(1, 3), ex)
        assertEquals(listOf("B1", "A1"), order(ex))
        val m = File(ctx.cacheDir, "m.pdf")
        Editor.merge(listOf(a, b), m)
        assertEquals(listOf("A1", "A2", "A3", "B1", "B2"), order(m))
    }
}
