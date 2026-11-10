package io.github.lohanlilson.dispersio

import android.content.Intent
import android.net.Uri
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDDocumentNameDictionary
import com.tom_roush.pdfbox.pdmodel.PDEmbeddedFilesNameTreeNode
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.common.filespecification.PDComplexFileSpecification
import com.tom_roush.pdfbox.pdmodel.common.filespecification.PDEmbeddedFile
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionJavaScript
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionURI
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** PDF de golpe: faixa de alerta e “Remover o perigo”. */
@RunWith(AndroidJUnit4::class)
class SegurancaTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun makePdf(): File {
        PDFBoxResourceLoader.init(ctx)
        val f = File(ctx.filesDir, "recebidos/golpe.pdf").apply { parentFile?.mkdirs(); delete() }
        PDDocument().use { doc ->
            val page = PDPage(PDRectangle.A4); doc.addPage(page)
            PDPageContentStream(doc, page).use { cs ->
                cs.beginText(); cs.setFont(PDType1Font.HELVETICA, 12f); cs.newLineAtOffset(60f, 780f)
                cs.showText("Documento protegido - clique para visualizar"); cs.endText()
            }
            page.annotations.add(PDAnnotationLink().apply {
                rectangle = PDRectangle(60f, 100f, 480f, 600f)
                action = PDActionURI().apply { uri = "https://office365-login.xyz/a" }
            })
            doc.documentCatalog.openAction = PDActionJavaScript("app.alert('oi')")
            val fs = PDComplexFileSpecification().apply {
                file = "nota_fiscal.exe"
                embeddedFile = PDEmbeddedFile(doc, "MZ fake".byteInputStream())
            }
            val tree = PDEmbeddedFilesNameTreeNode().apply { names = mapOf("nota_fiscal.exe" to fs) }
            doc.documentCatalog.names = PDDocumentNameDictionary(doc.documentCatalog).apply { embeddedFiles = tree }
            doc.save(f)
        }
        return f
    }

    private fun waitFor(ms: Long, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(100) }
        return cond()
    }

    @After
    fun limpar() { ctx.getSharedPreferences("recentes", 0).edit().clear().commit() }

    @Test
    fun faixaDeGolpeERemoverPerigo() {
        AppVm.AUTOSAVE_MS = 600_000
        val f = makePdf()
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.fromFile(f), "application/pdf").setClass(ctx, MainActivity::class.java)
        ActivityScenario.launch<MainActivity>(intent).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            assertTrue(waitFor(15_000) { vm.doc != null && !vm.loading })
            val d = vm.doc!!
            assertTrue("procurou golpes", waitFor(30_000) { d.threats.isNotEmpty() })
            val titles = d.threats.map { it.title }
            assertTrue(titles.toString(), titles.any { "JavaScript" in it })
            assertTrue(titles.toString(), titles.any { "programa anexado" in it })
            assertTrue(titles.toString(), titles.any { "botão" in it })
            assertTrue(d.threats.first().level == Seguranca.DANGER)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.removeDanger(d) }
            assertTrue(waitFor(20_000) { !d.busy && d.dirty && d.threats.none { "JavaScript" in it.title } })
            PDDocument.load(d.work!!).use { pd ->
                val left = Seguranca.scanDoc(pd).map { it.title }
                assertTrue(left.toString(), left.none { "JavaScript" in it || "anexado" in it })
                assertTrue(pd.documentCatalog.cosObject.getDictionaryObject(COSName.OPEN_ACTION) == null)
            }
        }
    }
}
