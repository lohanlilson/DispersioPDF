package io.github.lohanlilson.dispersio

import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.util.Log
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Artigo de duas colunas: ordem de leitura, cabeçalho/rodapé, referências e sobrescritos fora da tradução;
 *  tradução no próprio documento (Original/Tradução). */
@RunWith(AndroidJUnit4::class)
class TraducaoArtigoTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun article(): File {
        val doc = PdfDocument()
        val p = Paint().apply { color = Color.BLACK; textSize = 10f }
        val small = Paint().apply { color = Color.BLACK; textSize = 6f }
        val bold = Paint().apply { color = Color.BLACK; textSize = 16f; typeface = Typeface.DEFAULT_BOLD }
        for (n in 1..2) {
            val pg = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, n).create())
            val c = pg.canvas
            c.drawText("Journal of Veterinary Forensics 2021; 12: 34-40", 50f, 30f, Paint().apply { textSize = 8f })
            c.drawText("$n", 295f, 825f, Paint().apply { textSize = 8f })
            if (n == 1) {
                c.drawText("Animal cruelty and family violence", 50f, 70f, bold)
                listOf("Dogs with chronic lesions were more", "frequent in rural areas.").forEachIndexed { k, s -> c.drawText(s, 50f, 100f + k * 13, p) }
                listOf("Animal cruelty is a significant indicator", "of interpersonal violence [12, 15].", "Veterinarians should document injuries",
                    "carefully (Arkow et al., 2011). In this study", "we examined the records of 120 dogs that were")
                    .forEachIndexed { k, s -> c.drawText(s, 50f, 150f + k * 13, p) }
                listOf("brought to the clinic between 2015 and", "2019. Most animals presented fractures.").forEachIndexed { k, s -> c.drawText(s, 315f, 100f + k * 13, p) }
                c.drawText("Neglect was common", 315f, 150f, p)
                c.drawText("3", 315f + p.measureText("Neglect was common"), 146f, small)
                c.drawText(" in all regions studied.", 315f + p.measureText("Neglect was common") + 4, 150f, p)
            } else {
                c.drawText("Conclusions: cruelty must be reported to the authorities.", 50f, 100f, p)
                c.drawText("References", 50f, 150f, Paint().apply { textSize = 12f; typeface = Typeface.DEFAULT_BOLD })
                c.drawText("1. Arkow P. The relationships between animal abuse and other forms of", 50f, 170f, Paint().apply { textSize = 9f })
                c.drawText("family violence. Family Violence Bulletin. 1996;12:29-34.", 50f, 182f, Paint().apply { textSize = 9f })
            }
            doc.finishPage(pg)
        }
        val f = File(ctx.filesDir, "recebidos/artigo2col.pdf").apply { parentFile?.mkdirs(); delete() }
        f.outputStream().use { doc.writeTo(it) }; doc.close()
        return f
    }

    @After
    fun limpar() { ctx.getSharedPreferences("recentes", 0).edit().clear().commit() }

    @Test
    fun analiseETraducao() {
        PDFBoxResourceLoader.init(ctx)
        val f = article()
        val per = PDDocument.load(f).use { DocAnalysis.analyze(it, listOf(0, 1)) }
        per.values.flatten().forEach { Log.i("DispersioTest", "bloco p${it.page} keep=${it.keep} cont=${it.cont} ${it.why} | ${it.shown.take(60)}") }
        val p0 = per[0]!!.map { it.shown }
        val iRural = p0.indexOfFirst { it.startsWith("Dogs with chronic") }
        val iLeft = p0.indexOfFirst { it.startsWith("Animal cruelty is") }
        val iRight = p0.indexOfFirst { it.startsWith("brought to the clinic") }
        assertTrue("$p0", iRural in 0 until iLeft && iLeft < iRight)
        assertTrue(per[0]!!.first { it.shown.startsWith("brought") }.cont)
        assertTrue(per.values.flatten().filter { it.shown.startsWith("Journal of") || it.shown == "1" || it.shown == "2" }.all { it.keep })
        assertTrue(per[1]!!.first { it.shown.startsWith("1. Arkow") }.keep)
        assertTrue(per[0]!!.any { "³" in it.shown })

        val ok = runBlocking { withTimeoutOrNull(120_000) { runCatching { Traducao.download("en", "pt") }.isSuccess } } == true
        assumeTrue("sem acesso ao serviço de modelos do Google neste emulador", ok)
        val res = HashMap<Int, List<Pair<TBlock, String?>>>()
        PDDocument.load(f).use { pd -> runBlocking { DocTranslator.run(pd, listOf(0, 1), "en", "pt", { p, items -> res[p] = items }) } }
        val left = res[0]!!.first { it.first.shown.startsWith("Animal cruelty is") }.second!!
        Log.i("DispersioTest", "tradução: $left")
        assertTrue(left, "[12, 15]" in left && "(Arkow et al., 2011)" in left)
        assertTrue(res[1]!!.first { it.first.shown.startsWith("1. Arkow") }.second == null)
        val out = File(ctx.cacheDir, "traduzido-teste.pdf")
        TranslatedPdf.build(ctx, f, null, out, res)
        val txt = PDDocument.load(out).use { PDFTextStripper().getText(it) }
        assertTrue(txt.take(400), txt.contains("crueldade", true) && txt.contains("Journal of Veterinary Forensics"))

        // no app: traduzir mostra a cópia traduzida no lugar; "Original" volta
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            var end = System.currentTimeMillis() + 20_000
            while (vm.doc?.language == null && System.currentTimeMillis() < end) Thread.sleep(100)
            val d = vm.doc!!
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.startTranslation(d, "en", "pt") }
            end = System.currentTimeMillis() + 120_000
            while ((vm.tr?.running != false || vm.doc?.readOnly != true) && System.currentTimeMillis() < end) Thread.sleep(200)
            val st = vm.tr!!
            assertEquals(2, st.pages.size)
            assertTrue("mostra a tradução", vm.doc === st.translated && vm.doc!!.readOnly)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.showTranslated(false) }
            assertTrue(vm.doc === d && !d.readOnly)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.showTranslated(true) }
            assertTrue(vm.doc === st.translated)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.requestClose() }
            assertTrue("voltar sai da tradução para o original", vm.doc === d)
            assertFalse(d.dirty)
        }
    }
}
