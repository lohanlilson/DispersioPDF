package io.github.lohanlilson.lumenpdf

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
) {
    val shown get() = Citacoes.plain(text)
}

/** Citações ficam fora da tradução e voltam no fim da frase. Mesmas regras de lumenpdf/traducao.py. */
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
        for (para in c.paras) {
            var txt = ""
            var l = Float.MAX_VALUE; var t = Float.MAX_VALUE; var r = -1f; var b = -1f
            var maxSize = 0f; var boldChars = 0; var chars = 0
            for (ln in para) {
                val big = ln.flatten().maxOfOrNull { it.fontSizeInPt } ?: 0f
                val words = ln.map { w ->
                    val s = w.joinToString("") { it.unicode ?: "" }
                    val small = w.all { it.fontSizeInPt < big * 0.78f }
                    if (small && Regex("[\\d,;\\-–*†‡§]{1,15}").matches(s.trim()) && s.any { it.isDigit() }) "${Citacoes.SUP}${s.trim()}${Citacoes.SUP_END}"
                    else {
                        for (p in w) {
                            l = minOf(l, p.xDirAdj); r = maxOf(r, p.xDirAdj + p.widthDirAdj)
                            t = minOf(t, p.yDirAdj - p.heightDir * 1.15f); b = maxOf(b, p.yDirAdj + p.heightDir * 0.25f)
                            maxSize = maxOf(maxSize, p.fontSizeInPt)
                            chars++
                            if (p.font?.name?.contains("Bold", true) == true) boldChars++
                        }
                        s
                    }
                }
                var lineText = ""
                for (w in words) lineText = if (lineText.isEmpty() || w.firstOrNull() == Citacoes.SUP) lineText + w else "$lineText $w"
                lineText = lineText.trim()
                if (lineText.isEmpty()) continue
                txt = if (txt.endsWith("-") && lineText.first().isLowerCase()) txt.dropLast(1) + lineText
                    else if (txt.isEmpty()) lineText else "$txt $lineText"
            }
            txt = txt.replace(Regex("[ \\t]+"), " ").trim()
            if (txt.isEmpty() || r < 0) continue
            out += TBlock(page, RectF(l, t, r, b), txt, if (maxSize > 0) maxSize else 10f, chars > 0 && boldChars > chars / 2)
        }
        return out
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
            }
        }
        var inRefs = false
        for (p in pages) for (b in per[p]!!) {
            val t = b.shown
            if (REF_HEAD.matches(t)) { inRefs = true; continue }
            if (inRefs && t.length < 80 && AFTER_REFS.containsMatchIn(t)) { inRefs = false; continue }
            if (inRefs && !b.keep) { b.keep = true; b.why = "referências" }
        }
        var prev: TBlock? = null
        for (p in pages) for (b in per[p]!!) {
            if (b.keep) continue
            val pv = prev
            if (pv != null && !Regex("[.!?:”\"»)]\\s*$").containsMatchIn(pv.shown) && b.shown.firstOrNull()?.isLowerCase() == true &&
                kotlin.math.abs(pv.size - b.size) < 1.5f && !pv.bold) b.cont = true
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
    private fun font(doc: PDDocument, ctx: Context, bold: Boolean): PDFont =
        ctx.assets.open(if (bold) "fontes/LiberationSans-Bold.ttf" else "fontes/LiberationSans-Regular.ttf").use { PDType0Font.load(doc, it) }

    private fun clean(f: PDFont, s: String): String = buildString {
        for (ch in s) append(if (runCatching { f.getStringWidth(ch.toString()) }.isSuccess) ch else '?')
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

    fun build(ctx: Context, src: File, password: String?, out: File, pages: Map<Int, List<Pair<TBlock, String?>>>) {
        PDDocument.load(src, password ?: "").use { doc ->
            doc.isAllSecurityToBeRemoved = true
            val regular = font(doc, ctx, false); val bold = font(doc, ctx, true)
            for ((p, items) in pages) {
                val page = doc.getPage(p)
                if (page.rotation % 360 != 0) continue
                val box = page.cropBox
                val todo = items.filter { (b, t) -> t != null && !b.keep }
                if (todo.isEmpty()) continue
                PDPageContentStream(doc, page, PDPageContentStream.AppendMode.APPEND, true, true).use { cs ->
                    for ((b, _) in todo) {
                        cs.setNonStrokingColor(1f, 1f, 1f)
                        cs.addRect(box.lowerLeftX + b.rect.left - 1, box.upperRightY - b.rect.bottom - 1, b.rect.width() + 2, b.rect.height() + 2)
                        cs.fill()
                    }
                    cs.setNonStrokingColor(0.08f, 0.08f, 0.08f)
                    for ((b, t0) in todo) {
                        val f = if (b.bold) bold else regular
                        val t = clean(f, t0!!)
                        var w = b.rect.width()
                        if (b.rect.height() < b.size * 2) {     // título de uma linha: pode crescer até a margem
                            val limit = box.width - 36 - b.rect.left
                            val blocker = items.map { it.first.rect }.filter { it !== b.rect && it.left > b.rect.right && it.top < b.rect.bottom && it.bottom > b.rect.top }
                            w = maxOf(w, (blocker.minOfOrNull { it.left - 4 - b.rect.left } ?: limit))
                        }
                        var size = b.size * 0.95f
                        var lines = wrap(f, t, size, w)
                        while (size > b.size * 0.45f && lines.size * size * 1.15f > b.rect.height() + size * 0.3f) {
                            size *= 0.94f; lines = wrap(f, t, size, w)
                        }
                        var y = box.upperRightY - b.rect.top - size
                        for (ln in lines) {
                            cs.beginText(); cs.setFont(f, size); cs.newLineAtOffset(box.lowerLeftX + b.rect.left, y); cs.showText(ln); cs.endText()
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
