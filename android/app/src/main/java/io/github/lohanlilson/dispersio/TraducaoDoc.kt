package io.github.lohanlilson.dispersio

import android.content.Context
import android.graphics.RectF
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.font.PDFont
import com.tom_roush.pdfbox.pdmodel.font.PDType0Font
import com.tom_roush.pdfbox.text.PDFTextStripper
import com.tom_roush.pdfbox.text.TextPosition
import java.io.File

/** Um bloco de texto da página (parágrafo, título…), em coordenadas de cima para baixo (pontos do PDF). */
data class TBlock(
    val page: Int, val rect: RectF, val text: String, val size: Float, val bold: Boolean,
    var keep: Boolean = false, var cont: Boolean = false, var why: String = "",
    val serif: Boolean = false, val center: Boolean = false, val nlines: Int = 1,
) {
    val shown get() = Citacoes.plain(text)
}

/** Citações ficam fora da tradução e voltam no fim da frase. Mesmas regras de dispersio/traducao.py. */
object Citacoes {
    const val SUP = ''
    const val SUP_END = ''
    private val SUP_RE = Regex("$SUP([^$SUP_END]*)$SUP_END")
    private val BRACKET = Regex("\\s?\\[\\s*\\d+[a-z]?(?:\\s*[-–,;]\\s*\\d+[a-z]?)*\\s*\\]")
    private val AUTHOR = Regex("\\s?\\((?=[^()]*\\b(?:19|20)\\d{2}[a-z]?\\b)" +
        "(?=[^()]*[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\\-]+(?:\\s+et\\s+al\\.?|\\s+(?:and|&|e|y)\\s+[A-ZÀ-Ý]|,|\\s+(?:19|20)\\d{2}))[^()]{3,240}\\)")
    private const val SUPERS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    private val ABBR = Regex("\\b(?:et al|e\\.g|i\\.e|Fig|Figs|Eq|Eqs|Ref|Refs|vs|approx|ca|cf|Dr|Mr|Mrs|Ms|Prof|No|Vol|pp|Sr|Sra|Jr|St|Inc|Ltd|sp|spp)\\.")
    val KEEP = Regex("^[\\d\\s.,;:()\\[\\]%±×=<>+\\-–/·*]+$")

    fun superscript(s: String) = s.trim().map { c -> when (c) { in '0'..'9' -> SUPERS[c - '0']; ',' -> '˒'; '-', '–' -> '⁻'; else -> c } }.joinToString("")
    fun plain(t: String) = SUP_RE.replace(t) { superscript(it.groupValues[1]) }

    fun sentences(text: String): List<String> {
        val prot = ABBR.replace(text) { it.value.replace('.', '․') }
        return prot.split(Regex("(?<=[.!?])\\s+(?=[A-ZÀ-Ý0-9(\"“])")).map { it.replace('․', '.').trim() }.filter { it.isNotEmpty() }
    }

    fun split(sentence: String): Pair<String, List<String>> {
        val cites = ArrayList<String>()
        var s = SUP_RE.replace(sentence) { cites += "$SUP${it.groupValues[1]}$SUP_END"; " " }
        s = BRACKET.replace(s) { cites += it.value.trim(); " " }
        s = AUTHOR.replace(s) { cites += it.value.trim(); " " }
        s = s.replace(Regex("\\s{2,}"), " ").replace(Regex("\\s+([.,;:!?)])"), "$1").trim()
        return s to cites
    }

    fun join(text: String, cites: List<String>): String {
        if (cites.isEmpty()) return text
        val m = Regex("^(.*?)([.!?:;]*[\"”»)]*)$", RegexOption.DOT_MATCHES_ALL).find(text.trimEnd())
        val body = m?.groupValues?.get(1) ?: text
        val end = m?.groupValues?.get(2) ?: ""
        val sb = StringBuilder(body)
        for (c in cites) if (c.first() == SUP) sb.append(superscript(c.substring(1, c.length - 1))) else sb.append(' ').append(c)
        return sb.append(end).toString()
    }

