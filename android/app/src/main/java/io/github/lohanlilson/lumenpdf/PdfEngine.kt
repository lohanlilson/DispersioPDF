package io.github.lohanlilson.lumenpdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Rect
import android.graphics.RectF
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.LruCache
import io.legere.pdfiumandroid.PdfDocument
import io.legere.pdfiumandroid.PdfPage
import io.legere.pdfiumandroid.PdfPasswordException
import io.legere.pdfiumandroid.PdfiumCore
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.withContext
import java.io.File
import java.util.concurrent.Executors
import kotlin.math.roundToInt

/** Tamanho de exibição da página em pontos (já considera a rotação). */
data class PageSize(val w: Float, val h: Float) {
    val ratio get() = h / w
}

/** Retângulo em frações da LARGURA da página exibida (x e y divididos pela largura). */
data class FracRect(val l: Float, val t: Float, val r: Float, val b: Float)

data class SearchHit(val page: Int, val rects: List<FracRect>)
data class PageLink(val area: FracRect, val page: Int?, val uri: String?)
data class TocItem(val title: String, val page: Int, val level: Int)

class PasswordNeeded : Exception()

/**
 * Acesso ao PDFium. Tudo roda numa única thread: o PDFium não é seguro para uso em paralelo.
 */
class PdfEngine(context: Context) {
    private val core = PdfiumCore(context)
    val dispatcher = Executors.newSingleThreadExecutor { r -> Thread(r, "pdfium").apply { priority = Thread.NORM_PRIORITY } }
        .asCoroutineDispatcher()

    private val cache = object : LruCache<String, Bitmap>((Runtime.getRuntime().maxMemory() / 5).toInt()) {
        override fun sizeOf(key: String, value: Bitmap) = value.allocationByteCount
    }

    fun cached(key: String): Bitmap? = cache.get(key)

    suspend fun open(context: Context, uri: Uri, password: String? = null): OpenPdf = withContext(dispatcher) {
        val pfd = context.contentResolver.openFileDescriptor(uri, "r") ?: error("Não foi possível abrir o arquivo")
        val doc = try {
            if (password != null) core.newDocument(pfd, password) else core.newDocument(pfd)
        } catch (e: PdfPasswordException) {
            pfd.close()
            throw PasswordNeeded()
        } catch (e: Exception) {
            pfd.close()
            throw e
        }
        val n = doc.getPageCount()
        val sizes = ArrayList<PageSize>(n)
        for (i in 0 until n) {
            doc.openPage(i).use { p ->
                sizes += PageSize(p.getPageWidthPoint().toFloat().coerceAtLeast(1f), p.getPageHeightPoint().toFloat().coerceAtLeast(1f))
            }
        }
        OpenPdf(this@PdfEngine, doc, pfd, sizes, uri.toString())
    }

    suspend fun render(pdf: OpenPdf, page: Int, widthPx: Int): Bitmap = withContext(dispatcher) {
        val key = "${pdf.id}#$page@$widthPx"
        cache.get(key)?.let { return@withContext it }
        val sz = pdf.sizes[page]
        val w = widthPx.coerceAtLeast(16)
        val h = (w * sz.ratio).roundToInt().coerceAtLeast(16)
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        bmp.eraseColor(Color.WHITE)
        pdf.doc.openPage(page).use { p ->
            p.renderPageBitmap(bmp, 0, 0, w, h, true, false, Color.WHITE, Color.WHITE)
        }
        cache.put(key, bmp)
        bmp
    }

    /** Converte um retângulo em coordenadas do PDF para frações da largura exibida. */
    private fun frac(p: PdfPage, sz: PageSize, r: RectF): FracRect {
        val base = 4000
        val hh = (base * sz.ratio).roundToInt()
        val d: Rect = p.mapRectToDevice(0, 0, base, hh, 0, r)
        val l = minOf(d.left, d.right) / base.toFloat()
        val rr = maxOf(d.left, d.right) / base.toFloat()
        val t = minOf(d.top, d.bottom) / base.toFloat()
        val b = maxOf(d.top, d.bottom) / base.toFloat()
        return FracRect(l, t, rr, b)
    }

    suspend fun search(pdf: OpenPdf, query: String, onPage: (Int) -> Unit = {}): List<SearchHit> = withContext(dispatcher) {
        val out = ArrayList<SearchHit>()
        if (query.isBlank()) return@withContext out
        for (i in 0 until pdf.sizes.size) {
            onPage(i)
            pdf.doc.openPage(i).use { p ->
                p.openTextPage().use { tp ->
                    val fr = tp.findStart(query, emptySet(), 0) ?: return@use
                    try {
                        while (fr.findNext()) {
                            val idx = fr.getSchResultIndex()
                            val cnt = fr.getSchCount()
                            val nr = tp.textPageCountRects(idx, cnt)
                            val rects = (0 until nr).mapNotNull { k -> tp.textPageGetRect(k)?.let { frac(p, pdf.sizes[i], it) } }
                            if (rects.isNotEmpty()) out += SearchHit(i, rects)
                        }
                    } finally {
                        fr.close()
                    }
                }
            }
        }
        out
    }

    suspend fun links(pdf: OpenPdf, page: Int): List<PageLink> = withContext(dispatcher) {
        pdf.links.getOrPut(page) {
            pdf.doc.openPage(page).use { p ->
                p.getPageLinks().map { PageLink(frac(p, pdf.sizes[page], it.bounds), it.destPageIdx, it.uri) }
            }
        }
    }

    suspend fun pageText(pdf: OpenPdf, page: Int): String = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p -> p.openTextPage().use { tp -> tp.textPageGetText(0, tp.textPageCountChars()) ?: "" } }
    }

    suspend fun toc(pdf: OpenPdf): List<TocItem> = withContext(dispatcher) {
        val out = ArrayList<TocItem>()
        fun walk(list: List<PdfDocument.Bookmark>, level: Int) {
            for (b in list) {
                out += TocItem(b.title ?: "", b.pageIdx.toInt(), level)
                walk(b.children, level + 1)
            }
        }
        walk(pdf.doc.getTableOfContents(), 0)
        out
    }

    suspend fun close(pdf: OpenPdf) = withContext(dispatcher) {
        runCatching { pdf.doc.close() }
        runCatching { pdf.pfd.close() }
    }

    /** Miniatura da primeira página (lista de recentes), guardada em disco. */
    suspend fun thumbnail(context: Context, uri: Uri, file: File): Bitmap? = withContext(dispatcher) {
        if (file.exists()) return@withContext android.graphics.BitmapFactory.decodeFile(file.absolutePath)
        runCatching {
            context.contentResolver.openFileDescriptor(uri, "r")?.use { pfd ->
                core.newDocument(pfd).use { doc ->
                    doc.openPage(0).use { p ->
                        val w = 240
                        val h = (w * p.getPageHeightPoint().toFloat() / p.getPageWidthPoint().coerceAtLeast(1)).roundToInt()
                            .coerceIn(16, 480)
                        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                        bmp.eraseColor(Color.WHITE)
                        p.renderPageBitmap(bmp, 0, 0, w, h, true, false, Color.WHITE, Color.WHITE)
                        file.parentFile?.mkdirs()
                        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 90, it) }
                        bmp
                    }
                }
            }
        }.getOrNull()
    }
}

class OpenPdf(
    val engine: PdfEngine,
    val doc: PdfDocument,
    val pfd: ParcelFileDescriptor,
    val sizes: List<PageSize>,
    val id: String,
) {
    val links = HashMap<Int, List<PageLink>>()
}
