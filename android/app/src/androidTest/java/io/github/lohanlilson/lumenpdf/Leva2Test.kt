package io.github.lohanlilson.lumenpdf

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Paint
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
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipInputStream

/** OCR, conversões, detecção de campos, comparação e tarja. */
@RunWith(AndroidJUnit4::class)
class Leva2Test {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val dir get() = File(ctx.cacheDir, "leva2").apply { mkdirs() }
    private val engine get() = (ctx.applicationContext as LumenApp).engine

    private fun pdf(name: String, lines: List<String>, asImage: Boolean = false, draw: (android.graphics.Canvas) -> Unit = {}): File {
        val doc = PdfDocument()
        val p = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        val paint = Paint().apply { color = Color.BLACK; textSize = if (asImage) 22f else 14f; isAntiAlias = true }
        if (asImage) {
            // página "escaneada": o texto vira imagem
            val bmp = Bitmap.createBitmap(1190, 1684, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.WHITE) }
            val c = android.graphics.Canvas(bmp)
            paint.textSize = 44f
            lines.forEachIndexed { i, l -> c.drawText(l, 100f, 200f + i * 80f, paint) }
            p.canvas.drawBitmap(bmp, null, android.graphics.Rect(0, 0, 595, 842), null)
        } else lines.forEachIndexed { i, l -> p.canvas.drawText(l, 60f, 100f + i * 26f, paint) }
        draw(p.canvas)
        doc.finishPage(p)
        val f = File(dir, name)
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    @Test
    fun ocrDePaginaEscaneada() = runBlocking {
        val f = pdf("scan.pdf", listOf("CONTRATO DE CESSAO", "Valor total 10000 reais"), asImage = true)
        val pdf = engine.open(ctx, Uri.fromFile(f))
        val words = Ocr.page(engine, pdf, 0)
        Log.i("LumenTest", "OCR: ${words.map { it.first }}")
        val sz = pdf.sizes[0]
        val pts = engine.pdfPoints(pdf, 0, words.map { it.second.l to it.second.b })
        val ow = words.mapIndexed { i, (t, r) -> Editor.OcrWord(t, pts[i * 2], pts[i * 2 + 1], (r.r - r.l) * sz.w, (r.b - r.t) * sz.w) }
        engine.close(pdf)
        val out = File(dir, "scan_ocr.pdf")
        Editor.apply(f, out, null) { d -> Editor.ocrLayer(d, 0, ow) }
        val text = PDDocument.load(out).use { PDFTextStripper().getText(it) }
        assertTrue("OCR não encontrou o texto: $text", text.contains("CONTRATO") && text.contains("Valor"))
        val pdf2 = engine.open(ctx, Uri.fromFile(out))
        assertEquals(1, engine.search(pdf2, "CONTRATO").size)
        engine.close(pdf2)
    }

    @Test
    fun wordExcel() {
        val pages = listOf("Nome  Valor\nJoão  1.234,56\nMaria  R$ 10,00", "Página 2")
        val docx = ByteArrayOutputStream().also { Convert.docx(pages, it) }.toByteArray()
        val xlsx = ByteArrayOutputStream().also { Convert.xlsx(pages, it) }.toByteArray()
        fun entries(b: ByteArray) = ZipInputStream(b.inputStream()).use { z -> generateSequence { z.nextEntry }.map { it.name }.toList() }
        assertTrue(entries(docx).contains("word/document.xml"))
        assertTrue(entries(xlsx).containsAll(listOf("xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml")))
        val sheet = ZipInputStream(xlsx.inputStream()).use { z ->
            generateSequence { z.nextEntry }.first { it.name == "xl/worksheets/sheet1.xml" }; z.readBytes().toString(Charsets.UTF_8)
        }
        assertTrue(sheet.contains("<v>1234.56</v>") && sheet.contains("<v>10.0</v>") && sheet.contains("João"))
    }