    /** Traduz um parágrafo frase a frase, sem as citações; elas voltam no fim de cada frase. */
    suspend fun translate(para: String, tr: suspend (String) -> String): String {
        val p = plain(para)
        if (p.isBlank() || KEEP.matches(p) || p.count { it.isLetter() } < 3) return p
        val out = ArrayList<String>()
        for (s in sentences(para)) {
            val (clean, cites) = split(s)
            val t = if (clean.count { it.isLetter() } >= 2) runCatching { tr(clean) }.getOrDefault(clean) else clean
            out += join(t, cites)
        }
        return out.joinToString(" ")
    }
}

/** Lê o documento como um leitor: parágrafos na ordem certa (colunas), o que não se traduz, o que continua. */
object DocAnalysis {
    private class Collector : PDFTextStripper() {
        val paras = ArrayList<MutableList<MutableList<List<TextPosition>>>>()   // parágrafo → linhas → palavras
        private var cur: MutableList<MutableList<List<TextPosition>>>? = null
        private var line: MutableList<List<TextPosition>>? = null
        init { sortByPosition = false; setShouldSeparateByBeads(true) }
        override fun writeParagraphStart() { cur = ArrayList<MutableList<List<TextPosition>>>().also { paras += it }; line = null }
        override fun writeLineSeparator() { line = null }
        override fun writeString(text: String, pos: List<TextPosition>) {
            val p = cur ?: ArrayList<MutableList<List<TextPosition>>>().also { paras += it; cur = it }
            val l = line ?: ArrayList<List<TextPosition>>().also { p += it; line = it }
            if (pos.isNotEmpty()) l += ArrayList(pos)
        }
    }

    private val REF_HEAD = Regex("^\\s*(?:\\d+\\.?\\s*)?(?:references?(?:\\s+list)?|bibliography|literature\\s+cited|works\\s+cited|" +
        "refer[êe]ncias(?:\\s+bibliogr[áa]ficas)?|bibliografia|referencias|r[ée]f[ée]rences|literatur(?:verzeichnis)?|" +
        "riferimenti(?:\\s+bibliografici)?)\\s*:?\\s*$", RegexOption.IGNORE_CASE)
    private val AFTER_REFS = Regex("^\\s*(?:\\d+\\.?\\s*)?(?:appendix|appendices|ap[êe]ndices?|anexos?|supplementary|supporting\\s+information|" +
        "material\\s+suplementar)\\b", RegexOption.IGNORE_CASE)
    private val PAGE_NO = Regex("^\\s*(?:p(?:age|ágina|ag)?\\.?\\s*)?\\d{1,4}(?:\\s*(?:of|de|/)\\s*\\d{1,4})?\\s*$", RegexOption.IGNORE_CASE)

