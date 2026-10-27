package io.github.lohanlilson.dispersio

import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.util.Log
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Documento em inglês: o app percebe o idioma e traduz para português no próprio aparelho. */
@RunWith(AndroidJUnit4::class)
class TraducaoTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    @After
    fun limpar() { ctx.getSharedPreferences("recentes", 0).edit().clear().commit() }

    @Test
    fun detectaETraduz() {
        val doc = PdfDocument()
        val pg = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        val p = Paint().apply { color = Color.BLACK; textSize = 12f }
        listOf("Animal cruelty is a significant indicator of interpersonal violence.", "Veterinarians should document injuries carefully",
            "and report suspected cases to the authorities. The results of this study", "show that most cases involved dogs that were kept",
            "in poor conditions for a long time.").forEachIndexed { k, s -> pg.canvas.drawText(s, 50f, 80f + k * 18f, p) }
        doc.finishPage(pg)
        val f = File(ctx.filesDir, "recebidos/artigo_en.pdf").apply { parentFile?.mkdirs(); delete() }
        f.outputStream().use { doc.writeTo(it) }; doc.close()
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            val end = System.currentTimeMillis() + 20_000
            while ((vm.doc?.language == null) && System.currentTimeMillis() < end) Thread.sleep(100)
            val d = vm.doc!!
            assertEquals("en", d.language)
            // tradução no aparelho (precisa baixar o pacote de português uma vez)
            val ok = runBlocking { withTimeoutOrNull(120_000) { runCatching { Traducao.download("en", "pt") }.isSuccess } } == true
            Log.i("DispersioTest", "pacote de tradução baixado: $ok")
            assumeTrue("sem acesso ao serviço de modelos do Google neste emulador", ok)
            val t = runBlocking { Traducao.translate("en", "pt", reflow(vm.engine.pageText(d.pdf, 0)).joinToString(" ")) }
            Log.i("DispersioTest", "tradução: $t")
            assertTrue(t, t.lowercase().contains("crueldade") && t.lowercase().contains("cães"))
        }
    }
}
