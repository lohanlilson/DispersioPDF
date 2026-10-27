package io.github.lohanlilson.lumenpdf

import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.net.Uri
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.pdmodel.PDDocument
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Salvamento automático: grava sozinho depois de editar, ao sair do app e ao fechar; desligado, volta a perguntar. */
@RunWith(AndroidJUnit4::class)
class AutosalvarTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun makePdf(name: String): File {
        val doc = PdfDocument()
        val p = Paint().apply { color = Color.BLACK; textSize = 14f }
        val page = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        repeat(8) { k -> page.canvas.drawText("Linha ${k + 1} do contrato de cessão de créditos.", 50f, 80f + k * 30f, p) }
        doc.finishPage(page)
        val f = File(ctx.filesDir, "recebidos/$name").apply { parentFile?.mkdirs(); delete() }
        f.outputStream().use { doc.writeTo(it) }
        doc.close()
        return f
    }

    private fun highlights(f: File) = PDDocument.load(f).use { d -> d.getPage(0).annotations.count { it.subtype == "Highlight" } }

    private fun waitFor(ms: Long, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(50) }
        return cond()
    }

    private fun mark(vm: AppVm, d: ViewerDoc, line: Int) {
        val y = (80f + line * 30f - 5f) / 842f
        val sel = runBlocking { vm.engine.pageChars(d.pdf, 0) }.let { it.wordSelection(it.charAt(0.1f, y, false), it.charAt(0.4f, y, false)) }
        InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.markup(d, sel, Markup.HIGHLIGHT, 0xFFFFD400) }
        assertTrue(waitFor(15_000) { d.dirty && !d.busy && d.pendingMarks.isEmpty() })
    }

    @After
    fun limpar() {
        AppVm.AUTOSAVE_MS = 5000L
        ctx.getSharedPreferences("recentes", 0).edit().clear().commit()
    }

    @Test
    fun salvaSozinho() {
        AppVm.AUTOSAVE_MS = 1500
        val f = makePdf("auto.pdf")
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            assertTrue(waitFor(15_000) { vm.doc != null && !vm.loading })
            val d = vm.doc!!
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.prefs.autosave = true }
            Thread.sleep(1500)

            // 1. grava sozinho pouco depois da alteração; só uma versão anterior na sessão
            mark(vm, d, 0)
            assertTrue("salvou sozinho", waitFor(10_000) { !d.dirty })
            assertEquals(1, highlights(f))
            mark(vm, d, 2)
            assertTrue(waitFor(10_000) { !d.dirty })
            assertEquals(2, highlights(f))
            val vs = Versions.list(ctx, d.uri)
            assertEquals(1, vs.size)
            assertEquals("a versão guardada é a de antes das alterações", 0, highlights(vs[0]))

            // 2. desligado: não grava e pergunta ao fechar
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.prefs.autosave = false }
            mark(vm, d, 4)
            Thread.sleep(3500)
            assertTrue(d.dirty)
            assertEquals(2, highlights(f))
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.requestClose() }
            Thread.sleep(300)
            assertTrue("pergunta se quer salvar", vm.confirmClose)
            assertEquals(2, highlights(f))

            // 3. ligado de novo: fechar grava sem perguntar
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.confirmClose = false; vm.prefs.autosave = true }
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.requestClose() }
            assertTrue("fechou", waitFor(10_000) { vm.doc == null })
            assertFalse(vm.confirmClose)
            assertEquals(3, highlights(f))
        }
    }

    @Test
    fun salvaAoSairDoApp() {
        AppVm.AUTOSAVE_MS = 600_000   // o tempo não chega: quem grava é a saída do app
        val f = makePdf("sair.pdf")
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            assertTrue(waitFor(15_000) { vm.doc != null && !vm.loading })
            val d = vm.doc!!
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.prefs.autosave = true }
            Thread.sleep(1500)
            mark(vm, d, 1)
            Thread.sleep(1000)
            assertTrue(d.dirty)
            sc.moveToState(Lifecycle.State.CREATED)    // vai para segundo plano (onStop)
            assertTrue("gravou ao sair", waitFor(10_000) { !d.dirty })
            assertEquals(1, highlights(f))
        }
    }
}