    fun rawBlocks(doc: PDDocument, page: Int): List<TBlock> {
        val c = Collector()
        c.startPage = page + 1; c.endPage = page + 1
        runCatching { c.getText(doc) }
        val out = ArrayList<TBlock>()
        val pageW = doc.getPage(page).cropBox.width
        for (para in c.paras) {
            val rows = ArrayList<LineInfo>()
            for (ln in para) {
                var l = Float.MAX_VALUE; var t = Float.MAX_VALUE; var r = -1f; var b = -1f
                var maxSize = 0f; var boldChars = 0; var chars = 0; var serifChars = 0
                var family = ""
                val all = ln.flatten()
                val big = all.maxOfOrNull { it.fontSizeInPt } ?: 0f
                val bigH = all.maxOfOrNull { it.heightDir } ?: 0f
                val base = all.map { it.yDirAdj }.sorted().let { if (it.isEmpty()) 0f else it[it.size / 2] }
                // número de citação pequeno/elevado — às vezes vem grudado na palavra ("common³")
                fun tiny(p: TextPosition) = (big > 0 && p.fontSizeInPt < big * 0.78f) || (bigH > 0 && p.heightDir < bigH * 0.72f) ||
                    (bigH > 0 && p.yDirAdj < base - bigH * 0.25f)
                fun citeChar(p: TextPosition) = (p.unicode ?: "").let { u -> u.isNotEmpty() && u.all { it.isDigit() || it in ",;-–*†‡§" } }
                fun sup(p: TextPosition) = citeChar(p) && tiny(p)
                // alguns geradores (Skia/Chrome/Android) gravam o número elevado fora de ordem, no fim da linha:
                // reordena pela posição e remonta os espaços pelo vão entre letras
                val pos = all.sortedBy { it.xDirAdj }
                val sb = StringBuilder()
                var prev: TextPosition? = null
                var i = 0
                while (i < pos.size) {
                    val p = pos[i]
                    if (sup(p)) {
                        var j = i
                        while (j < pos.size && sup(pos[j])) j++
                        val run = pos.subList(i, j).joinToString("") { it.unicode ?: "" }.trim()
                        if (run.any { it.isDigit() }) {
                            while (sb.endsWith(" ")) sb.setLength(sb.length - 1)
                            sb.append(Citacoes.SUP).append(run).append(Citacoes.SUP_END)
                            if ((pos.getOrNull(j)?.unicode ?: "").firstOrNull()?.isLetterOrDigit() == true) sb.append(' ')
                            prev = pos[j - 1]; i = j; continue
                        }
                    }
                    val u = p.unicode ?: ""
                    val q = prev
                    if (q != null && u.isNotBlank() && sb.isNotEmpty() && !sb.endsWith(" ")) {
                        val gap = p.xDirAdj - (q.xDirAdj + q.widthDirAdj)
                        val sp = if (q.widthOfSpace > 0f && !q.widthOfSpace.isNaN()) q.widthOfSpace else q.fontSizeInPt * 0.25f
                        if (gap > sp * 0.45f) sb.append(' ')
                    }
                    if (u.isBlank()) { if (sb.isNotEmpty() && !sb.endsWith(" ")) sb.append(' ') }
                    else {
                        sb.append(u)
                        l = minOf(l, p.xDirAdj); r = maxOf(r, p.xDirAdj + p.widthDirAdj)
                        t = minOf(t, p.yDirAdj - p.heightDir * 1.15f); b = maxOf(b, p.yDirAdj + p.heightDir * 0.25f)
                        maxSize = maxOf(maxSize, p.fontSizeInPt)
                        chars++
                        val fn = p.font?.name.orEmpty()
                        if (BOLD_FONT.containsMatchIn(fn)) boldChars++
                        if (SERIF_FONT.containsMatchIn(fn)) serifChars++
                        if (family.isEmpty()) family = fn.substringAfter('+').lowercase().split('-', ',', '.')[0].replace("bold", "")
                    }
                    prev = p; i++
                }
                val lineText = sb.toString().trim()
                if (lineText.isEmpty() || r < 0) continue
                rows += LineInfo(lineText, RectF(l, t, r, b), if (maxSize > 0) maxSize else 10f, chars > 0 && boldChars > chars * 0.7f,
                    serifChars > chars / 2, family)
            }
            // um parágrafo do PDFBox pode ter título + texto: separa pelas mudanças de tamanho, negrito e fonte
            val groups = ArrayList<MutableList<LineInfo>>()
            for (ln in rows) {
                val g = groups.lastOrNull(); val pv = g?.lastOrNull()
                val split = pv == null || kotlin.math.abs(ln.size - pv.size) > maxOf(ln.size, pv.size) * 0.15f || ln.bold != pv.bold ||
                    (ln.family != pv.family && (g.size == 1 || ln.text.split(' ').size <= 8))
                if (split) groups += mutableListOf(ln) else g!! += ln
            }
            for (g in groups) {
                var txt = ""
                for (ln in g) txt = if (txt.endsWith("-") && ln.text.first().isLowerCase()) txt.dropLast(1) + ln.text
                    else if (txt.isEmpty()) ln.text else "$txt ${ln.text}"
                txt = txt.replace(Regex("[ \\t]+"), " ").trim()
                if (txt.isEmpty()) continue
                val rect = RectF(g[0].rect); for (ln in g.drop(1)) rect.union(ln.rect)
                val cx = (rect.left + rect.right) / 2
                val center = if (g.size >= 2) g.all { kotlin.math.abs((it.rect.left + it.rect.right) / 2 - cx) < rect.width() * 0.03f } &&
                    g.maxOf { it.rect.left } - g.minOf { it.rect.left } > rect.width() * 0.04f
                    else kotlin.math.abs(cx - pageW / 2) < pageW * 0.02f && rect.width() < pageW * 0.8f
                out += TBlock(page, rect, txt, g.maxOf { it.size }, g.count { it.bold } * 2 > g.size,
                    serif = g.count { it.serif } * 2 > g.size, center = center, nlines = g.size)
            }
        }
        return out
    }

