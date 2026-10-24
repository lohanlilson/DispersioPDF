package io.github.lohanlilson.lumenpdf

import android.graphics.RectF
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.font.PDType0Font
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.text.PDFTextStripper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Editar texto mantém fonte, negrito/itálico, tamanho e cor, e o texto antigo sai do arquivo. */
@RunWith(AndroidJUnit4::class)
class TextEditTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun doc(): File {
        val f = File(ctx.cacheDir, "estilos.pdf")
        PDDocument().use { d ->
            val p = PDPage(PDRectangle.A4)
            d.addPage(p)
            val serifBold = ctx.assets.open("fontes/LiberationSerif-Bold.ttf").use { PDType0Font.load(d, it, true) }
            PDPageContentStream(d, p).use { cs ->
                cs.beginText()
                cs.setFont(PDType1Font.HELVETICA, 12f)
                cs.setNonStrokingColor(0f, 0f, 0f)
                cs.newLineAtOffset(72f, 700f)
                cs.showText("Nome: ")
                cs.setFont(PDType1Font.HELVETICA_BOLD, 12f)
                cs.setNonStrokingColor(0.8f, 0f, 0f)
                cs.showText("FULANO DE TAL")
                cs.setFont(PDType1Font.HELVETICA, 12f)
                cs.setNonStrokingColor(0f, 0f, 0f)
                cs.showText(" - CPF 111.222.333-44")
                cs.endText()
                // fonte embutida (subconjunto só com as letras usadas), azul, 16 pt
                cs.beginText()
                cs.setFont(serifBold, 16f)
                cs.setNonStrokingColor(0f, 0.2f, 0.8f)
                cs.newLineAtOffset(72f, 650f)
                cs.showText("Contrato original")
                cs.endText()
            }
            d.save(f)
        }
        return f
    }

    private fun text(f: File) = PDDocument.load(f).use { PDFTextStripper().getText(it) }

    @Test
    fun manterEstilo() {
        TextEdit.assets = ctx.assets
        val src = doc()
        val line1 = RectF(70f, 714f, 400f, 696f)
        // toque em "FULANO"
        var run = PDDocument.load(src).use { TextEdit.analyze(it, 0, line1, 140f, 703f) }
        Log.i("LumenTest", "trecho: $run")
        assertNotNull(run)
        assertEquals("FULANO DE TAL", run!!.text)
        assertTrue(run.style.bold)
        assertEquals(0xCC0000, run.style.color and 0xFFFFFF)
        assertEquals(12f, run.style.size, 0.1f)

        val out1 = File(ctx.cacheDir, "estilos1.pdf")
        var used = ""
        Editor.apply(src, out1, null) { d ->
            val r = TextEdit.replace(d, 0, line1, 140f, 703f, "BELTRANO SILVA")!!
            used = r.fontUsed
            r.changed
        }
        Log.i("LumenTest", "fonte usada: $used; texto: ${text(out1).trim()}")
        assertEquals("fonte original do PDF", used)
        val t1 = text(out1)
        assertTrue("antigo continua no arquivo: $t1", !t1.contains("FULANO"))
        assertTrue(t1.contains("Nome:") && t1.contains("BELTRANO SILVA") && t1.contains("CPF 111.222.333-44"))
        run = PDDocument.load(out1).use { TextEdit.analyze(it, 0, line1, 140f, 703f) }
        Log.i("LumenTest", "depois: $run")
        assertEquals("BELTRANO SILVA", run!!.text)
        assertTrue(run.style.bold && run.style.fontName.contains("Bold"))
        assertEquals(0xCC0000, run.style.color and 0xFFFFFF)
        // "Nome:" continua normal e preto
        val nome = PDDocument.load(out1).use { TextEdit.analyze(it, 0, line1, 80f, 703f) }!!
        assertEquals("Nome:", nome.text)
        assertTrue(!nome.style.bold && nome.style.color and 0xFFFFFF == 0)

        // fonte embutida sem as letras novas (v, ç): usa a substituta de mesmas medidas, mantendo negrito, serifa e cor
        val line2 = RectF(70f, 668f, 300f, 645f)
        val before = PDDocument.load(out1).use { TextEdit.analyze(it, 0, line2, 100f, 655f) }!!
        assertEquals("Contrato original", before.text)
        assertEquals("serif", before.style.family)
        val out2 = File(ctx.cacheDir, "estilos2.pdf")
        Editor.apply(out1, out2, null) { d ->
            val r = TextEdit.replace(d, 0, line2, 100f, 655f, "Contrato revisado — cessão")!!
            used = r.fontUsed
            r.changed
        }
        Log.i("LumenTest", "fonte usada 2: $used; texto: ${text(out2).trim()}")
        assertEquals("LiberationSerif-Bold", used)
        val after = PDDocument.load(out2).use { TextEdit.analyze(it, 0, line2, 100f, 655f) }!!
        Log.i("LumenTest", "depois 2: $after")
        assertEquals("Contrato revisado — cessão", after.text)
        assertTrue(after.style.bold && after.style.family == "serif")
        assertEquals(16f, after.style.size, 0.1f)
        val c = after.style.color
        assertTrue("cor ${Integer.toHexString(c)}", ((c shr 16) and 0xFF) < 10 && ((c shr 8) and 0xFF) in 45..56 && (c and 0xFF) in 200..208)
        val t2 = text(out2)
        assertTrue(!t2.contains("original") && t2.contains("BELTRANO SILVA"))
        // PDFium abre e desenha a página editada
        kotlinx.coroutines.runBlocking {
            val e = PdfEngine(ctx)
            val pdf = e.open(ctx, android.net.Uri.fromFile(out2), null)
            val bmp = e.render(pdf, 0, 600)
            assertTrue(bmp.width > 0)
            e.close(pdf)
        }
        out2.copyTo(File(File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }, "texto_estilos.pdf"), overwrite = true)
    }
}
