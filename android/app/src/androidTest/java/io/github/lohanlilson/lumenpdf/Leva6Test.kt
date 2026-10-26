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
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionURI
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.text.PDFTextStripper
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/** Localizar e substituir, links, comentários em FDF, medidas e imagens. */
@RunWith(AndroidJUnit4::class)
class Leva6Test {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val engine by lazy { PdfEngine(ctx) }
    private val out get() = File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }

    private fun contrato(): File {
        val f = File(ctx.cacheDir, "contrato6.pdf")
        PDDocument().use { d ->
            val p = PDPage(PDRectangle.A4); d.addPage(p)
            PDPageContentStream(d, p).use { cs ->
                cs.beginText()
                cs.setFont(PDType1Font.HELVETICA, 12f); cs.setNonStrokingColor(0f, 0f, 0f); cs.newLineAtOffset(72f, 700f)
                cs.showText("Cedente: ")
                cs.setFont(PDType1Font.HELVETICA_BOLD, 12f); cs.setNonStrokingColor(0.8f, 0f, 0f); cs.showText("FULANO DE TAL")
                cs.setFont(PDType1Font.HELVETICA, 12f); cs.setNonStrokingColor(0f, 0f, 0f); cs.showText(" - CPF 111.222.333-44")
                cs.endText()
                cs.beginText()
                cs.setFont(PDType1Font.TIMES_ROMAN, 11f); cs.newLineAtOffset(72f, 670f)
                cs.showText("Assina Fulano de Tal. Site www.exemplo.com.br e contato@exemplo.com")
                cs.endText()
            }
            d.save(f)
        }
        return f
    }

    private fun text(f: File) = PDDocument.load(f).use { PDFTextStripper().getText(it) }

    @Test
    fun localizarESubstituir() {
        TextEdit.assets = ctx.assets
        val src = contrato()
        val dst = File(ctx.cacheDir, "contrato6b.pdf")
        var n = 0
        Editor.apply(src, dst, null) { d ->
            TextEdit.replaceInPage(d, 0, Regex("fulano de tal", RegexOption.IGNORE_CASE), "BELTRANO DA SILVA").let { (ch, k) -> n = k; ch }
        }
        val t = text(dst)
        Log.i("LumenTest", "substituir: $n → ${t.trim().replace("\n", " | ")}")
        assertEquals(2, n)
        assertTrue(t, !t.contains("FULANO", true) && Regex("BELTRANO DA SILVA").findAll(t).count() == 2)
        assertTrue(t.contains("CPF 111.222.333-44") && t.contains("www.exemplo.com.br"))
        // estilo mantido e resto da linha deslocado
        val nome = PDDocument.load(dst).use { TextEdit.analyze(it, 0, RectF(70f, 714f, 500f, 696f), 150f, 703f) }!!
        Log.i("LumenTest", "estilo depois: $nome")
        assertEquals("BELTRANO DA SILVA", nome.text)
        assertTrue(nome.style.bold && (nome.style.color and 0xFFFFFF) == 0xCC0000)
        val cpf = PDDocument.load(dst).use { TextEdit.analyze(it, 0, RectF(70f, 714f, 500f, 696f), nome.rect.right + 30f, 703f) }!!
        assertTrue("sobreposto: ${cpf.rect} x ${nome.rect}", cpf.rect.left >= nome.rect.right - 0.5f)
        runBlocking {
            val pdf = engine.open(ctx, Uri.fromFile(dst))
            assertEquals(2, engine.search(pdf, "BELTRANO").size)
            engine.close(pdf)
        }
        dst.copyTo(File(out, "substituir.pdf"), overwrite = true)
    }

    @Test
    fun linksAutomaticos() = runBlocking {
        val src = contrato()
        val pdf = engine.open(ctx, Uri.fromFile(src))
        val pc = engine.pageChars(pdf, 0)
        val i = pc.text.indexOf("www.exemplo.com.br")
        val j = pc.text.indexOf("contato@exemplo.com")
        val items = listOf("https://www.exemplo.com.br" to pc.selection(i, i + 17).pdfRects, "mailto:contato@exemplo.com" to pc.selection(j, j + 18).pdfRects)
        engine.close(pdf)
        val dst = File(ctx.cacheDir, "links6.pdf")
        Editor.apply(src, dst, null) { d -> MoreEdit.links(d, 0, items) }
        val uris = PDDocument.load(dst).use { d -> d.getPage(0).annotations.filterIsInstance<PDAnnotationLink>().map { (it.action as PDActionURI).uri } }
        Log.i("LumenTest", "links: $uris")
        assertEquals(listOf("https://www.exemplo.com.br", "mailto:contato@exemplo.com"), uris)
        // de novo: não duplica
        val dst2 = File(ctx.cacheDir, "links6b.pdf")
        Editor.apply(dst, dst2, null) { d -> MoreEdit.links(d, 0, items) }
        assertEquals(2, PDDocument.load(dst2).use { it.getPage(0).annotations.count { a -> a is PDAnnotationLink } })
    }

    @Test
    fun comentariosFdf() {
        val src = contrato()
        val withC = File(ctx.cacheDir, "fdf6.pdf")
        Editor.apply(src, withC, null) { d ->
            Editor.note(d, 0, 300f, 600f, "nota para revisão", 0xFFFFD400) +
                Editor.markup(d, 0, listOf(RectF(72f, 712f, 200f, 698f)), Markup.HIGHLIGHT, 0xFFFFD400) +
                Editor.shape(d, 0, "Square", 100f, 500f, 200f, 400f, 0xFFD7373F, 2f)
        }
        val bytes = ByteArrayOutputStream().also { o -> PDDocument.load(withC).use { MoreEdit.exportFdf(it, "contrato.pdf", o) } }.toByteArray()
        Log.i("LumenTest", "FDF: ${bytes.size} bytes")
        assertTrue(String(bytes, Charsets.ISO_8859_1).startsWith("%FDF"))
        val target = File(ctx.cacheDir, "fdf6b.pdf")
        var n = 0
        Editor.apply(src, target, null) { d -> MoreEdit.importFdf(d, bytes.inputStream()).let { (ch, k) -> n = k; ch } }
        val types = PDDocument.load(target).use { d -> d.getPage(0).annotations.map { it.subtype } }
        Log.i("LumenTest", "importados: $n $types")
        assertEquals(3, n)
        assertTrue(types.containsAll(listOf("Text", "Highlight", "Square")))
        // FDF no formato gerado pelo Lumen PDF do computador (e pelo Acrobat)
        val desktop = """%FDF-1.2
1 0 obj
<</FDF<</Annots[2 0 R 3 0 R]/F(teste.pdf)>>>>
endobj
2 0 obj
<</Type/Annot/Subtype/Highlight/C[1 1 0]/F 4/QuadPoints[72 734 200 734 72 718 200 718]/Rect[68 717 204 735]/Contents(destaque)/Page 0>>
endobj
3 0 obj
<</Type/Annot/Subtype/Text/Rect[300 626 316 642]/C[1 1 0]/F 28/Contents(nota do computador)/Name/Note/Page 0>>
endobj
trailer
<</Root 1 0 R>>
%%EOF
""".toByteArray(Charsets.ISO_8859_1)
        val t2 = File(ctx.cacheDir, "fdf6c.pdf")
        Editor.apply(src, t2, null) { d -> MoreEdit.importFdf(d, desktop.inputStream()).let { (ch, k) -> n = k; ch } }
        assertEquals(2, n)
        assertTrue(PDDocument.load(t2).use { d -> d.getPage(0).annotations.any { it.contents == "nota do computador" } })
    }

    @Test
    fun medidas() {
        val src = contrato()
        val dst = File(ctx.cacheDir, "medidas6.pdf")
        val s = MeasureScale.plan(100, "m")
        val len = distPts(100f, 400f, 172f, 400f) * s.factor
        val area = MoreEdit.polygonArea(listOf(100f to 300f, 172f to 300f, 172f to 228f, 100f to 228f)) * s.factor * s.factor
        Log.i("LumenTest", "medidas: ${MoreEdit.fmtMeasure(len, "m")} ${MoreEdit.fmtMeasure(area, "m", true)}")
        assertEquals("2,54 m", MoreEdit.fmtMeasure(len, "m"))
        assertEquals("6,45 m²", MoreEdit.fmtMeasure(area, "m", true))
        Editor.apply(src, dst, null) { d ->
            MoreEdit.measureLine(d, 0, 100f, 400f, 172f, 400f, "2,54 m", 0xFF1473E6) +
                MoreEdit.measureArea(d, 0, listOf(100f to 300f, 172f to 300f, 172f to 228f, 100f to 228f), "6,45 m²", 0xFF1473E6)
        }
        PDDocument.load(dst).use { d ->
            val a = d.getPage(0).annotations
            Log.i("LumenTest", "anotações de medida: ${a.map { it.subtype + ":" + it.contents }}")
            assertTrue(a.any { it.subtype == "Line" && it.contents.contains("2,54 m") })
            assertTrue(a.any { it.subtype == "Polygon" && it.contents.contains("6,45 m²") })
            assertTrue(a.filter { it.subtype == "FreeText" }.all { it.cosObject.containsKey(COSName.AP) })
        }
        // desenhado na tela: há pixels azuis na linha e no rótulo
        runBlocking {
            val pdf = engine.open(ctx, Uri.fromFile(dst))
            val bmp = engine.render(pdf, 0, 595)
            var blue = 0
            for (x in 95..180) for (y in 430..450) { val c = bmp.getPixel(x, y); if (Color.blue(c) > 150 && Color.red(c) < 120) blue++ }
            Log.i("LumenTest", "pixels azuis na linha: $blue")
            assertTrue(blue > 30)
            engine.close(pdf)
        }
        dst.copyTo(File(out, "medidas.pdf"), overwrite = true)
    }

    @Test
    fun imagens() {
        val doc = PdfDocument()
        val pg = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        val bmp = Bitmap.createBitmap(200, 150, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.rgb(200, 30, 30)) }
        pg.canvas.drawText("Logo:", 60f, 80f, Paint().apply { textSize = 14f })
        pg.canvas.drawBitmap(bmp, null, android.graphics.Rect(100, 100, 300, 250), null)
        doc.finishPage(pg)
        val src = File(ctx.cacheDir, "imagens6.pdf")
        src.outputStream().use { doc.writeTo(it) }
        doc.close()
        val imgs = PDDocument.load(src).use { PageImages.list(it, 0) }
        Log.i("LumenTest", "imagens: ${imgs.map { it.rect }}")
        assertEquals(1, imgs.size)
        val moved = File(ctx.cacheDir, "imagens6b.pdf")
        Editor.apply(src, moved, null) { d -> PageImages.move(d, imgs[0], 300f, 400f, 500f, 550f) }
        val after = PDDocument.load(moved).use { PageImages.list(it, 0) }.single().rect
        Log.i("LumenTest", "depois de mover: $after")
        assertTrue("$after", kotlin.math.abs(after.left - 300f) < 0.5f && kotlin.math.abs(after.bottom - 400f) < 0.5f &&
            kotlin.math.abs(after.right - 500f) < 0.5f && kotlin.math.abs(after.top - 550f) < 0.5f)
        val green = Bitmap.createBitmap(40, 40, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.rgb(20, 180, 60)) }
        val replaced = File(ctx.cacheDir, "imagens6c.pdf")
        val img2 = PDDocument.load(moved).use { PageImages.list(it, 0) }.single()
        Editor.apply(moved, replaced, null) { d -> PageImages.replace(d, img2, green) }
        runBlocking {
            val pdf = engine.open(ctx, Uri.fromFile(replaced))
            val b = engine.render(pdf, 0, 595)
            val c = b.getPixel(400, 842 - 475)
            Log.i("LumenTest", "cor no lugar da imagem: ${Integer.toHexString(c)}")
            assertTrue(Color.green(c) > 150 && Color.red(c) < 80)
            engine.close(pdf)
        }
        val deleted = File(ctx.cacheDir, "imagens6d.pdf")
        Editor.apply(replaced, deleted, null) { d -> PageImages.delete(d, PDDocument.load(replaced).use { PageImages.list(it, 0) }.single().let { it }) }
        assertEquals(0, PDDocument.load(deleted).use { PageImages.list(it, 0) }.size)
        assertTrue(text(deleted).contains("Logo"))
    }
}