    private val EN_STOP = setOf("the", "of", "and", "to", "in", "is", "are", "for", "with", "that", "this", "we", "as", "by", "on",
        "be", "from", "an", "which", "our", "it", "at", "was", "were", "has", "have", "can", "not", "or", "where", "when", "if", "then")

    private class LineInfo(val text: String, val rect: RectF, val size: Float, val bold: Boolean, val serif: Boolean, val family: String)
    private val BOLD_FONT = Regex("bold|black|heavy|semibold|demi|[.,-]b$|-bd|bd$|cmbx|medi", RegexOption.IGNORE_CASE)
    private val SERIF_FONT = Regex("times|serif|roman|minion|georgia|cambria|garamond|palatino|charter|nimbusrom|cmr|lmroman|stix|" +
        "utopia|baskerville|caslon|warnock|advtim", RegexOption.IGNORE_CASE)
    private val EMAIL_URL = Regex("[\\w.+-]+@[\\w-]+(?:\\.[\\w-]+)+|https?://\\S+|www\\.\\S+|doi\\.org/\\S+")

    /** Linha de autores: nomes com iniciais maiúsculas, vírgulas e números de afiliação sobrescritos. */
    private fun authors(text: String, words: List<String>): Boolean {
        if (text.count { it == Citacoes.SUP } < 2 || ',' !in text || words.isEmpty()) return false
        val particles = setOf("and", "e", "y", "de", "da", "do", "dos", "das", "van", "von")
        return words.count { it[0].isUpperCase() || it.lowercase() in particles } >= words.size * 0.8 &&
            !Regex("[.!?]\\s+[a-z]").containsMatchIn(Citacoes.plain(text))
    }

    fun readingOrder(blocks: List<TBlock>, width: Float, height: Float): List<TBlock> {
        val mid = width / 2
        fun side(b: TBlock): Char {
            if (b.rect.bottom < height * 0.085f || b.rect.top > height * 0.915f) return 'F'
            if (b.rect.left < mid - width * 0.04f && b.rect.right > mid + width * 0.04f) return 'F'
            val cx = (b.rect.left + b.rect.right) / 2
            if (kotlin.math.abs(cx - mid) < width * 0.03f) return 'F'
            return if (cx < mid) 'L' else 'R'
        }
        if (blocks.count { side(it) == 'L' } < 2 || blocks.count { side(it) == 'R' } < 2) return blocks.sortedWith(compareBy({ Math.round(it.rect.top) }, { it.rect.left }))
        val out = ArrayList<TBlock>(); val band = ArrayList<TBlock>()
        fun flush() { out += band.filter { side(it) == 'L' }.sortedBy { it.rect.top }; out += band.filter { side(it) == 'R' }.sortedBy { it.rect.top }; band.clear() }
        for (b in blocks.sortedWith(compareBy({ it.rect.top }, { it.rect.left }))) if (side(b) == 'F') { flush(); out += b } else band += b
        flush()
        return out
    }

