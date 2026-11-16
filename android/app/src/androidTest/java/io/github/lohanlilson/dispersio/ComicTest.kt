package io.github.lohanlilson.dispersio

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Leitor de quadrinhos: abre .cbz em ordem natural, escolhe o modo, guarda a página e passa de capítulo. */
@RunWith(AndroidJUnit4::class)
class ComicTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun jpg(w: Int, h: Int): ByteArray {
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.rgb(90, 120, 200)) }
        return ByteArrayOutputStream().also { b.compress(Bitmap.CompressFormat.JPEG, 80, it) }.toByteArray()
    }

    private fun cbz(name: String, n: Int, w: Int, h: Int, manga: Boolean = false): File {
        val f = File(ctx.cacheDir, name)
        ZipOutputStream(f.outputStream()).use { z ->
            for (i in listOf(10, 2, 1).filter { it <= n } + (3..n).filter { it != 10 }) {
                z.putNextEntry(ZipEntry("p$i.jpg")); z.write(jpg(w, h)); z.closeEntry()
            }
            if (manga) { z.putNextEntry(ZipEntry("ComicInfo.xml")); z.write("<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>".toByteArray()); z.closeEntry() }
        }
        return f
    }

    private fun waitFor(ms: Long, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(100) }
        return cond()
    }

    @Test
    fun abreModoECapitulos() {
        val book = Comic.open(ctx, Uri.fromFile(cbz("ordem.cbz", 10, 200, 300)), "ordem.cbz")
        assertEquals(listOf("p1.jpg", "p2.jpg", "p3.jpg"), book.pages.take(3))
        assertEquals("p10.jpg", book.pages.last())
        book.close()

        val c1 = cbz("Cap 1.cbz", 3, 200, 300, manga = true); val c2 = cbz("Cap 2.cbz", 4, 200, 300, manga = true)
        val web = cbz("webtoon.cbz", 3, 200, 900)
        ActivityScenario.launch(MainActivity::class.java).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.open(Uri.fromFile(web), fromPicker = false) }
            assertTrue("abriu", waitFor(15_000) { vm.comic != null })
            assertEquals("webtoon", vm.comic!!.defaultMode)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.closeComic() }

            val chapters = listOf(Library.Chapter(Uri.fromFile(c1), c1.name), Library.Chapter(Uri.fromFile(c2), c2.name))
            val series = Library.Series("serie-teste", "Série", chapters)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.openComicFromLibrary(series, 0) }
            assertTrue(waitFor(15_000) { vm.comic?.book?.name == "Cap 1.cbz" })
            assertEquals("manga", vm.comic!!.defaultMode)
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.comicChapter(1) }
            assertTrue("próximo capítulo", waitFor(15_000) { vm.comic?.book?.name == "Cap 2.cbz" })
            assertEquals(1f, Comic.progress(ctx, chapters[0].key)!!, 0.001f)
            assertTrue(Library.progress(ctx, series) > 0.4f)
            assertEquals("lendo", Library.tag(ctx, series))
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.closeComic() }
        }
    }

    @Test
    fun abreEpub() {
        val f = File(ctx.cacheDir, "livro.epub")
        ZipOutputStream(f.outputStream()).use { z ->
            fun put(n: String, t: String) { z.putNextEntry(ZipEntry(n)); z.write(t.toByteArray()); z.closeEntry() }
            put("mimetype", "application/epub+zip")
            put("META-INF/container.xml", "<container><rootfiles><rootfile full-path=\"OEBPS/c.opf\"/></rootfiles></container>")
            put("OEBPS/c.opf", "<package><metadata><dc:title>Meu Livro</dc:title></metadata><manifest>" +
                "<item id=\"a\" href=\"a.xhtml\"/><item id=\"b\" href=\"b.xhtml\"/></manifest><spine><itemref idref=\"a\"/><itemref idref=\"b\"/></spine></package>")
            put("OEBPS/a.xhtml", "<html><body><p>Um</p></body></html>")
            put("OEBPS/b.xhtml", "<html><body><p>Dois</p></body></html>")
        }
        ActivityScenario.launch(MainActivity::class.java).use { sc ->
            lateinit var vm: AppVm
            sc.onActivity { vm = ViewModelProvider(it)[AppVm::class.java] }
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.open(Uri.fromFile(f), fromPicker = false) }
            assertTrue("abriu o livro", waitFor(15_000) { vm.epub != null })
            assertEquals("Meu Livro", vm.epub!!.title)
            assertEquals(listOf("a.xhtml", "b.xhtml"), vm.epub!!.chapters.map { it.name })
            InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.closeEpub() }
        }
    }

    @Test
    fun achaBaloes() {
        val bmp = Bitmap.createBitmap(900, 1300, Bitmap.Config.ARGB_8888)
        val c = android.graphics.Canvas(bmp); c.drawColor(Color.rgb(170, 170, 180))
        val white = android.graphics.Paint().apply { color = Color.WHITE }
        val ink = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 34f; typeface = android.graphics.Typeface.DEFAULT_BOLD; textAlign = android.graphics.Paint.Align.CENTER }
        c.drawOval(60f, 80f, 480f, 320f, white); c.drawText("WHERE DID", 270f, 175f, ink); c.drawText("YOU GO LAST", 270f, 215f, ink); c.drawText("NIGHT?", 270f, 255f, ink)
        c.drawOval(430f, 520f, 830f, 740f, white); c.drawText("I WAS AT", 630f, 615f, ink); c.drawText("THE LIBRARY.", 630f, 655f, ink)
        val b = MangaTrad.balloons(bmp, "en")
        assertEquals(b.toString(), 2, b.size)
        assertTrue(b[0].text.uppercase().contains("NIGHT") && b[1].text.uppercase().contains("LIBRARY"))
    }
}
