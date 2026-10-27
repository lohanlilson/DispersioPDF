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
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Formas, dividir, versões, páginas em branco, endireitar, recortar, extrair imagens e PDF/A. */
@RunWith(AndroidJUnit4::class)
class Leva5Test {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val engine by lazy { PdfEngine(ctx) }
    private val out get() = File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }

    private fun textPdf(name: String, pages: Int = 6): File {
        val doc = PdfDocument()
        val p = Paint().apply { color = Color.BLACK; textSize = 12f }
        for (n in 1..pages) {
            val pg = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, n).create())
            repeat(20) { k -> pg.canvas.drawText("Página $n, linha ${k + 1}: texto do contrato.", 60f, 80f + k * 18f, p) }
            doc.finishPage(pg)
        }
        val f = File(ctx.cacheDir, name)
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    /** Página digitalizada (imagem) com texto inclinado em [deg] graus; deg = null → página em branco (papel levemente cinza). */
    private fun scanPdf(name: String, vararg degs: Float?): File {
        val doc = PdfDocument()
        degs.forEachIndexed { n, deg ->
            val bmp = Bitmap.createBitmap(1240, 1754, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.rgb(246, 246, 244)) }
            if (deg != null) {
                val c = android.graphics.Canvas(bmp)
                c.rotate(deg, 620f, 877f)
                val p = Paint().apply { color = Color.rgb(25, 25, 25); textSize = 30f; isAntiAlias = true }
                repeat(28) { k -> c.drawText("Cláusula ${k + 1}. O cedente transfere ao cessionário os créditos descritos.", 120f, 160f + k * 50f, p) }
            }
            val pg = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, n + 1).create())
            pg.canvas.drawBitmap(bmp, null, android.graphics.Rect(0, 0, 595, 842), null)
            doc.finishPage(pg)
        }
        val f = File(ctx.cacheDir, name)
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    @Test
    fun formas() {
        val src = textPdf("formas.pdf", 1)
        val dst = File(ctx.cacheDir, "formas2.pdf")
        Editor.apply(src, dst, null) { d ->
            Editor.shape(d, 0, "Square", 100f, 700f, 250f, 600f, 0xFFD7373F, 2f) +
                Editor.shape(d, 0, "Circle", 300f, 700f, 450f, 600f, 0xFF1473E6, 2f) +
                Editor.shape(d, 0, "Arrow", 100f, 500f, 300f, 400f, 0xFF2D9D78, 3f)
        }
        val ann = PDDocument.load(dst).use { Editor.annotations(it) }
        Log.i("DispersioTest", "formas: ${ann.map { it.subtype }}")
        assertEquals(listOf("Square", "Circle", "Line"), ann.map { it.subtype })
        // mover a seta desloca os pontos dela
        val moved = File(ctx.cacheDir, "formas3.pdf")
        Editor.apply(dst, moved, null) { d -> Editor.moveAnnot(d, ann[2], 50f, -20f) }
        val line = PDDocument.load(moved).use { (it.getPage(0).annotations[2] as com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLine).line }
        assertEquals(150f, line[0], 0.1f); assertEquals(480f, line[1], 0.1f)
        runBlocking { val pdf = engine.open(ctx, Uri.fromFile(moved)); engine.render(pdf, 0, 600); engine.close(pdf) }
        moved.copyTo(File(out, "formas.pdf"), overwrite = true)
    }

    @Test
    fun dividir() {
        val src = textPdf("dividir.pdf", 7)
        assertEquals(listOf(listOf(0, 1, 2), listOf(3, 4, 5), listOf(6)), Editor.splitGroups(src, null, "every", "3"))
        assertEquals(listOf(listOf(0, 1), listOf(2, 3, 4, 5, 6)), Editor.splitGroups(src, null, "ranges", "1-2; 3-"))
        val bySize = Editor.splitGroups(src, null, "size", "0.004")   // ~4 KB por arquivo
        Log.i("DispersioTest", "dividir por tamanho: $bySize")
        assertTrue(bySize.size >= 2 && bySize.flatten() == (0..6).toList())
        val files = Editor.split(src, null, bySize, File(ctx.cacheDir, "partes").apply { deleteRecursively() }, "dividir")
        assertEquals(bySize.size, files.size)
        assertEquals(7, files.sumOf { f -> PDDocument.load(f).use { it.numberOfPages } })
    }

    @Test
    fun versoesAnteriores() {
        val f = textPdf("versoes.pdf", 1)
        val uri = Uri.fromFile(f).toString()
        Versions.list(ctx, uri).forEach { it.delete() }
        assertTrue(Versions.backup(ctx, uri) != null)
        f.writeBytes(textPdf("outra.pdf", 2).readBytes())
        Versions.backup(ctx, uri)
        val l = Versions.list(ctx, uri)
        assertEquals(2, l.size)
        assertEquals(1, PDDocument.load(l.last()).use { it.numberOfPages })   // a mais antiga é a original
        repeat(12) { Versions.backup(ctx, uri); Thread.sleep(5) }
        assertEquals(Versions.KEEP, Versions.list(ctx, uri).size)
    }

    @Test
    fun brancoEndireitarRecortar(): Unit = runBlocking {
        val f = scanPdf("scan.pdf", 2.5f, null, 0f)
        val pdf = engine.open(ctx, Uri.fromFile(f))
        val blank = (0 until 3).filter { PageAnalysis.isBlank(engine, pdf, it, false) }
        Log.i("DispersioTest", "em branco: $blank")
        assertEquals(listOf(1), blank)
        val a0 = PageAnalysis.skew(engine, pdf, 0)
        val a2 = PageAnalysis.skew(engine, pdf, 2)
        Log.i("DispersioTest", "inclinação: $a0 e $a2")
        assertTrue("inclinação $a0", kotlin.math.abs(a0 - 2.5) < 0.4)
        assertTrue(kotlin.math.abs(a2) < 0.3)
        val box = PageAnalysis.contentBox(engine, pdf, 2)!!
        Log.i("DispersioTest", "conteúdo: $box")
        assertTrue("$box", box.l > 0.05f && box.r < 0.95f && box.t > 0.05f && box.b < 1.35f)
        val pts = engine.pdfPoints(pdf, 2, listOf(box.l to box.t, box.r to box.b))
        engine.close(pdf)
        val fixed = File(ctx.cacheDir, "scan2.pdf")
        Editor.apply(f, fixed, null) { d -> PageEdit.rotateContent(d, 0, a0) }
        val pdf2 = engine.open(ctx, Uri.fromFile(fixed))
        val after = PageAnalysis.skew(engine, pdf2, 0)
        engine.close(pdf2)
        Log.i("DispersioTest", "depois de endireitar: $after")
        assertTrue("ainda torta: $after", kotlin.math.abs(after) < 0.3)
        val cropped = File(ctx.cacheDir, "scan3.pdf")
        Editor.applyFull(fixed, cropped, null) { d, _ -> PageEdit.crop(d, 2, pts[0], pts[1], pts[2], pts[3]) }
        val cb = PDDocument.load(cropped).use { it.getPage(2).cropBox }
        Log.i("DispersioTest", "recorte: $cb")
        assertTrue(cb.width < 560 && cb.height < 800)
        cropped.copyTo(File(out, "scan_endireitado.pdf"), overwrite = true)
        Unit
    }

    @Test
    fun extrairImagens() {
        val f = scanPdf("imagens.pdf", 0f, 0f)
        val n = PageEdit.extractImages(ctx, f, null, "teste_extrair")
        Log.i("DispersioTest", "imagens extraídas: $n")
        assertEquals(2, n)
    }

    @Test
    fun pdfA() {
        // fontes padrão não embutidas, comentário, campo de formulário e imagem
        val src = File(ctx.cacheDir, "pdfa_origem.pdf")
        PDDocument().use { d ->
            val p = PDPage(PDRectangle.A4); d.addPage(p)
            PDPageContentStream(d, p).use { cs ->
                cs.beginText(); cs.setFont(PDType1Font.HELVETICA, 12f); cs.newLineAtOffset(72f, 760f); cs.showText("Contrato de cessão (Helvetica)"); cs.endText()
                cs.beginText(); cs.setFont(PDType1Font.TIMES_BOLD, 12f); cs.newLineAtOffset(72f, 740f); cs.showText("Times Bold"); cs.endText()
                cs.beginText(); cs.setFont(PDType1Font.COURIER, 12f); cs.newLineAtOffset(72f, 720f); cs.showText("Courier"); cs.endText()
            }
            d.save(src)
        }
        val withNote = File(ctx.cacheDir, "pdfa_origem2.pdf")
        Editor.apply(src, withNote, null) { d -> Editor.note(d, 0, 300f, 600f, "nota", 0xFFFFD400) + Editor.markup(d, 0, listOf(RectF(72f, 775f, 260f, 757f)), Markup.HIGHLIGHT, 0xFFFFD400) }
        val dst = File(out, "teste_pdfa.pdf")
        val problems = PdfA.convert(ctx, withNote, null, dst, "Contrato teste")
        Log.i("DispersioTest", "PDF/A avisos: $problems")
        assertTrue(problems.isEmpty())
        PDDocument.load(dst).use { d ->
            val xmp = d.documentCatalog.metadata.exportXMPMetadata().use { String(it.readBytes()) }
            assertTrue(xmp.contains("<pdfaid:part>2</pdfaid:part>"))
            assertEquals(1, d.documentCatalog.outputIntents.size)
        }
        // texto visível e pesquisável depois de embutir as fontes
        runBlocking {
            val pdf = engine.open(ctx, Uri.fromFile(dst))
            assertEquals(1, engine.search(pdf, "Courier").size)
            engine.close(pdf)
        }
        // a versão escaneada também (será validada pelo veraPDF no GitHub)
        PdfA.convert(ctx, scanPdf("pdfa_scan.pdf", 0f), null, File(out, "teste_pdfa_scan.pdf"), "Digitalização")
    }
}