    /** {página: blocos na ordem de leitura}, marcando o que não se traduz e o que continua o parágrafo anterior. */
    fun analyze(doc: PDDocument, pages: List<Int>): Map<Int, List<TBlock>> {
        val per = LinkedHashMap<Int, List<TBlock>>()
        val heights = HashMap<Int, Float>()
        for (p in pages) {
            val box = doc.getPage(p).cropBox
            heights[p] = box.height
            per[p] = readingOrder(rawBlocks(doc, p), box.width, box.height)
        }
        fun key(b: TBlock) = b.shown.lowercase().replace(Regex("\\d+"), "#").trim()
        fun edge(b: TBlock) = b.rect.bottom < heights[b.page]!! * 0.085f || b.rect.top > heights[b.page]!! * 0.915f
        val cnt = per.values.flatten().filter { edge(it) }.groupingBy { key(it) }.eachCount()
        val rep = maxOf(2, (pages.size * 0.3 + 0.5).toInt())
        for (b in per.values.flatten()) {
            val t = b.shown
            when {
                PAGE_NO.matches(t) -> { b.keep = true; b.why = "número da página" }
                edge(b) && pages.size >= 2 && (cnt[key(b)] ?: 0) >= rep -> { b.keep = true; b.why = "cabeçalho/rodapé" }
                Citacoes.KEEP.matches(t) || t.count { it.isLetter() } < 3 -> { b.keep = true; b.why = "números" }
                else -> {
                    val h = heights[b.page]!!
                    val words = Regex("[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’-]*").findAll(t).map { it.value }.toList()
                    when {
                        words.none { it.length >= 3 } -> { b.keep = true; b.why = "números" }
                        (b.rect.bottom < h * 0.075f || b.rect.top > h * 0.94f) && words.size <= 20 -> { b.keep = true; b.why = "cabeçalho/rodapé" }
                        authors(b.text, words) -> { b.keep = true; b.why = "autores" }
                        EMAIL_URL.containsMatchIn(t) && EMAIL_URL.replace(t, " ").trim().split(Regex("\\s+")).size <= 6 ->
                            { b.keep = true; b.why = "e-mail/endereço" }
                        (Citacoes.SUP in b.text || Regex("[∗*†‡§]").containsMatchIn(t)) && words.size in 2..5 && words.all { it[0].isUpperCase() } ->
                            { b.keep = true; b.why = "nome" }
                        Regex("[=∗×|^]").containsMatchIn(t) && words.size <= 14 && words.none { it.lowercase() in EN_STOP } ->
                            { b.keep = true; b.why = "fórmula" }
                    }
                }
            }
        }
        var inRefs = false
        for (p in pages) for (b in per[p]!!) {
            val t = b.shown
            if (REF_HEAD.matches(t)) { inRefs = true; continue }
            if (inRefs && t.length < 80 && AFTER_REFS.containsMatchIn(t)) { inRefs = false; continue }
            if (inRefs && !b.keep) { b.keep = true; b.why = "referências" }
        }
        // primeira página: nomes e instituições entre o título e o "Abstract" ficam como estão
        per[pages.firstOrNull() ?: -1]?.takeIf { pages.first() == 0 }?.let { bl ->
            val head = bl.firstOrNull { Regex("^\\s*(abstract|resumo|summary)\\b", RegexOption.IGNORE_CASE).containsMatchIn(it.shown) }?.rect?.top
            val title = bl.filter { !it.keep }.maxByOrNull { it.size }
            if (head != null) for (b in bl) {
                if (b.keep || b === title || b.rect.bottom > head) continue
                val ws = Regex("[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’.-]*").findAll(b.shown).map { it.value }.toList()
                if (ws.isNotEmpty() && ws.size <= 12 && ws.all { it[0].isUpperCase() } && !Regex("[.!?]\\s*$").containsMatchIn(b.shown) &&
                    !Regex("\\b(article|research|review|access|original|letter|report|paper|study|case)\\b", RegexOption.IGNORE_CASE).containsMatchIn(b.shown)) {
                    b.keep = true; b.why = "nomes"
                }
            }
        }
        // parágrafo que continua na outra coluna/página: o anterior é o último bloco do corpo do texto, pulando notas,
        // legendas e figuras que ficam no meio
        val sizes = per.values.flatten().filter { !it.keep && !it.bold && it.nlines >= 2 }.map { it.size }.sorted()
        val body = sizes.getOrNull(sizes.size / 2)
        val caption = Regex("^\\s*(fig(?:ure|ura)?s?|tab(?:le|ela)?|chart|gr[áa]fico|quadro|scheme)\\.?\\s*[A-Z]?\\d+", RegexOption.IGNORE_CASE)
        var prev: TBlock? = null
        for (p in pages) for (b in per[p]!!) {
            if (b.keep) continue
            if (b.bold) { prev = null; continue }
            if ((body != null && kotlin.math.abs(b.size - body) >= 1.5f) || caption.containsMatchIn(b.shown)) continue
            val pv = prev
            if (pv != null && !Regex("[.!?:”\"»)]\\s*$").containsMatchIn(pv.shown) && b.shown.firstOrNull()?.isLowerCase() == true) b.cont = true
            prev = b
        }
        return per
    }

