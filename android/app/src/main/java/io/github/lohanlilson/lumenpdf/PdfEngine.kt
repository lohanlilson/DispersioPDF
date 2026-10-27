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
import kotlinx.coroutines.launch
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

    /** Tarefas em segundo plano (medir o tamanho das páginas). */
    private val bg = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Default)

    /**
     * Abre o PDF. Carregar cada página só para saber o tamanho é lento (dezenas de ms por página), então:
     * known = tamanhos já conhecidos (reabrir depois de uma edição que não muda as páginas) são reaproveitados;
     * senão, mede a primeira página e as demais em segundo plano (a tela se ajusta quando chegam).
     */
    suspend fun open(context: Context, uri: Uri, password: String? = null, known: List<PageSize>? = null): OpenPdf {
        val pdf = withContext(dispatcher) {
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
            if (known != null && known.size == n) {
                OpenPdf(this@PdfEngine, doc, pfd, androidx.compose.runtime.mutableStateListOf<PageSize>().apply { addAll(known) },
                    uri.toString(), BooleanArray(n) { true })
            } else {
                val first = if (n > 0) doc.openPage(0).use { measure(it) } else PageSize(595f, 842f)
                val list = androidx.compose.runtime.mutableStateListOf<PageSize>()
                repeat(n) { list += first }
                OpenPdf(this@PdfEngine, doc, pfd, list, uri.toString(), BooleanArray(n) { it == 0 })
            }
        }
        if (pdf.measured.any { !it }) bg.launch { measureAll(pdf) }
        return pdf
    }

    private fun measure(p: PdfPage) =
        PageSize(p.getPageWidthPoint().toFloat().coerceAtLeast(1f), p.getPageHeightPoint().toFloat().coerceAtLeast(1f))

    /** Tamanho real da página (mede na hora se ainda não foi medida). p = página já aberta. */
    private fun sizeOf(pdf: OpenPdf, page: Int, p: PdfPage): PageSize {
        if (pdf.measured[page]) return pdf.sizes[page]
        val sz = measure(p)
        pdf.measured[page] = true
        if (sz != pdf.sizes[page]) bg.launch(kotlinx.coroutines.Dispatchers.Main) { if (!pdf.closed) pdf.sizes[page] = sz }
        return sz
    }

    suspend fun pageSize(pdf: OpenPdf, page: Int): PageSize =
        if (pdf.measured[page]) pdf.sizes[page] else withContext(dispatcher) { pdf.doc.openPage(page).use { sizeOf(pdf, page, it) } }

    /** Mede as páginas restantes, uma por vez (a renderização das visíveis passa na frente entre uma e outra). */
    private suspend fun measureAll(pdf: OpenPdf) {
        val pending = HashMap<Int, PageSize>()
        for (i in pdf.measured.indices) {
            if (pdf.closed) return
            if (pdf.measured[i]) continue
            val sz = runCatching {
                withContext(dispatcher) { if (pdf.closed || pdf.measured[i]) null else pdf.doc.openPage(i).use { measure(it) } }
            }.getOrNull() ?: continue
            pdf.measured[i] = true
            if (sz != pdf.sizes[i]) pending[i] = sz
            if (pending.size >= 25 || i == pdf.measured.lastIndex) {
                val batch = HashMap(pending); pending.clear()
                withContext(kotlinx.coroutines.Dispatchers.Main) { if (!pdf.closed) batch.forEach { (k, v) -> pdf.sizes[k] = v } }
            }
        }
        if (pending.isNotEmpty()) withContext(kotlinx.coroutines.Dispatchers.Main) { if (!pdf.closed) pending.forEach { (k, v) -> pdf.sizes[k] = v } }
    }

    suspend fun render(pdf: OpenPdf, page: Int, widthPx: Int): Bitmap = withContext(dispatcher) {
        val key = "${pdf.id}#$page@$widthPx"
        cache.get(key)?.let { return@withContext it }
        val w = widthPx.coerceAtLeast(16)
        val bmp = pdf.doc.openPage(page).use { p ->
            val sz = sizeOf(pdf, page, p)
            val h = (w * sz.ratio).roundToInt().coerceAtLeast(16)
            Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).also { b ->
                b.eraseColor(Color.WHITE)
                p.renderPageBitmap(b, 0, 0, w, h, true, false, Color.WHITE, Color.WHITE)
            }
        }
        cache.put(key, bmp)
        android.util.Log.d("LumenPdf", "renderizado $key")
        bmp
    }

    /** Desenha sem guardar no cache (leitura de código de barras, análise). */
    suspend fun renderFresh(pdf: OpenPdf, page: Int, widthPx: Int): Bitmap = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val sz = sizeOf(pdf, page, p)
            val w = widthPx.coerceAtLeast(16)
            val h = (w * sz.ratio).roundToInt().coerceAtLeast(16)
            Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).also { b ->
                b.eraseColor(Color.WHITE)
                p.renderPageBitmap(b, 0, 0, w, h, false, false, Color.WHITE, Color.WHITE)
            }
        }
    }

    /** Rotação atual da página em graus (0, 90, 180, 270). */
    suspend fun pageRotation(pdf: OpenPdf, page: Int): Int = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p -> ((p.getPageRotation() % 4 + 4) % 4) * 90 }
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
                            val rects = (0 until nr).mapNotNull { k -> tp.textPageGetRect(k)?.let { frac(p, sizeOf(pdf, i, p), it) } }
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
        pdf.doc.openPage(page).use { p -> toPdf(p, sizeOf(pdf, page, p), fx, fy) }
    }

    suspend fun pdfPoints(pdf: OpenPdf, page: Int, pts: List<Pair<Float, Float>>): FloatArray = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val out = FloatArray(pts.size * 2)
            pts.forEachIndexed { i, (x, y) -> val q = toPdf(p, sizeOf(pdf, page, p), x, y); out[i * 2] = q.x; out[i * 2 + 1] = q.y }
            out
        }
    }

    /** Vários retângulos de uma vez (cada página é aberta uma vez só). */
    suspend fun fracOfAll(pdf: OpenPdf, items: List<Pair<Int, RectF>>): List<FracRect> = withContext(dispatcher) {
        val out = arrayOfNulls<FracRect>(items.size)
        items.indices.groupBy { items[it].first }.forEach { (page, idx) ->
            pdf.doc.openPage(page).use { p ->
                val sz = sizeOf(pdf, page, p)
                idx.forEach { k -> out[k] = frac(p, sz, items[k].second) }
            }
        }
        out.map { it!! }
    }

    suspend fun fracOf(pdf: OpenPdf, page: Int, r: RectF): FracRect = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p -> frac(p, sizeOf(pdf, page, p), r) }
    }

    /** Caracteres da página (uma vez por versão do documento). */
    suspend fun pageChars(pdf: OpenPdf, page: Int): PageChars {
        pdf.chars[page]?.let { return it }
        return withContext(dispatcher) {
            pdf.chars.getOrPut(page) {
                pdf.doc.openPage(page).use { p ->
                    p.openTextPage().use { tp ->
                        val n = tp.textPageCountChars()
                        val sb = StringBuilder(n)
                        val fr = arrayOfNulls<FracRect>(n)
                        val pr = arrayOfNulls<RectF>(n)
                        for (k in 0 until n) {
                            val c = tp.textPageGetUnicode(k)
                            sb.append(c)
                            val b = tp.textPageGetCharBox(k)
                            if (b != null && kotlin.math.abs(b.right - b.left) > 0.01f && c != '\n' && c != '\r') {
                                pr[k] = b
                                fr[k] = frac(p, sizeOf(pdf, page, p), b)
                            }
                        }
                        PageChars(page, sb.toString(), fr, pr)
                    }
                }
            }
        }
    }

    /** Índice do caractere sob o dedo (-1 se não houver texto perto). */
    suspend fun charAt(pdf: OpenPdf, page: Int, fx: Float, fy: Float): Int = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val pt = toPdf(p, sizeOf(pdf, page, p), fx, fy)
            p.openTextPage().use { tp ->
                var i = tp.textPageGetCharIndexAtPos(pt.x.toDouble(), pt.y.toDouble(), 4.0, 4.0)
                if (i < 0) i = tp.textPageGetCharIndexAtPos(pt.x.toDouble(), pt.y.toDouble(), 14.0, 10.0)
                i
            }
        }
    }

    /** Caracteres da página com a caixa de cada um (coordenadas do PDF). */
    suspend fun chars(pdf: OpenPdf, page: Int): List<Pair<Char, RectF?>> = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            p.openTextPage().use { tp ->
                (0 until tp.textPageCountChars()).map { k ->
                    tp.textPageGetUnicode(k) to tp.textPageGetCharBox(k)?.takeIf { kotlin.math.abs(it.right - it.left) > 0.01f }
                }
            }
        }
    }

    suspend fun lineAt(pdf: OpenPdf, page: Int, fx: Float, fy: Float): TextLine? = withContext(dispatcher) {
        pdf.doc.openPage(page).use { p ->
            val pt = toPdf(p, sizeOf(pdf, page, p), fx, fy)
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
                    frac(p, sizeOf(pdf, page, p), rect), size, l, base)
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
                    pdfRects.map { frac(p, sizeOf(pdf, page, p), it) }, pdfRects)
            }
        }
    }

    suspend fun links(pdf: OpenPdf, page: Int): List<PageLink> = withContext(dispatcher) {
        pdf.links.getOrPut(page) {
            pdf.doc.openPage(page).use { p ->
                p.getPageLinks().map { PageLink(frac(p, sizeOf(pdf, page, p), it.bounds), it.destPageIdx, it.uri) }
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
        pdf.closed = true
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
    /** tamanhos das páginas (estado observável: os que ainda não foram medidos chegam depois) */
    val sizes: androidx.compose.runtime.snapshots.SnapshotStateList<PageSize>,
    val id: String,
    val measured: BooleanArray,
) {
    @Volatile var closed = false
    val links = HashMap<Int, List<PageLink>>()
    val chars = java.util.concurrent.ConcurrentHashMap<Int, PageChars>()
}

/**
 * Caracteres de uma página guardados em memória: a seleção e o marca-texto acompanham o dedo
 * sem consultar o PDFium a cada movimento.
 */
class PageChars(val page: Int, val text: String, val frac: Array<FracRect?>, val pdf: Array<RectF?>) {
    val size get() = frac.size

    /** Caractere sob o ponto; strict = só se estiver perto de algum texto. */
    fun charAt(fx: Float, fy: Float, strict: Boolean = true): Int {
        var best = -1
        var bd = Float.MAX_VALUE
        for (k in frac.indices) {
            val r = frac[k] ?: continue
            if (fx in r.l..r.r && fy in r.t..r.b) return k
            val dx = maxOf(r.l - fx, 0f, fx - r.r)
            val dy = maxOf(r.t - fy, 0f, fy - r.b)
            val dd = dx + dy * 3
            if (dd < bd) { bd = dd; best = k }
        }
        return if (strict && bd > 0.02f) -1 else best
    }

    /** Palavra que contém o caractere k (início, fim). */
    fun word(k: Int): Pair<Int, Int> {
        var a = k; var b = k
        while (a > 0 && text.getOrNull(a - 1)?.isLetterOrDigit() == true) a--
        while (b < text.length - 1 && text.getOrNull(b + 1)?.isLetterOrDigit() == true) b++
        return a to b
    }

    /** Seleção de palavras inteiras, do caractere a até o b (em qualquer direção). */
    fun wordSelection(a: Int, b: Int): TextSelection {
        val (s, e) = if (a <= b) word(a).first to word(b).second else word(b).first to word(a).second
        return selection(s, e)
    }

    fun selection(a: Int, b: Int): TextSelection {
        val s = minOf(a, b).coerceIn(0, size - 1)
        val e = maxOf(a, b).coerceIn(0, size - 1)
        val fr = ArrayList<FracRect>()
        val pr = ArrayList<RectF>()
        var cf: FracRect? = null
        var cp: RectF? = null
        for (k in s..e) {
            val f = frac[k] ?: continue
            val p = pdf[k] ?: continue
            val c = cf
            val h = f.b - f.t
            val sameLine = c != null && kotlin.math.abs((f.t + f.b) / 2 - (c.t + c.b) / 2) < maxOf(h, c.b - c.t) * 0.6f && f.l >= c.l - h
            if (c != null && sameLine) {
                cf = FracRect(minOf(c.l, f.l), minOf(c.t, f.t), maxOf(c.r, f.r), maxOf(c.b, f.b))
                val q = cp!!
                cp = RectF(minOf(q.left, p.left), maxOf(q.top, p.top), maxOf(q.right, p.right), minOf(q.bottom, p.bottom))
            } else {
                c?.let { fr += it; pr += cp!! }
                cf = f
                cp = RectF(minOf(p.left, p.right), maxOf(p.top, p.bottom), maxOf(p.left, p.right), minOf(p.top, p.bottom))
            }
        }
        cf?.let { fr += it; pr += cp!! }
        return TextSelection(page, s, e, text.substring(s, minOf(e + 1, text.length)).replace("\r\n", "\n"), fr, pr)
    }
}
