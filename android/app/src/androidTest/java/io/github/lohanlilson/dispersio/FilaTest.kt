package io.github.lohanlilson.dispersio

import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** "Fila do Dispersio" no Compartilhar: guarda na fila (não abre) e junta na ordem. */
@RunWith(AndroidJUnit4::class)
class FilaTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun pdf(name: String, pages: Int): File {
        PDFBoxResourceLoader.init(ctx)
        val f = File(ctx.cacheDir, name)
        PDDocument().use { d -> repeat(pages) { d.addPage(PDPage()) }; d.save(f) }
        return f
    }

    private fun waitFor(ms: Long, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(100) }
        return cond()
    }

    @Test
    fun compartilharParaAFila() {
        Fila.list(ctx).forEach { it.delete() }
        val a = pdf("a.pdf", 1); val b = pdf("b.pdf", 2)
        val i = Intent(Intent.ACTION_SEND_MULTIPLE).setComponent(ComponentName(ctx.packageName, "io.github.lohanlilson.dispersio.Fila"))
            .setType("application/pdf")
            .putParcelableArrayListExtra(Intent.EXTRA_STREAM, arrayListOf(Uri.fromFile(a), Uri.fromFile(b)))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ActivityScenario.launch<MainActivity>(i).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            assertTrue("entrou na fila", waitFor(10_000) { vm.queueCount == 2 })
            assertTrue("não abre o documento", vm.doc == null)
            assertTrue("mostra a fila", vm.showQueue)
            val files = Fila.list(ctx)
            assertEquals(listOf("a.pdf", "b.pdf"), files.map { it.name })
            Fila.saveOrder(ctx, files.reversed())
            val out = Fila.merge(ctx, Fila.list(ctx))
            PDDocument.load(out).use { assertEquals(3, it.numberOfPages) }
            Fila.list(ctx).forEach { it.delete() }
        }
    }
}
