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

/** Linha de texto tocada (para editar): rect em coordenadas do PDF, frac na tela, tamanho e linha de base. */
data class TextLine(val page: Int, val text: String, val rect: RectF, val frac: FracRect, val size: Float, val x: Float, val baseline: Float)

data class TextSelection(val page: Int, val start: Int, val end: Int, val text: String,
                         val rects: List<FracRect>, val pdfRects: List<RectF>)

/**
 * Acesso ao PDFium. Tudo roda numa única thread: o PDFium não é seguro para uso em paralelo.
 */
private const val BASE = 4000

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
        android.util.Log.d("LumenPdf", "renderizado $key")
        bmp
    }

    /** Converte um retângulo em coordenadas do PDF para frações da largura exibida. */
    private fun frac(p: PdfPage, sz: PageSize, r: RectF): FracRect {
        val hh = (BASE * sz.ratio).roundToInt()
        val d: Rect = p.mapRectToDevice(0, 0, BASE, hh, 0, r)
        val l = minOf(d.left, d.right) / BASE.toFloat()
        val rr = maxOf(d.left, d.right) / BASE.toFloat()
        val t = minOf(d.top, d.bottom) / BASE.toFloat()
        val b = maxOf(d.top, d.bottom) / BASE.toFloat()
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


    /** Ponto em frações da largura exibida -> coordenadas do PDF. */
    private fun toPdf(p: PdfPage, sz: PageSize, fx: Float, fy: Float): android.graphics.PointF {
        val hh = (BASE * sz.ratio).roundToInt()
        return p.mapDeviceCoordsToPage(0, 0, BASE, hh, 0, (fx * BASE).roundToInt(), (fy * BASE).roundToInt())
    }

    suspend fun pdfPoint(pdf: OpenPdf, page: Int, fx: Float, fy: Float): android.graphics.PointF = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p -> toPdf(p, pdf.sizes[page], fx, fy) }
    }

    suspend fun pdfPoints(pdf: OpenPdf, page: Int, pts: List<Pair<Float, Float>>): FloatArray = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val out = FloatArray(pts.size * 2)
            pts.forEachIndexed { i, (x, y) -> val q = toPdf(p, pdf.sizes[page], x, y); out[i * 2] = q.x; out[i * 2 + 1] = q.y }
            out
        }
    }

    suspend fun fracOf(pdf: OpenPdf, page: Int, r: RectF): FracRect = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p -> frac(p, pdf.sizes[page], r) }
    }

    /** Índice do caractere sob o dedo (-1 se não houver texto perto). */
    suspend fun charAt(pdf: OpenPdf, page: Int, fx: Float, fy: Float): Int = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val pt = toPdf(p, pdf.sizes[page], fx, fy)
            p.openTextPage().use { tp ->
                var i = tp.textPageGetCharIndexAtPos(pt.x.toDouble(), pt.y.toDouble(), 4.0, 4.0)
                if (i < 0) i = tp.textPageGetCharIndexAtPos(pt.x.toDouble(), pt.y.toDouble(), 14.0, 10.0)
                i
            }
        }
    }

    suspend fun lineAt(pdf: OpenPdf, page: Int, fx: Float, fy: Float): TextLine? = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val pt = toPdf(p, pdf.sizes[page], fx, fy)
            p.openTextPage().use { tp ->
                val n = tp.textPageCountChars()
                val i = tp.textPageGetCharIndexAtPos(pt.x.toDouble(), pt.y.toDouble(), 6.0, 6.0)
                if (i < 0 || i >= n) return@withContext null
                fun box(k: Int): RectF? = tp.textPageGetCharBox(k)?.takeIf { kotlin.math.abs(it.right - it.left) > 0.01f }
                val b0 = box(i) ?: return@withContext null
                val mid = (b0.top + b0.bottom) / 2
                val h = kotlin.math.abs(b0.top - b0.bottom).coerceAtLeast(2f)
                fun sameLine(k: Int): Boolean {
                    val c = tp.textPageGetUnicode(k)
                    if (c == '\n' || c == '\r') return false
                    val b = box(k) ?: return true   // espaço sem caixa: continua
                    return kotlin.math.abs((b.top + b.bottom) / 2 - mid) < h * 0.6f
                }
                var a = i
                while (a > 0 && sameLine(a - 1)) a--
                var e = i
                while (e < n - 1 && sameLine(e + 1)) e++
                val boxes = (a..e).mapNotNull { box(it) }
                val l = boxes.minOf { minOf(it.left, it.right) }
                val r = boxes.maxOf { maxOf(it.left, it.right) }
                val top = boxes.maxOf { maxOf(it.top, it.bottom) }
                val bottom = boxes.minOf { minOf(it.top, it.bottom) }
                val base = boxes.map { minOf(it.top, it.bottom) }.sorted().let { it[it.size / 2] }
                val rect = RectF(l, top, r, bottom)
                val size = tp.getFontSize(i).toFloat().takeIf { it > 1f } ?: (top - bottom)
                TextLine(page, (tp.textPageGetText(a, e - a + 1) ?: "").trimEnd('\r', '\n'), rect,
                    frac(p, pdf.sizes[page], rect), size, l, base)
            }
        }
    }

    /** Seleção de a até b (inclusive): texto, retângulos na tela e no PDF. */
    suspend fun selection(pdf: OpenPdf, page: Int, a: Int, b: Int): TextSelection = withContext(dispatcher) {
        val s = minOf(a, b)
        val n = maxOf(a, b) - s + 1
        pdf.doc.openPage(page).use { p ->
            p.openTextPage().use { tp ->
                val nr = tp.textPageCountRects(s, n)
                val pdfRects = (0 until nr).mapNotNull { tp.textPageGetRect(it) }
                TextSelection(page, s, s + n - 1, tp.textPageGetText(s, n) ?: "",
                    pdfRects.map { frac(p, pdf.sizes[page], it) }, pdfRects)
            }
        }
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