    @Test
    fun detectarCampos() = runBlocking {
        val f = pdf("form.pdf", listOf("Nome completo: ________________________________", "CPF: ............................",
            "Aceita?  ( ) Sim   ( ) Não")) { c ->
            val line = Paint().apply { color = Color.BLACK; strokeWidth = 1f }
            c.drawLine(70f, 520f, 260f, 520f, line)
            c.drawText("Assinatura do Cedente", 100f, 536f, Paint().apply { color = Color.BLACK; textSize = 11f })
        }
        val pdf = engine.open(ctx, Uri.fromFile(f))
        val chars = engine.chars(pdf, 0)
        engine.close(pdf)
        val out = File(dir, "form_campos.pdf")
        var count: Map<String, Int> = emptyMap()
        Editor.applyFull(f, out, null) { d, _ -> count = FieldDetect.create(d, mapOf(0 to FieldDetect.detect(d, 0, chars))) }
        val names = PDDocument.load(out).use { d -> Editor.fields(d).map { it.label + "/" + it.kind } }
        Log.i("LumenTest", "campos: $count $names")
        assertTrue("campos: $count $names", (count["text"] ?: 0) >= 2 && (count["check"] ?: 0) == 2 && (count["signature"] ?: 0) == 1)
        // preencher: texto e caixa de seleção
        val filled = File(dir, "form_preenchido.pdf")
        Editor.apply(out, filled, null) { d ->
            val fs = Editor.fields(d)
            Editor.setField(d, fs.first { it.kind == FormField.Kind.TEXT }.name, "Lohan") +
                Editor.setField(d, fs.first { it.kind == FormField.Kind.CHECK }.name, "on")
        }
        val vals = PDDocument.load(filled).use { d -> Editor.fields(d).map { it.value } }
        assertTrue("valores: $vals", "Lohan" in vals && vals.any { it == "Yes" })
    }

    @Test
    fun compararETarjar() = runBlocking {
        val a = pdf("v1.pdf", listOf("O preço é R$ 10.000,00 à vista.", "CPF do cedente: 123.456.789-00"))
        val b = pdf("v2.pdf", listOf("O preço é R$ 12.500,00 à vista.", "CPF do cedente: 123.456.789-00", "Cláusula nova."))
        val pa = engine.open(ctx, Uri.fromFile(a)); val pb = engine.open(ctx, Uri.fromFile(b))
        val ch = Compare.changes(Compare.words(engine, pa), Compare.words(engine, pb))
        Log.i("LumenTest", "comparação: ${ch.map { it.kind + ":" + it.textA + "->" + it.textB }}")
        assertEquals(listOf("alterado", "inserido"), ch.map { it.kind })
        assertTrue(ch[0].rectsA.isNotEmpty() && ch[0].rectsB.isNotEmpty())
        // tarja do CPF: some do arquivo
        val chars = engine.chars(pa, 0)
        val text = String(chars.map { it.first }.toCharArray())
        val m = Regex("\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}").find(text)!!
        val boxes = chars.subList(m.range.first, m.range.last + 1).mapNotNull { it.second }
        val r = android.graphics.RectF(boxes.minOf { it.left }, boxes.maxOf { it.top }, boxes.maxOf { it.right }, boxes.minOf { it.bottom })
        val fr = engine.fracOf(pa, 0, r)
        val w = 1654
        val bmp = engine.render(pa, 0, w).copy(Bitmap.Config.ARGB_8888, true)
        android.graphics.Canvas(bmp).drawRect(fr.l * w, fr.t * w, fr.r * w, fr.b * w, Paint().apply { color = Color.BLACK })
        engine.close(pa); engine.close(pb)
        val out = File(dir, "tarjado.pdf")
        Editor.applyFull(a, out, null) { d, _ -> Editor.redactPage(d, 0, bmp, listOf(r)) }
        val after = PDDocument.load(out).use { PDFTextStripper().getText(it) }
        assertTrue("o CPF ainda está no arquivo: $after", !after.contains("123.456.789-00"))
    }
}
