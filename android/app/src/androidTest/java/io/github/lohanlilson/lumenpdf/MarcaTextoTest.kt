package io.github.lohanlilson.lumenpdf

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.util.Log
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipe
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationTextMarkup
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Marca-texto: arrastar destaca na hora; tocar numa palavra destaca a palavra; a seleção é rápida mesmo em páginas cheias. */
@RunWith(AndroidJUnit4::class)
class MarcaTextoTest {
    @get:Rule
    val compose = createEmptyComposeRule()
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun makePdf(): File {
        val doc = PdfDocument()
        val title = Paint().apply { color = Color.BLACK; textSize = 26f }
        val body = Paint().apply { color = Color.BLACK; textSize = 9f }
        for (n in 1..2) {
            val page = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, n).create())
            val c = page.canvas
            c.drawText("Contrato de cessão $n", 50f, 80f, title)
            var y = 120f
            repeat(70) { k ->   // página cheia: ~7 mil caracteres
                c.drawText("Cláusula ${k + 1}. O cedente transfere ao cessionário os créditos descritos no anexo, com todos os direitos.", 40f, y, body)
                y += 10.5f
            }
            doc.finishPage(page)
        }
        val f = File(ctx.filesDir, "recebidos/marca.pdf").apply { parentFile?.mkdirs() }
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private fun shot(name: String) {
        Thread.sleep(500)
        val bmp: Bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot() ?: return
        val dir = File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }
        File(dir, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 90, it) }
    }

    @org.junit.After
    fun limparRecentes() {
        // não deixa este documento nos recentes (a tela inicial dos outros testes espera a lista vazia)
        ctx.getSharedPreferences("recentes", 0).edit().clear().commit()
    }

    @Test
    fun marcaTexto() {
        val f = makePdf()
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            compose.waitUntil(15_000) { compose.onAllNodesWithText("1 / 2").fetchSemanticsNodes().isNotEmpty() }
            Thread.sleep(1500)
            val d = vm.doc!!

            // seleção em memória: rápida mesmo com milhares de caracteres
            val pc = runBlocking { vm.engine.pageChars(d.pdf, 0) }
            val t0 = System.nanoTime()
            repeat(100) { k -> pc.selection(pc.charAt(0.1f, 0.15f, strict = false), pc.charAt(0.2f + k * 0.006f, 0.6f, strict = false)) }
            val ms = (System.nanoTime() - t0) / 1e6 / 100
            Log.i("LumenTest", "caracteres=${pc.size} seleção média=${"%.2f".format(ms)} ms")
            assertTrue("seleção lenta: $ms ms", ms < 25)   // antes da otimização eram centenas de ms

            compose.onNodeWithContentDescription("Editar").performClick()
            compose.onNodeWithContentDescription("Marca-texto").performScrollTo().performClick()
            compose.waitForIdle()
            // arrasta sobre o título (linha de base y=80, letras de 26 pt)
            compose.onNodeWithContentDescription("Página 1").performTouchInput {
                val y = height * 71f / 842f
                swipe(Offset(width * 0.1f, y), Offset(width * 0.5f, y), 500)
            }
            val tEnd = System.currentTimeMillis()
            compose.waitUntil(1_500) { d.pendingMarks.isNotEmpty() || d.dirty }
            Log.i("LumenTest", "destaque visível em ${System.currentTimeMillis() - tEnd} ms (pendentes=${d.pendingMarks.size})")
            shot("20_marca_texto")
            compose.waitUntil(15_000) { d.dirty && !d.busy }
            // toque numa palavra com o marca-texto: destaca a palavra
            compose.onNodeWithContentDescription("Página 1").performTouchInput {
                click(Offset(width * 0.11f, height * 117f / 842f))
            }
            compose.mainClock.advanceTimeBy(1000)
            compose.waitUntil(15_000) { d.pendingMarks.isEmpty() && !d.busy && d.annots.size >= 2 }
            shot("21_marca_palavra")
            compose.onNodeWithContentDescription("Salvar").performClick()
            compose.onNodeWithText("Salvar").performClick()
            Thread.sleep(2500)
        }

        PDDocument.load(f).use { doc ->
            val marks = doc.getPage(0).annotations.filterIsInstance<PDAnnotationTextMarkup>().filter { it.subtype == "Highlight" }
            val strip = com.tom_roush.pdfbox.text.PDFTextStripperByArea()
            val texts = marks.map { m ->
                val r = m.rectangle
                strip.addRegion("r", android.graphics.RectF(r.lowerLeftX, 842 - r.upperRightY, r.upperRightX, 842 - r.lowerLeftY))
                strip.extractRegions(doc.getPage(0))
                strip.getTextForRegion("r").trim()
            }
            Log.i("LumenTest", "destaques: $texts")
            assertEquals(2, marks.size)
            assertTrue("$texts", texts.any { it.startsWith("Contrato de") })
            assertTrue(texts.any { it.startsWith("Cláusula") && it.length < 14 })
        }
    }
}