    /** Divide a tradução de um parágrafo que atravessa blocos, na proporção do original, sempre num espaço. */
    fun splitLike(text: String, parts: List<String>): List<String> {
        if (parts.size == 1) return listOf(text)
        val lens = parts.map { maxOf(1, Citacoes.plain(it).length) }
        val total = lens.sum()
        val cuts = ArrayList<Int>(); var acc = 0; var last = 0
        for (n in lens.dropLast(1)) {
            acc += n
            val pos = (text.length.toLong() * acc / total).toInt()
            var sp = text.lastIndexOf(' ', pos).takeIf { it > last } ?: text.indexOf(' ', pos)
            if (sp <= last) sp = maxOf(last, minOf(pos, text.length))
            cuts += sp; last = sp
        }
        val out = ArrayList<String>(); var prevCut = 0
        for (c in cuts + text.length) { out += text.substring(prevCut, c).trim(); prevCut = c }
        return out
    }
}

/** Escreve a tradução por cima do texto original (imagens e desenhos ficam): cópia do PDF só para leitura. */
object TranslatedPdf {
    private fun font(doc: PDDocument, ctx: Context, serif: Boolean, bold: Boolean): PDFont {
        val fam = if (serif) "LiberationSerif" else "LiberationSans"
        return ctx.assets.open("fontes/$fam-${if (bold) "Bold" else "Regular"}.ttf").use { PDType0Font.load(doc, it) }
    }

    private fun clean(f: PDFont, s: String): String = buildString {
        for (ch in s.replace('∗', '*')) append(if (runCatching { f.getStringWidth(ch.toString()) }.isSuccess) ch else '?')
    }

    private fun wrap(f: PDFont, text: String, size: Float, width: Float): List<String> {
        val out = ArrayList<String>(); var cur = ""
        for (w in text.split(' ')) {
            val cand = if (cur.isEmpty()) w else "$cur $w"
            if (f.getStringWidth(cand) / 1000f * size <= width || cur.isEmpty()) cur = cand else { out += cur; cur = w }
        }
        if (cur.isNotEmpty()) out += cur
        return out
    }

