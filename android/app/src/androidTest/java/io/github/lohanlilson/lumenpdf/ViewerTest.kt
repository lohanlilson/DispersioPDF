package io.github.lohanlilson.lumenpdf

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.net.Uri
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.doubleClick
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import android.util.Log
import androidx.compose.ui.test.printToLog
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Abre um PDF como se viesse de outro app, procura um texto e dá zoom; salva capturas de tela para conferência. */
@RunWith(AndroidJUnit4::class)
class ViewerTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun makePdf(): File {
        val doc = PdfDocument()
        val title = Paint().apply { color = Color.rgb(109, 60, 240); textSize = 26f; isFakeBoldText = true }
        val body = Paint().apply { color = Color.BLACK; textSize = 11f }
        for (n in 1..3) {
            val page = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, n).create())
            val c = page.canvas
            c.drawText("Lumen PDF - página $n", 50f, 80f, title)
            var y = 120f
            repeat(40) { k ->
                val extra = if (n == 2 && k == 10) " Foro da comarca de Goiânia." else ""
                c.drawText("Cláusula ${k + 1}. Contrato de cessão de créditos entre as partes.$extra", 50f, y, body)
                y += 16f
            }
            doc.finishPage(page)
        }
        val f = File(ctx.filesDir, "recebidos/teste.pdf").apply { parentFile?.mkdirs() }
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private fun shot(name: String) {
        Thread.sleep(700)
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        val bmp: Bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot() ?: return
        val dir = File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }
        File(dir, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    /** Motor de PDF direto (sem tela): renderiza e extrai texto do arquivo de teste. */
    @Test
    fun motorPdf() = runBlocking {
        val f = makePdf()
        val engine = (ctx.applicationContext as LumenApp).engine
        val pdf = engine.open(ctx, Uri.fromFile(f))
        val bmp = engine.render(pdf, 0, 600)
        var ink = 0
        for (y in 0 until bmp.height step 3) for (x in 0 until bmp.width step 3) if (bmp.getPixel(x, y) != android.graphics.Color.WHITE) ink++
        val dir = File(ctx.getExternalFilesDir(null), "capturas").apply { mkdirs() }
        File(dir, "motor_pagina1.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val text = engine.pageText(pdf, 1)
        val hits1 = engine.search(pdf, "Lumen")
        val hits2 = engine.search(pdf, "Goiânia")
        Log.i("LumenTest", "pixels=$ink texto='${text.take(120)}' Lumen=${hits1.size} Goiania=${hits2.size} tamanho=${pdf.sizes}")
        engine.close(pdf)
        assertTrue("página renderizada em branco", ink > 50)
        assertTrue("sem texto extraído", text.contains("Cláusula"))
        assertTrue("busca não achou", hits1.size == 3 && hits2.size == 1)
    }

    @OptIn(ExperimentalTestApi::class)
    @Test
    fun telaInicial() {
        ActivityScenario.launch<MainActivity>(Intent(ctx, MainActivity::class.java)).use {
            try {
                compose.waitUntil(10_000) { compose.onAllNodesWithText("Abrir PDF", substring = true).fetchSemanticsNodes().isNotEmpty() }
            } finally {
                shot("00_inicio")
                runCatching { compose.onRoot().printToLog("LumenTest") }
            }
        }
    }

    @OptIn(ExperimentalTestApi::class)
    @Test
    fun abrirBuscarEZoom() {
        val f = makePdf()
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf")
            .setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use {
            compose.waitUntil(15_000) { compose.onAllNodesWithText("1 / 3").fetchSemanticsNodes().isNotEmpty() }
            Thread.sleep(2500)
            shot("01_documento")
            compose.onNodeWithContentDescription("Localizar").performClick()
            compose.onNode(hasSetTextAction()).performTextInput("Goiânia")
            compose.onNode(hasSetTextAction()).performImeAction()
            try {
                compose.waitUntil(15_000) { compose.onAllNodesWithText("1/1").fetchSemanticsNodes().isNotEmpty() }
            } finally {
                shot("02a_busca")
                runCatching { compose.onRoot().printToLog("LumenTest") }
            }
            compose.waitUntil(5_000) { compose.onAllNodesWithText("2 / 3").fetchSemanticsNodes().isNotEmpty() }
            shot("02_busca")
            compose.onNodeWithContentDescription("Fechar busca").performClick()
            compose.onRoot().performTouchInput { doubleClick(center) }
            Thread.sleep(1500)
            shot("03_zoom")
        }
        // voltou para a lista de recentes com o arquivo
        ActivityScenario.launch<MainActivity>(Intent(ctx, MainActivity::class.java)).use {
            compose.waitUntil(10_000) { compose.onAllNodesWithText("teste.pdf").fetchSemanticsNodes().isNotEmpty() }
            shot("04_recentes")
        }
    }
}