    /** Cor de fundo de cada bloco (a mais comum entre os pixels da página renderizada), para cobrir o original. */
    private fun backgrounds(doc: PDDocument, page: Int, rects: List<RectF>): List<FloatArray> {
        val white = rects.map { floatArrayOf(1f, 1f, 1f) }
        return runCatching {
            val bmp = com.tom_roush.pdfbox.rendering.PDFRenderer(doc).renderImage(page, 1f)
            try {
                rects.map { r ->
                    val counts = HashMap<Int, Int>()
                    val x0 = r.left.toInt().coerceIn(0, bmp.width - 1); val x1 = r.right.toInt().coerceIn(0, bmp.width - 1)
                    val y0 = r.top.toInt().coerceIn(0, bmp.height - 1); val y1 = r.bottom.toInt().coerceIn(0, bmp.height - 1)
                    val step = maxOf(1, minOf(x1 - x0, y1 - y0) / 12)
                    var y = y0
                    while (y <= y1) { var x = x0; while (x <= x1) {
                        val c = bmp.getPixel(x, y)
                        val q = (minOf(255, ((c shr 16 and 255) + 4) / 8 * 8) shl 16) or (minOf(255, ((c shr 8 and 255) + 4) / 8 * 8) shl 8) or
                            minOf(255, ((c and 255) + 4) / 8 * 8)
                        counts[q] = (counts[q] ?: 0) + 1; x += step }; y += step }
                    val q = counts.maxByOrNull { it.value }?.key ?: 0xFFFFFF
                    floatArrayOf((q shr 16 and 255) / 255f, (q shr 8 and 255) / 255f, (q and 255) / 255f)
                }
            } finally { bmp.recycle() }
        }.getOrDefault(white)
    }

    private class Plan(val b: TBlock, val text: String, val f: PDFont, val left: Float, val width: Float, val height: Float,
                       val bg: FloatArray, var size: Float)

    fun build(ctx: Context, src: File, password: String?, out: File, pages: Map<Int, List<Pair<TBlock, String?>>>) {
        PDDocument.load(src, password ?: "").use { doc ->
            doc.isAllSecurityToBeRemoved = true
            val fonts = HashMap<String, PDFont>()
            fun f(serif: Boolean, bold: Boolean) = fonts.getOrPut("$serif$bold") { font(doc, ctx, serif, bold) }
            for ((p, items) in pages) {
                val page = doc.getPage(p)
                if (page.rotation % 360 != 0) continue
                val box = page.cropBox
                val todo = items.filter { (b, t) -> t != null && !b.keep }
                if (todo.isEmpty()) continue
                val bgs = backgrounds(doc, p, todo.map { it.first.rect })
                val others = items.map { it.first.rect }
                val bottom = box.height * 0.94f
                val plans = todo.mapIndexed { k, (b, t0) ->
                    val font = f(b.serif, b.bold)
                    val t = clean(font, t0!!)
                    var left = b.rect.left; var w = b.rect.width()
                    if (b.nlines <= 1 && b.center) {          // título centralizado: cresce igual para os dois lados
                        val grow = minOf(b.rect.left - 36, box.width - 36 - b.rect.right).coerceAtLeast(0f)
                        left -= grow; w += grow * 2
                    } else if (b.nlines <= 1) {               // título de uma linha: pode crescer até a margem
                        val limit = box.width - 36 - b.rect.left
                        val blocker = others.filter { it !== b.rect && it.left > b.rect.right && it.top < b.rect.bottom && it.bottom > b.rect.top }
                        w = maxOf(w, (blocker.minOfOrNull { it.left - 4 - b.rect.left } ?: limit))
                    }
                    // e para baixo, até o próximo bloco (o português costuma ser ~20% mais longo)
                    val below = others.filter { it !== b.rect && it.top >= b.rect.bottom - 1 && it.left < left + w - 2 && it.right > left + 2 }
                        .minOfOrNull { it.top } ?: bottom
                    val h = (maxOf(b.rect.height(), minOf(below, bottom) - 2 - b.rect.top))
                        .coerceAtMost(b.rect.height() + maxOf(b.rect.height() * 0.6f, b.size * 3))
                    // maior tamanho de letra em que o texto cabe
                    var size = b.size
                    while (size > b.size * 0.3f && wrap(font, t, size, w).size * size * 1.15f > h + size * 0.2f) size *= 0.96f
                    Plan(b, t, font, left, w, h, bgs[k], size / b.size)
                }
                // mesmo tamanho de letra para o texto corrido da página
                val body = plans.filter { !it.b.bold && it.b.nlines >= 2 }
                if (body.isNotEmpty()) {
                    val ref = body.map { it.b.size }.sorted()[body.size / 2]
                    val similar = body.filter { kotlin.math.abs(it.b.size - ref) <= ref * 0.12f }
                    if (similar.isNotEmpty()) {
                        val common = similar.map { it.size }.sorted()[similar.size / 5]
                        for (pl in similar) pl.size = minOf(pl.size, common)
                    }
                }
                PDPageContentStream(doc, page, PDPageContentStream.AppendMode.APPEND, true, true).use { cs ->
                    for (pl in plans) {                        // primeiro cobre todos os originais, depois escreve
                        cs.setNonStrokingColor(pl.bg[0], pl.bg[1], pl.bg[2])
                        cs.addRect(box.lowerLeftX + pl.b.rect.left - 1, box.upperRightY - pl.b.rect.bottom - 0.8f, pl.b.rect.width() + 2, pl.b.rect.height() + 1.6f)
                        cs.fill()
                    }
                    for (pl in plans) {
                        val lum = 0.299f * pl.bg[0] + 0.587f * pl.bg[1] + 0.114f * pl.bg[2]
                        if (lum > 0.5f) cs.setNonStrokingColor(0.08f, 0.08f, 0.08f) else cs.setNonStrokingColor(1f, 1f, 1f)
                        val size = pl.b.size * pl.size
                        val lines = wrap(pl.f, pl.text, size, pl.width)
                        val maxLines = maxOf(1, ((pl.height + size * 0.2f) / (size * 1.15f)).toInt())
                        var y = box.upperRightY - pl.b.rect.top - size
                        for ((k, ln) in lines.withIndex()) {
                            if (k >= maxLines) break           // nunca escreve por cima do bloco seguinte
                            val lw = runCatching { pl.f.getStringWidth(ln) / 1000f * size }.getOrDefault(0f)
                            val x = if (pl.b.center) pl.left + (pl.width - lw) / 2 else pl.left
                            cs.beginText(); cs.setFont(pl.f, size); cs.newLineAtOffset(box.lowerLeftX + x, y); cs.showText(ln); cs.endText()
                            y -= size * 1.15f
                        }
                    }
                }
            }
            doc.save(out)
        }
    }
}

/** Tradução do documento inteiro, em ordem de leitura, página por página. */
object DocTranslator {
    suspend fun run(doc: PDDocument, pages: List<Int>, src: String, dst: String,
                    onPage: suspend (Int, List<Pair<TBlock, String?>>) -> Unit, cancelled: () -> Boolean = { false }) {
        val per = DocAnalysis.analyze(doc, pages)
        val units = ArrayList<MutableList<TBlock>>()
        var cur: MutableList<TBlock>? = null
        for (p in pages) for (b in per[p]!!) {
            if (b.keep) continue
            if (b.cont && cur != null) cur += b else { cur = mutableListOf(b); units += cur }
        }
        val left = pages.associateWith { p -> units.count { u -> u.any { it.page == p } } }.toMutableMap()
        val result = HashMap<TBlock, String>()
        val done = HashSet<Int>()
        suspend fun flush() {
            for (p in pages) {
                if (p in done) continue
                if ((left[p] ?: 0) > 0) break
                done += p
                onPage(p, per[p]!!.map { it to result[it] })
            }
        }
        flush()
        for (u in units) {
            if (cancelled()) return
            var text = ""
            for (b in u) text = if (text.endsWith("-") && b.text.firstOrNull()?.isLowerCase() == true) text.dropLast(1) + b.text
                else if (text.isEmpty()) b.text else "$text ${b.text}"
            val tr = Citacoes.translate(text) { Traducao.translate(src, dst, it) }
            DocAnalysis.splitLike(tr, u.map { it.text }).forEachIndexed { i, t -> result[u[i]] = t }
            for (p in u.map { it.page }.toSet()) left[p] = (left[p] ?: 1) - 1
            flush()
        }
    }
}
